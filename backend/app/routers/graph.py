"""
Graph router - REST endpoints for Neo4j graph exploration and queries.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

from app.models.database import run_cypher

router = APIRouter()
logger = structlog.get_logger()


class CypherQuery(BaseModel):
    """Cypher query request."""
    query: str
    params: Optional[Dict[str, Any]] = {}


class GraphNode(BaseModel):
    """Graph node representation."""
    id: str
    labels: List[str]
    properties: Dict[str, Any]


class GraphRelationship(BaseModel):
    """Graph relationship representation."""
    id: str
    type: str
    start_node: str
    end_node: str
    properties: Dict[str, Any]


class GraphData(BaseModel):
    """Full graph data for visualization."""
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]


@router.get("/schema")
async def get_graph_schema():
    """Get the graph database schema (node labels and relationship types)."""
    try:
        # Get node labels
        labels_result = await run_cypher("CALL db.labels()", {})
        labels = [r["label"] for r in labels_result] if labels_result else []

        # Get relationship types
        rel_result = await run_cypher("CALL db.relationshipTypes()", {})
        relationship_types = [r["relationshipType"] for r in rel_result] if rel_result else []

        # Get property keys
        props_result = await run_cypher("CALL db.propertyKeys()", {})
        property_keys = [r["propertyKey"] for r in props_result] if props_result else []

        # Get counts per label
        label_counts = {}
        for label in labels:
            count_result = await run_cypher(f"MATCH (n:{label}) RETURN count(n) as count", {})
            label_counts[label] = count_result[0]["count"] if count_result else 0

        return {
            "labels": labels,
            "relationship_types": relationship_types,
            "property_keys": property_keys,
            "label_counts": label_counts,
        }
    except Exception as e:
        logger.error("Failed to get graph schema", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overview")
async def get_graph_overview():
    """Get an overview of all nodes and relationships for visualization."""
    try:
        # Get all nodes with their labels and properties
        nodes_result = await run_cypher(
            """
            MATCH (n)
            RETURN id(n) as id, labels(n) as labels, properties(n) as props
            LIMIT 500
            """,
            {}
        )

        nodes = []
        for r in nodes_result or []:
            node_id = r.get("props", {}).get("id") or str(r["id"])
            nodes.append({
                "id": node_id,
                "neo4j_id": r["id"],
                "labels": r["labels"],
                "properties": _serialize_props(r["props"]),
                "label": _get_display_label(r["labels"], r["props"]),
            })

        # Get all relationships
        rels_result = await run_cypher(
            """
            MATCH (a)-[r]->(b)
            RETURN id(r) as id, type(r) as type,
                   properties(a).id as source_id, id(a) as source_neo4j_id,
                   properties(b).id as target_id, id(b) as target_neo4j_id,
                   properties(r) as props
            LIMIT 1000
            """,
            {}
        )

        relationships = []
        for r in rels_result or []:
            relationships.append({
                "id": str(r["id"]),
                "type": r["type"],
                "source": r.get("source_id") or str(r["source_neo4j_id"]),
                "target": r.get("target_id") or str(r["target_neo4j_id"]),
                "properties": _serialize_props(r.get("props", {})),
            })

        return {
            "nodes": nodes,
            "relationships": relationships,
            "node_count": len(nodes),
            "relationship_count": len(relationships),
        }
    except Exception as e:
        logger.error("Failed to get graph overview", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query")
async def execute_cypher_query(query_request: CypherQuery):
    """Execute a Cypher query and return results."""
    query = query_request.query.strip()

    # Basic safety checks - block destructive operations
    query_upper = query.upper()
    dangerous_keywords = ["DELETE", "REMOVE", "DROP", "DETACH", "CREATE INDEX", "CREATE CONSTRAINT"]
    for keyword in dangerous_keywords:
        if keyword in query_upper:
            raise HTTPException(
                status_code=400,
                detail=f"Query contains forbidden keyword: {keyword}. This interface is read-only."
            )

    try:
        results = await run_cypher(query, query_request.params or {})

        # Process results to handle Neo4j types
        processed_results = []
        for record in results or []:
            processed_record = {}
            for key, value in record.items():
                processed_record[key] = _serialize_value(value)
            processed_results.append(processed_record)

        return {
            "success": True,
            "results": processed_results,
            "count": len(processed_results),
        }
    except Exception as e:
        logger.error("Cypher query failed", query=query, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/node/{node_id}")
async def get_node_details(node_id: str):
    """Get detailed information about a specific node and its connections."""
    try:
        # Get node details
        node_result = await run_cypher(
            """
            MATCH (n {id: $id})
            RETURN id(n) as neo4j_id, labels(n) as labels, properties(n) as props
            """,
            {"id": node_id}
        )

        if not node_result:
            raise HTTPException(status_code=404, detail="Node not found")

        node = node_result[0]

        # Get connected nodes
        connections_result = await run_cypher(
            """
            MATCH (n {id: $id})-[r]-(connected)
            RETURN type(r) as relationship,
                   CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END as direction,
                   labels(connected) as connected_labels,
                   properties(connected) as connected_props
            """,
            {"id": node_id}
        )

        connections = []
        for r in connections_result or []:
            connections.append({
                "relationship": r["relationship"],
                "direction": r["direction"],
                "labels": r["connected_labels"],
                "properties": _serialize_props(r["connected_props"]),
                "name": _get_display_label(r["connected_labels"], r["connected_props"]),
            })

        return {
            "node": {
                "id": node_id,
                "neo4j_id": node["neo4j_id"],
                "labels": node["labels"],
                "properties": _serialize_props(node["props"]),
            },
            "connections": connections,
            "connection_count": len(connections),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get node details", node_id=node_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_graph_stats():
    """Get statistics about the graph database."""
    try:
        stats = {}

        # Total counts
        count_result = await run_cypher(
            "MATCH (n) RETURN count(n) as nodes",
            {}
        )
        stats["total_nodes"] = count_result[0]["nodes"] if count_result else 0

        rel_count_result = await run_cypher(
            "MATCH ()-[r]->() RETURN count(r) as relationships",
            {}
        )
        stats["total_relationships"] = rel_count_result[0]["relationships"] if rel_count_result else 0

        # Counts by type
        stats["persons"] = await _count_label("Person")
        stats["conditions"] = await _count_label("Condition")
        stats["medications"] = await _count_label("Medication")
        stats["allergens"] = await _count_label("Allergen")
        stats["documents"] = await _count_label("Document")
        stats["aliases"] = await _count_label("Alias")

        return stats
    except Exception as e:
        logger.error("Failed to get graph stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def _count_label(label: str) -> int:
    """Count nodes with a specific label."""
    result = await run_cypher(f"MATCH (n:{label}) RETURN count(n) as count", {})
    return result[0]["count"] if result else 0


def _serialize_props(props: dict) -> dict:
    """Serialize Neo4j properties to JSON-safe format."""
    if not props:
        return {}
    return {k: _serialize_value(v) for k, v in props.items()}


def _serialize_value(value):
    """Serialize a single Neo4j value to JSON-safe format."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    # Handle Neo4j date/datetime types
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if hasattr(value, 'iso_format'):
        return value.iso_format()
    # Fallback to string representation
    return str(value)


def _get_display_label(labels: list, props: dict) -> str:
    """Get a display label for a node."""
    # Try common name properties
    for key in ["name", "preferred_name", "full_legal_name", "title", "id"]:
        if key in props and props[key]:
            return str(props[key])
    # Fall back to first label
    return labels[0] if labels else "Unknown"
