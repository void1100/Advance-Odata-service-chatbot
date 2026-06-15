"""MCP server wrapper.

This exposes the orchestrator's tools as MCP-style tool calls. It can be
embedded into the FastAPI app via the /mcp endpoint, and also provides a
standalone run helper for `python -m app.mcp.mcp_server`.
"""
import asyncio
import json
from typing import Any, Dict, List

from app.services.service_manager import service_manager
from app.agents.orchestrator import orchestrator
from app.db.sqlite_store import list_sessions, get_messages
from loguru import logger


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "list_services",
        "description": "List all registered OData services and their entity sets.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "register_service",
        "description": "Register a new OData service by id, name, and base URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "base_url": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["id", "name", "base_url"],
        },
    },
    {
        "name": "query_odata",
        "description": "Run a natural-language query against the orchestrated OData services.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "session_id": {"type": "string"},
                "user_role": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_sessions",
        "description": "List chat sessions.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_messages",
        "description": "Get all messages for a session.",
        "input_schema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
    {
        "name": "execute_join",
        "description": "Execute a saved cross-service join by ID and return merged results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "join_id": {"type": "string", "description": "ID of the saved join to execute"},
            },
            "required": ["join_id"],
        },
    },
]


class MCPServer:
    def __init__(self):
        self.tools = list(TOOLS)
        self._custom_tool_names: set = set()

    def register_custom_entity_tool(self, service_id: str, entity_name: str, description: str, allowed_columns: list, base_entity_set: str):
        tool_name = f"query_{service_id}_{entity_name}"
        if tool_name in self._custom_tool_names:
            return
        properties = {}
        if allowed_columns:
            properties["select"] = {
                "type": "array",
                "items": {"type": "string", "enum": allowed_columns},
                "description": f"Columns to return. Allowed: {', '.join(allowed_columns)}",
            }
        properties["filter"] = {"type": "string", "description": "OData filter expression"}
        properties["expand"] = {"type": "array", "items": {"type": "string"}, "description": "Related entities to expand"}
        properties["orderby"] = {"type": "string", "description": "Order by column asc/desc"}
        properties["top"] = {"type": "integer", "description": "Max rows to return"}
        properties["skip"] = {"type": "integer", "description": "Rows to skip"}
        tool = {
            "name": tool_name,
            "description": f"[Custom] {description}. Base: {base_entity_set}. Service: {service_id}",
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": [],
            },
        }
        self.tools.append(tool)
        self._custom_tool_names.add(tool_name)
        logger.info(f"Registered MCP tool: {tool_name}")

    def remove_custom_entity_tool(self, service_id: str, entity_name: str):
        tool_name = f"query_{service_id}_{entity_name}"
        self.tools = [t for t in self.tools if t["name"] != tool_name]
        self._custom_tool_names.discard(tool_name)
        logger.info(f"Removed MCP tool: {tool_name}")

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "list_services":
            return {"services": service_manager.list_services()}
        if name == "register_service":
            svc = await service_manager.register_service(
                service_id=arguments["id"],
                name=arguments["name"],
                base_url=arguments["base_url"],
                description=arguments.get("description", ""),
            )
            return {"service": {"id": svc["id"], "name": svc["name"], "base_url": svc["base_url"]}}
        if name == "query_odata":
            res = await orchestrator.run(
                user_query=arguments["query"],
                session_id=arguments.get("session_id"),
                user_role=arguments.get("user_role", "Admin"),
            )
            return res
        if name == "list_sessions":
            return {"sessions": list_sessions()}
        if name == "get_messages":
            return {"messages": get_messages(arguments["session_id"])}
        if name == "execute_join":
            return await self._execute_join(arguments["join_id"])
        if name in self._custom_tool_names:
            return await self._call_custom_entity_tool(name, arguments)
        return {"error": f"Unknown tool: {name}"}

    async def _call_custom_entity_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        parts = tool_name.split("_", 2)
        if len(parts) < 3:
            return {"error": f"Invalid custom tool name: {tool_name}"}
        service_id = parts[1]
        entity_name = parts[2]
        plan = {
            "service_id": service_id,
            "entity_set": entity_name,
            "select": arguments.get("select"),
            "filter": arguments.get("filter"),
            "expand": arguments.get("expand"),
            "top": arguments.get("top", 50),
            "skip": arguments.get("skip"),
            "orderby": arguments.get("orderby"),
        }
        try:
            result = await service_manager.execute_plan(
                service_id=service_id,
                plan=plan,
                max_rows=arguments.get("top", 50),
            )
            return result
        except Exception as e:
            return {"error": str(e)}

    async def _execute_join(self, join_id: str) -> Dict[str, Any]:
        g = service_manager.graph()
        join_def = g.get_join(join_id)
        if not join_def:
            return {"error": f"Join not found: {join_id}"}
        from app.services.cross_service_join import union_join, match_join, enrichment_join
        try:
            left_client = service_manager.get_client(join_def["left_service"])
            right_client = service_manager.get_client(join_def["right_service"])
            if not left_client or not right_client:
                return {"error": "Service client not available"}
            left_table = await left_client.query(entity_set=join_def["left_entity"], top=200)
            right_table = await right_client.query(entity_set=join_def["right_entity"], top=200)
            left_data = left_client.flatten_odata_value(left_table)
            right_data = right_client.flatten_odata_value(right_table)
            left_cols = list(left_data[0].keys()) if left_data else []
            right_cols = list(right_data[0].keys()) if right_data else []
            strategy = join_def["strategy"]
            if strategy == "union":
                result = union_join(
                    [
                        {"service_id": join_def["left_service"], "table": {"columns": left_cols, "rows": left_data}},
                        {"service_id": join_def["right_service"], "table": {"columns": right_cols, "rows": right_data}},
                    ],
                    column_mapping=join_def.get("column_mapping"),
                )
            elif strategy == "match":
                result = match_join(
                    {"columns": left_cols, "rows": left_data},
                    {"columns": right_cols, "rows": right_data},
                    left_key=join_def["left_key"],
                    right_key=join_def["right_key"],
                    left_service=join_def["left_service"],
                    right_service=join_def["right_service"],
                )
            elif strategy == "enrichment":
                result = enrichment_join(
                    {"columns": left_cols, "rows": left_data},
                    {"columns": right_cols, "rows": right_data},
                    primary_key=join_def["left_key"],
                    secondary_key=join_def["right_key"],
                    primary_service=join_def["left_service"],
                    secondary_service=join_def["right_service"],
                )
            else:
                return {"error": f"Unknown strategy: {strategy}"}
            return {"join": join_def, "result": result}
        except Exception as e:
            return {"error": str(e)}


mcp_server = MCPServer()


if __name__ == "__main__":
    logger.info("MCP server tools available:")
    for t in TOOLS:
        logger.info(f"  - {t['name']}: {t['description']}")
