"""
RAG (Retrieval-Augmented Generation) for query plans.

Stores successful query→plan pairs in ChromaDB.
Retrieves similar plans as few-shot examples for the LLM.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ChromaDB collection name for query plans
COLLECTION_NAME = "query_plans"


class QueryPlanRAG:
    """RAG system for OData query plans."""

    def __init__(self):
        self._collection = None
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize ChromaDB client."""
        try:
            import chromadb
            persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "/app/data/chroma_db")
            self._client = chromadb.PersistentClient(path=persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"RAG: ChromaDB collection '{COLLECTION_NAME}' ready")
        except Exception as e:
            logger.warning(f"RAG: ChromaDB init failed: {e}")
            self._collection = None

    def store_plan(
        self,
        query: str,
        plan: Dict[str, Any],
        service_id: str,
        entity_set: str,
        success: bool = True,
    ):
        """Store a successful query plan for future retrieval."""
        if not self._collection or not success:
            return

        try:
            # Create document text from query + plan
            doc = self._query_to_document(query, plan)

            # Create metadata
            metadata = {
                "service_id": service_id,
                "entity_set": entity_set,
                "intent": plan.get("intent", "unknown"),
                "has_filter": bool(plan.get("steps", [{}])[0].get("filter")),
                "has_top": bool(plan.get("steps", [{}])[0].get("top")),
            }

            # Generate ID from query hash
            import hashlib
            doc_id = hashlib.md5(query.lower().strip().encode()).hexdigest()

            # Upsert (insert or update)
            self._collection.upsert(
                ids=[doc_id],
                documents=[doc],
                metadatas=[metadata],
            )
            logger.info(f"RAG: Stored plan for query: {query[:50]}...")
        except Exception as e:
            logger.warning(f"RAG: Failed to store plan: {e}")

    def retrieve_plans(
        self,
        query: str,
        service_id: Optional[str] = None,
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve similar query plans as few-shot examples."""
        if not self._collection:
            return []

        try:
            # Create query text
            query_text = self._query_to_document(query, {})

            # Build where filter
            where_filter = None
            if service_id:
                where_filter = {"service_id": service_id}

            # Query ChromaDB
            results = self._collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_filter,
            )

            if not results or not results.get("documents"):
                return []

            # Parse results into examples
            examples = []
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 1.0

                # Only include if similarity is high enough (distance < 0.5)
                if distance < 0.5:
                    example = self._document_to_plan(doc, metadata)
                    if example:
                        examples.append(example)

            logger.info(f"RAG: Retrieved {len(examples)} similar plans")
            return examples
        except Exception as e:
            logger.warning(f"RAG: Failed to retrieve plans: {e}")
            return []

    def _query_to_document(self, query: str, plan: Dict[str, Any]) -> str:
        """Convert query + plan to searchable document."""
        parts = [query.lower().strip()]

        # Add plan info if available
        if plan:
            steps = plan.get("steps", [])
            if steps:
                step = steps[0]
                parts.append(f"service:{step.get('service_id', '')}")
                parts.append(f"entity:{step.get('entity_set', '')}")
                if step.get("filter"):
                    parts.append(f"filter:{step['filter']}")
                if step.get("select"):
                    parts.append(f"select:{','.join(step['select'])}")

        return " ".join(parts)

    def _document_to_plan(self, doc: str, metadata: Dict) -> Optional[Dict]:
        """Convert retrieved document back to plan example."""
        try:
            # Parse the document to extract plan info
            parts = doc.split()
            if len(parts) < 2:
                return None

            # Reconstruct minimal plan from metadata
            plan = {
                "intent": metadata.get("intent", "read"),
                "steps": [{
                    "service_id": metadata.get("service_id", ""),
                    "entity_set": metadata.get("entity_set", ""),
                    "select": ["*"],
                }],
            }

            # Extract original query (first part of document)
            query = parts[0] if parts else ""

            return {"query": query, "plan": plan}
        except Exception:
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG statistics."""
        if not self._collection:
            return {"available": False}

        try:
            count = self._collection.count()
            return {"available": True, "count": count}
        except Exception:
            return {"available": False}


# Module-level singleton
query_plan_rag = QueryPlanRAG()
