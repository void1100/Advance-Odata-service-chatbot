"""Multi-entity aggregation for complex queries that span multiple entities
within the same OData service (e.g., sales by country needs Customers + Orders + Order_Details).

Fully dynamic — auto-detects entity relationships from column name matching.
No hardcoded service-specific chains.
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from loguru import logger


SALES_VALUE_PATTERNS = [
    (r"UnitPrice", "Quantity", "Discount"),
    (r"UnitPrice", "Quantity", None),
    (r"price", "quantity", "discount"),
    (r"price", "quantity", None),
    (r"amount", "quantity", "discount"),
    (r"amount", "quantity", None),
    (r"cost", "quantity", "discount"),
    (r"cost", "quantity", None),
]

SALES_FORMULA = "price * qty * (1 - disc)"

AGGREGATION_QUERY_PATTERNS = [
    (r'(?:total|sum|amount)\s+(?:of\s+)?(?:sales|revenue|amount|income|earnings|profit|cost|value|price|turnover)', "sales"),
    (r'(?:sales|revenue|amount|income|earnings|profit|cost|turnover|price|value)\s+(?:per|by|from|of|for)\s+(?:each|every|all)?', "sales"),
    (r'percentage.*?(?:total|sum)?\s*(?:sales|revenue|amount|income|earnings|profit|cost|value|price|turnover)', "sales"),
    (r'average.*?(?:order|transaction|sale|purchase|deal|invoice)', "avg_per_order"),
    (r'(?:count|number|total)\s+(?:of\s+)?(?:orders|transactions|sales|purchases|deals|invoices|bills)', "count_orders"),
    (r'(?:orders|transactions|sales|purchases|deals|invoices|bills)\s+(?:per|by|from|of)', "count_orders"),
]

GROUP_WORD_TO_COLUMN = {
    "country": "Country",
    "category": "Category",
    "region": "Region",
    "city": "City",
    "supplier": "Supplier",
    "employee": "Employee",
    "customer": "Customer",
    "product": "Product",
    "order": "Order",
    "status": "Status",
    "type": "Type",
    "year": "Year",
    "month": "Month",
    "quarter": "Quarter",
    "department": "Department",
    "user": "User",
    "seller": "Seller",
    "buyer": "Buyer",
    "vendor": "Vendor",
    "brand": "Brand",
    "shipper": "Shipper",
}


def _ensure_join_keys(chain: List[Dict[str, str]]):
    """Ensure all join keys are in columns_to_keep for each chain step."""
    for i, step in enumerate(chain):
        if step.get("key"):
            step["columns_to_keep"].append(step["key"])
        if step.get("link_to"):
            step["columns_to_keep"].append(step["link_to"])
        if i < len(chain) - 1:
            next_step = chain[i + 1]
            if next_step.get("link_to"):
                step["columns_to_keep"].append(next_step["link_to"])
            if next_step.get("key"):
                step["columns_to_keep"].append(next_step["key"])


def _detect_entity_relationships(entities_with_cols: Dict[str, List[str]]) -> Dict[str, List[Dict[str, str]]]:
    """Auto-detect relationships between entities by finding matching column names.

    Returns: {entity_a: [{entity_b, key_in_a, key_in_b}, ...], ...}
    """
    relationships: Dict[str, List[Dict[str, str]]] = {e: [] for e in entities_with_cols}
    entity_names = list(entities_with_cols.keys())

    for i, entity_a in enumerate(entity_names):
        cols_a = set(c.lower() for c in entities_with_cols[entity_a])
        for entity_b in entity_names[i+1:]:
            cols_b = set(c.lower() for c in entities_with_cols[entity_b])
            common = cols_a & cols_b
            meaningful_common = {
                c for c in common
                if not c.startswith("@odata")
                and c not in ("email", "emails", "concurrency", "photo", "notes",
                              "photopath", "addressinfo", "phones")
            }
            for col_lower in meaningful_common:
                orig_a = next((c for c in entities_with_cols[entity_a] if c.lower() == col_lower), col_lower)
                orig_b = next((c for c in entities_with_cols[entity_b] if c.lower() == col_lower), col_lower)
                relationships[entity_a].append({
                    "entity": entity_b, "key": orig_a, "remote_key": orig_b,
                })
                relationships[entity_b].append({
                    "entity": entity_a, "key": orig_b, "remote_key": orig_a,
                })

    return relationships


def _find_group_column(group_word: str, all_columns: Dict[str, List[str]]) -> Optional[Tuple[str, str]]:
    """Find which entity has the group-by column matching the query word."""
    canonical = GROUP_WORD_TO_COLUMN.get(group_word.lower().rstrip("s"))
    candidates = {group_word.lower(), group_word.lower().rstrip("s")}
    if canonical:
        candidates.add(canonical.lower())

    for entity, cols in all_columns.items():
        for c in cols:
            cl = c.lower()
            for cand in candidates:
                if cand == cl or cl.startswith(cand) or cand.startswith(cl.rstrip("s")):
                    if not cl.startswith("@odata") and cl not in ("email", "emails", "concurrency", "photo", "notes", "photopath"):
                        return (entity, c)
    return None


def _find_sales_entities(all_columns: Dict[str, List[str]]) -> Optional[Dict[str, Any]]:
    """Auto-detect which entities have sales-relevant columns (price, quantity, discount).

    Prefers entities that have BOTH price+qty (like Order_Details) over
    separate entities for each.
    """
    price_cols = {}
    qty_cols = {}
    disc_cols = {}

    qty_keywords = ("quantity", "qty", "numitems", "num_items")
    price_keywords = ("unitprice", "priceperunit", "costprice", "rate", "salary", "wage", "freight")
    disc_keywords = ("discount",)

    for entity, cols in all_columns.items():
        for c in cols:
            cl = c.lower()
            if cl in price_keywords:
                price_cols[entity] = c
            if cl in qty_keywords:
                qty_cols[entity] = c
            if cl in disc_keywords:
                disc_cols[entity] = c

    if price_cols and qty_cols:
        common = set(price_cols.keys()) & set(qty_cols.keys())
        if common:
            preferred = common.pop()
            return {
                "price_entity": preferred, "price_col": price_cols[preferred],
                "qty_entity": preferred, "qty_col": qty_cols[preferred],
                "disc_entity": preferred if preferred in disc_cols else None,
                "disc_col": disc_cols.get(preferred),
            }
        price_entity = list(price_cols.keys())[0]
        qty_entity = list(qty_cols.keys())[0]
        disc_entity = next((e for e in disc_cols if e in (price_entity, qty_entity)), list(disc_cols.keys())[0] if disc_cols else None)
        return {
            "price_entity": price_entity, "price_col": price_cols[price_entity],
            "qty_entity": qty_entity, "qty_col": qty_cols[qty_entity],
            "disc_entity": disc_entity,
            "disc_col": disc_cols.get(disc_entity) if disc_entity else None,
        }
    return None


def _build_chain(
    group_entity: str,
    group_col: str,
    value_entities: Set[str],
    relationships: Dict[str, List[Dict[str, str]]],
    all_entities: List[str],
) -> Optional[List[Dict[str, str]]]:
    """Find shortest path from group_entity to all value_entities using BFS."""
    remaining = set(value_entities) - {group_entity}
    if not remaining:
        return [{"entity": group_entity, "key": None, "link_to": None, "columns_to_keep": [group_col]}]

    parent = {}
    queue = [group_entity]
    visited = {group_entity}
    found = set()

    while queue and remaining:
        next_queue = []
        for ent in queue:
            for rel in relationships.get(ent, []):
                target = rel["entity"]
                if target in visited:
                    continue
                visited.add(target)
                parent[target] = (ent, rel["key"], rel["remote_key"])
                next_queue.append(target)
                if target in remaining:
                    found.add(target)
        queue = next_queue
        if found:
            remaining -= found

    chain = [{"entity": group_entity, "key": None, "link_to": None, "columns_to_keep": [group_col]}]
    included = {group_entity}

    for target in value_entities:
        if target == group_entity:
            continue
        path = []
        node = target
        while node in parent:
            prev, key, remote_key = parent[node]
            path.append({"entity": node, "key": key, "link_to": remote_key, "columns_to_keep": []})
            node = prev
        path.reverse()
        for step in path:
            if step["entity"] not in included:
                chain.append(step)
                included.add(step["entity"])

    return chain


def detect_multi_entity_query(query: str, service_id: str, entity_columns: Optional[Dict[str, List[str]]] = None) -> Optional[Dict[str, Any]]:
    """Detect if a query requires multi-entity aggregation for any service."""
    q = query.lower().strip()

    agg_type = None
    for pattern, atype in AGGREGATION_QUERY_PATTERNS:
        if re.search(pattern, q):
            agg_type = atype
            break

    if not agg_type:
        return None

    if not entity_columns:
        return None

    group_match = re.search(r'(?:by|per)\s+(?:each|every|all)?\s*(\w+)', q)
    if not group_match:
        group_match = re.search(r'(?:from|of)\s+(?:each|every|all)?\s*(\w+)', q)
    if not group_match:
        return None
    group_word = group_match.group(1)

    group_loc = _find_group_column(group_word, entity_columns)
    if not group_loc:
        return None

    group_entity, group_col = group_loc

    if agg_type == "sales":
        sales_info = _find_sales_entities(entity_columns)
        if not sales_info:
            return None
        value_entities = {sales_info["price_entity"], sales_info["qty_entity"]}
        if sales_info["disc_entity"]:
            value_entities.add(sales_info["disc_entity"])

        relationships = _detect_entity_relationships(entity_columns)
        chain = _build_chain(group_entity, group_col, value_entities, relationships, list(entity_columns.keys()))
        if not chain:
            return None

        for step in chain:
            if step["entity"] == sales_info["price_entity"]:
                step["columns_to_keep"].append(sales_info["price_col"])
            if step["entity"] == sales_info["qty_entity"]:
                step["columns_to_keep"].append(sales_info["qty_col"])
            if sales_info["disc_entity"] and step["entity"] == sales_info["disc_entity"]:
                step["columns_to_keep"].append(sales_info["disc_col"])

        _ensure_join_keys(chain)

        return {
            "type": "sales_by",
            "group_entity": group_entity,
            "group_col": group_col,
            "chain": chain,
            "sales_info": sales_info,
        }

    elif agg_type == "count_orders":
        relationships = _detect_entity_relationships(entity_columns)
        order_entities = set()
        for ent, cols in entity_columns.items():
            for c in cols:
                if any(kw in c.lower() for kw in ("orderid", "order_id", "transactionid", "invoiceid", "billid", "dealid")):
                    order_entities.add(ent)

        if not order_entities:
            order_entities = set(entity_columns.keys()) - {group_entity}

        chain = _build_chain(group_entity, group_col, order_entities, relationships, list(entity_columns.keys()))
        if not chain:
            return None

        _ensure_join_keys(chain)

        return {
            "type": "count_orders",
            "group_entity": group_entity,
            "group_col": group_col,
            "chain": chain,
        }

    elif agg_type == "avg_per_order":
        sales_info = _find_sales_entities(entity_columns)
        if not sales_info:
            return None
        value_entities = {sales_info["price_entity"], sales_info["qty_entity"]}
        relationships = _detect_entity_relationships(entity_columns)
        chain = _build_chain(group_entity, group_col, value_entities, relationships, list(entity_columns.keys()))
        if not chain:
            return None

        for step in chain:
            if step["entity"] == sales_info["price_entity"]:
                step["columns_to_keep"].append(sales_info["price_col"])
            if step["entity"] == sales_info["qty_entity"]:
                step["columns_to_keep"].append(sales_info["qty_col"])

        _ensure_join_keys(chain)

        return {
            "type": "avg_order_by",
            "group_entity": group_entity,
            "group_col": group_col,
            "chain": chain,
            "sales_info": sales_info,
        }

    return None


async def execute_multi_entity_aggregation(
    query: str,
    service_id: str,
    client,
    me_info: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Execute multi-entity aggregation using auto-detected chain."""
    chain = me_info["chain"]
    group_col = me_info["group_col"]
    agg_type = me_info["type"]

    try:
        entity_data = {}
        fetched_entities = set()
        for step in chain:
            entity = step["entity"]
            if entity in fetched_entities:
                continue
            logger.info(f"Multi-entity: fetching {entity} from {service_id}")
            raw = await client.query(entity_set=entity, top=500)
            flat = client.flatten_odata_value(raw)
            cols_to_keep = step.get("columns_to_keep", [])
            if cols_to_keep:
                flat = [{k: r.get(k) for k in cols_to_keep if k in r} for r in flat]
            entity_data[entity] = flat
            fetched_entities.add(entity)
            logger.info(f"  {entity}: {len(flat)} rows, cols: {list(flat[0].keys()) if flat else []}")

        joined_rows = entity_data[chain[0]["entity"]][:]

        for i in range(1, len(chain)):
            step = chain[i]
            link_col = step["link_to"]
            join_key = step["key"]
            right_data = entity_data.get(step["entity"], [])
            right_by_key = {}
            for r in right_data:
                k = r.get(join_key)
                if k not in right_by_key:
                    right_by_key[k] = []
                right_by_key[k].append(r)
            new_rows = []
            for left_row in joined_rows:
                left_val = left_row.get(link_col)
                matches = right_by_key.get(left_val, [])
                if matches:
                    for m_row in matches:
                        new_row = {**left_row}
                        for rk, rv in m_row.items():
                            if rk not in new_row or rk == join_key:
                                new_row[rk] = rv
                        new_rows.append(new_row)
                else:
                    new_rows.append(left_row)
            joined_rows = new_rows
            logger.info(f"  After joining {step['entity']}: {len(joined_rows)} rows")

        if agg_type == "sales_by":
            sales_info = me_info.get("sales_info", {})
            price_col = sales_info.get("price_col", "UnitPrice")
            qty_col = sales_info.get("qty_col", "Quantity")
            disc_col = sales_info.get("disc_col")
            value_col = "Sales"

            for r in joined_rows:
                try:
                    up = float(r.get(price_col, 0) or 0)
                    qty = float(r.get(qty_col, 0) or 0)
                    disc = float(r.get(disc_col, 0) or 0) if disc_col else 0
                    r[value_col] = round(up * qty * (1 - disc), 2)
                except (ValueError, TypeError):
                    r[value_col] = 0

            groups = {}
            for r in joined_rows:
                g = str(r.get(group_col, "Unknown") or "Unknown")
                if g not in groups:
                    groups[g] = 0
                groups[g] += r.get(value_col, 0)

            total = sum(groups.values()) or 1
            result_rows = []
            for g, val in sorted(groups.items(), key=lambda x: x[1], reverse=True):
                result_rows.append({
                    group_col: g,
                    "total_sales": round(val, 2),
                    "percentage": round((val / total) * 100, 2),
                })

            pct_filter = re.search(r'(?:more than|greater than|above|over|>)\s*(\d+(?:\.\d+)?)\s*%', query, re.IGNORECASE)
            if pct_filter:
                threshold = float(pct_filter.group(1))
                result_rows = [r for r in result_rows if r["percentage"] > threshold]

            return {
                "columns": [group_col, "total_sales", "percentage"],
                "rows": result_rows,
                "row_count": len(result_rows),
                "truncated": False,
                "total_count": len(result_rows),
                "summary": f"Sales by {group_col}: {len(result_rows)} groups from {len(joined_rows)} records",
            }

        elif agg_type == "count_orders":
            order_id_col = None
            for ent, cols in entity_data.items():
                for c in cols[0].keys() if cols else []:
                    if "orderid" in c.lower() or "order_id" in c.lower() or "id" == c.lower():
                        order_id_col = c
                        break
                if order_id_col:
                    break
            if not order_id_col:
                for ent, cols in entity_data.items():
                    if cols:
                        order_id_col = list(cols[0].keys())[0]
                        break

            groups = {}
            for r in joined_rows:
                g = str(r.get(group_col, "Unknown") or "Unknown")
                if g not in groups:
                    groups[g] = set()
                groups[g].add(r.get(order_id_col))

            result_rows = []
            for g, ids in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
                result_rows.append({group_col: g, "order_count": len(ids)})

            return {
                "columns": [group_col, "order_count"],
                "rows": result_rows,
                "row_count": len(result_rows),
                "truncated": False,
                "total_count": len(result_rows),
                "summary": f"Orders by {group_col}: {len(result_rows)} groups from {len(joined_rows)} records",
            }

        elif agg_type == "avg_order_by":
            sales_info = me_info.get("sales_info", {})
            price_col = sales_info.get("price_col", "UnitPrice")
            qty_col = sales_info.get("qty_col", "Quantity")
            disc_col = sales_info.get("disc_col")

            order_id_col = None
            for ent, cols in entity_data.items():
                for c in cols[0].keys() if cols else []:
                    if "orderid" in c.lower() or "order_id" in c.lower():
                        order_id_col = c
                        break
                if order_id_col:
                    break

            for r in joined_rows:
                try:
                    up = float(r.get(price_col, 0) or 0)
                    qty = float(r.get(qty_col, 0) or 0)
                    disc = float(r.get(disc_col, 0) or 0) if disc_col else 0
                    r["Sales"] = round(up * qty * (1 - disc), 2)
                except (ValueError, TypeError):
                    r["Sales"] = 0

            order_totals = {}
            for r in joined_rows:
                oid = r.get(order_id_col, id(r))
                g = str(r.get(group_col, "Unknown") or "Unknown")
                key = (g, oid)
                if key not in order_totals:
                    order_totals[key] = 0
                order_totals[key] += r.get("Sales", 0)

            groups = {}
            for (g, oid), total in order_totals.items():
                if g not in groups:
                    groups[g] = []
                groups[g].append(total)

            result_rows = []
            for g, totals in sorted(groups.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True):
                avg = round(sum(totals) / len(totals), 2) if totals else 0
                result_rows.append({group_col: g, "avg_order_value": avg, "order_count": len(totals)})

            return {
                "columns": [group_col, "avg_order_value", "order_count"],
                "rows": result_rows,
                "row_count": len(result_rows),
                "truncated": False,
                "total_count": len(result_rows),
                "summary": f"Average order value by {group_col}: {len(result_rows)} groups",
            }

    except Exception as e:
        logger.error(f"Multi-entity aggregation failed: {e}")
        return None

    return None
