"""Cross-Service Entity Join Engine.

Supports three join strategies:
- union: Stack rows from multiple services into one table
- match: Match rows by a common key across services
- enrichment: Query one service, use results to query another
"""
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


def union_join(
    results: List[Dict[str, Any]],
    column_mapping: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Stack rows from multiple services into one unified table.
    
    Args:
        results: List of {"service_id": ..., "table": {"columns": [...], "rows": [...]}}
        column_mapping: Optional mapping to rename columns per service.
            e.g. {"northwind": {"UnitPrice": "Price"}, "sample": {"Price": "Price"}}
    """
    all_columns = []
    seen_cols = set()
    all_rows = []
    for r in results:
        svc = r.get("service_id", "unknown")
        table = r.get("table", {})
        cols = table.get("columns", [])
        rows = table.get("rows", [])
        mapping = (column_mapping or {}).get(svc, {})
        for col in cols:
            mapped = mapping.get(col, col)
            if mapped not in seen_cols:
                all_columns.append(mapped)
                seen_cols.add(mapped)
        for row in rows:
            if isinstance(row, dict):
                mapped_row = {}
                for k, v in row.items():
                    mapped_row[mapping.get(k, k)] = v
                mapped_row["source_service"] = svc
                all_rows.append(mapped_row)
            elif isinstance(row, list):
                mapped_row = {}
                for i, col in enumerate(cols):
                    mapped_row[mapping.get(col, col)] = row[i] if i < len(row) else None
                mapped_row["source_service"] = svc
                all_rows.append(mapped_row)
    all_columns.append("source_service")
    normalized = []
    for row in all_rows:
        normalized.append({col: row.get(col) for col in all_columns})
    return {"columns": all_columns, "rows": normalized, "row_count": len(normalized), "strategy": "union"}


def match_join(
    left_result: Dict[str, Any],
    right_result: Dict[str, Any],
    left_key: str,
    right_key: str,
    left_service: str,
    right_service: str,
    join_type: str = "inner",
) -> Dict[str, Any]:
    """Match rows from two services by a common key.
    
    Args:
        left_result: {"columns": [...], "rows": [...]}
        right_result: {"columns": [...], "rows": [...]}
        left_key: Column name in left to match on
        right_key: Column name in right to match on
        join_type: "inner", "left", "right", "outer"
    """
    left_cols = left_result.get("columns", [])
    right_cols = right_result.get("columns", [])
    left_rows = left_result.get("rows", [])
    right_rows = right_result.get("rows", [])
    right_index = {}
    for row in right_rows:
        if isinstance(row, dict):
            key_val = row.get(right_key)
        elif isinstance(row, list):
            idx = right_cols.index(right_key) if right_key in right_cols else -1
            key_val = row[idx] if idx >= 0 and idx < len(row) else None
        else:
            continue
        if key_val not in right_index:
            right_index[key_val] = []
        right_index[key_val].append(row)
    merged_rows = []
    matched_right_keys = set()
    for row in left_rows:
        if isinstance(row, dict):
            key_val = row.get(left_key)
            left_data = dict(row)
        elif isinstance(row, list):
            idx = left_cols.index(left_key) if left_key in left_cols else -1
            key_val = row[idx] if idx >= 0 and idx < len(row) else None
            left_data = {left_cols[i]: row[i] for i in range(len(left_cols)) if i < len(row)}
        else:
            continue
        if key_val in right_index:
            matched_right_keys.add(key_val)
            for right_row in right_index[key_val]:
                merged = dict(left_data)
                if isinstance(right_row, dict):
                    for k, v in right_row.items():
                        if k != right_key:
                            merged[f"right_{k}"] = v
                elif isinstance(right_row, list):
                    for i, col in enumerate(right_cols):
                        if col != right_key and i < len(right_row):
                            merged[f"right_{col}"] = right_row[i]
                merged["left_service"] = left_service
                merged["right_service"] = right_service
                merged_rows.append(merged)
        elif join_type in ("left", "outer"):
            merged = dict(left_data)
            for col in right_cols:
                if col != right_key:
                    merged[f"right_{col}"] = None
            merged["left_service"] = left_service
            merged["right_service"] = None
            merged_rows.append(merged)
    if join_type in ("right", "outer"):
        for key_val, right_rows_list in right_index.items():
            if key_val not in matched_right_keys:
                for right_row in right_rows_list:
                    merged = {}
                    for col in left_cols:
                        merged[col] = None
                    if isinstance(right_row, dict):
                        for k, v in right_row.items():
                            if k != right_key:
                                merged[f"right_{k}"] = v
                    elif isinstance(right_row, list):
                        for i, col in enumerate(right_cols):
                            if col != right_key and i < len(right_row):
                                merged[f"right_{col}"] = right_row[i]
                    merged["left_service"] = None
                    merged["right_service"] = right_service
                    merged_rows.append(merged)
    all_columns = list(left_cols) + [f"right_{c}" for c in right_cols if c != right_key] + ["left_service", "right_service"]
    normalized = []
    for row in merged_rows:
        normalized.append({col: row.get(col) for col in all_columns})
    return {"columns": all_columns, "rows": normalized, "row_count": len(normalized), "strategy": "match"}


def enrichment_join(
    primary_result: Dict[str, Any],
    secondary_result: Dict[str, Any],
    primary_key: str,
    secondary_key: str,
    primary_service: str,
    secondary_service: str,
) -> Dict[str, Any]:
    """Enrich primary results with data from secondary service.
    
    Similar to match_join but designed for nested lookups.
    Primary rows are preserved; secondary data is added as extra columns.
    """
    primary_cols = primary_result.get("columns", [])
    secondary_cols = secondary_result.get("columns", [])
    primary_rows = primary_result.get("rows", [])
    secondary_rows = secondary_result.get("rows", [])
    secondary_index = {}
    for row in secondary_rows:
        if isinstance(row, dict):
            key_val = row.get(secondary_key)
        elif isinstance(row, list):
            idx = secondary_cols.index(secondary_key) if secondary_key in secondary_cols else -1
            key_val = row[idx] if idx >= 0 and idx < len(row) else None
        else:
            continue
        if key_val not in secondary_index:
            secondary_index[key_val] = row
    enriched_rows = []
    for row in primary_rows:
        if isinstance(row, dict):
            key_val = row.get(primary_key)
            enriched = dict(row)
        elif isinstance(row, list):
            idx = primary_cols.index(primary_key) if primary_key in primary_cols else -1
            key_val = row[idx] if idx >= 0 and idx < len(row) else None
            enriched = {primary_cols[i]: row[i] for i in range(len(primary_cols)) if i < len(row)}
        else:
            continue
        if key_val in secondary_index:
            sec_row = secondary_index[key_val]
            if isinstance(sec_row, dict):
                for k, v in sec_row.items():
                    if k != secondary_key:
                        enriched[f"enriched_{k}"] = v
            elif isinstance(sec_row, list):
                for i, col in enumerate(secondary_cols):
                    if col != secondary_key and i < len(sec_row):
                        enriched[f"enriched_{col}"] = sec_row[i]
        else:
            for col in secondary_cols:
                if col != secondary_key:
                    enriched[f"enriched_{col}"] = None
        enriched["primary_service"] = primary_service
        enriched["secondary_service"] = secondary_service
        enriched_rows.append(enriched)
    all_columns = list(primary_cols) + [f"enriched_{c}" for c in secondary_cols if c != secondary_key] + ["primary_service", "secondary_service"]
    normalized = []
    for row in enriched_rows:
        normalized.append({col: row.get(col) for col in all_columns})
    return {"columns": all_columns, "rows": normalized, "row_count": len(normalized), "strategy": "enrichment"}
