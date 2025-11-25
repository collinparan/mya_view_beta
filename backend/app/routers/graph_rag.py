"""
GraphRAG router - Endpoints for semantic similarity and RAG visualization.

Extends the graph explorer with semantic search capabilities.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import structlog

from app.services.graphrag import get_graphrag_service

router = APIRouter()
logger = structlog.get_logger()


class SimilarNode(BaseModel):
    """Similar node with similarity score."""
    id: str
    labels: List[str]
    properties: dict
    similarity_score: float


@router.get("/similar/{node_id}")
async def find_similar_nodes(
    node_id: str,
    top_k: int = Query(default=5, ge=1, le=20)
):
    """
    Find nodes semantically similar to the given node.

    This uses vector similarity on embeddings to find related medical events,
    even if they're not directly connected in the graph.

    Args:
        node_id: ID of the source node
        top_k: Number of similar nodes to return

    Returns:
        List of similar nodes with similarity scores
    """
    try:
        graphrag = get_graphrag_service()
        await graphrag.initialize()

        # Get the source node and its embedding
        async with graphrag.driver.session() as session:
            result = await session.run("""
                MATCH (source:LabEvent {id: $id})
                WHERE source.summary_embedding IS NOT NULL
                RETURN source.summary as summary,
                       source.summary_embedding as embedding,
                       source.id as id,
                       labels(source) as labels,
                       properties(source) as props
            """, {"id": node_id})

            source_record = await result.single()
            if not source_record:
                raise HTTPException(
                    status_code=404,
                    detail="Node not found or has no embedding"
                )

            source_embedding = source_record['embedding']

            # Find similar nodes using vector similarity
            similar_result = await session.run("""
                MATCH (target:LabEvent)
                WHERE target.summary_embedding IS NOT NULL
                  AND target.id <> $id
                WITH target,
                     gds.similarity.cosine(target.summary_embedding, $embedding) as similarity
                WHERE similarity > 0.5
                RETURN target.id as id,
                       labels(target) as labels,
                       properties(target) as props,
                       similarity
                ORDER BY similarity DESC
                LIMIT $top_k
            """, {
                "id": node_id,
                "embedding": source_embedding,
                "top_k": top_k
            })

            similar_nodes = []
            async for record in similar_result:
                # Serialize properties safely
                props = {}
                for key, value in record['props'].items():
                    if key == 'summary_embedding':
                        props[key] = f"<vector[{len(value)}]>"  # Don't send full embedding
                    elif hasattr(value, 'isoformat'):
                        props[key] = value.isoformat()
                    else:
                        props[key] = value

                similar_nodes.append({
                    "id": record['id'],
                    "labels": record['labels'],
                    "properties": props,
                    "similarity_score": float(record['similarity'])
                })

            return {
                "source_node_id": node_id,
                "similar_nodes": similar_nodes,
                "count": len(similar_nodes)
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to find similar nodes", node_id=node_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/semantic-search")
async def semantic_search(
    query: str = Query(..., min_length=3),
    family_member_id: Optional[str] = None,
    top_k: int = Query(default=5, ge=1, le=20)
):
    """
    Search the graph using natural language semantic search.

    Args:
        query: Natural language query
        family_member_id: Filter to specific family member
        top_k: Number of results to return

    Returns:
        List of semantically relevant nodes
    """
    try:
        graphrag = get_graphrag_service()
        await graphrag.initialize()

        # Embed the query
        query_embedding = await graphrag.embedder.embed_query(query)

        # Build cypher with optional family member filter
        cypher = """
            MATCH (le:LabEvent)
            WHERE le.summary_embedding IS NOT NULL
        """

        params = {
            "query_embedding": query_embedding,
            "top_k": top_k
        }

        if family_member_id:
            cypher += " AND exists((p:Person {id: $member_id})-[:HAD_LAB_EVENT]->(le))"
            params["member_id"] = family_member_id

        cypher += """
            WITH le,
                 gds.similarity.cosine(le.summary_embedding, $query_embedding) as similarity
            WHERE similarity > 0.3

            // Get the person
            MATCH (p:Person)-[:HAD_LAB_EVENT]->(le)

            // Get related info
            OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)
            OPTIONAL MATCH (le)-[:INCLUDES]->(lr:LabResult)

            RETURN le.id as id,
                   le.summary as summary,
                   le.date as date,
                   p.name as patient_name,
                   similarity,
                   collect(DISTINCT c.name) as conditions,
                   collect(DISTINCT {test: lr.test_name, value: lr.value, flag: lr.flag}) as lab_results
            ORDER BY similarity DESC
            LIMIT $top_k
        """

        async with graphrag.driver.session() as session:
            result = await session.run(cypher, params)

            results = []
            async for record in result:
                results.append({
                    "id": record['id'],
                    "summary": record['summary'],
                    "date": record['date'].isoformat() if record['date'] else None,
                    "patient_name": record['patient_name'],
                    "similarity_score": float(record['similarity']),
                    "conditions": [c for c in record['conditions'] if c],
                    "lab_results": [lr for lr in record['lab_results'] if lr.get('test')]
                })

            return {
                "query": query,
                "results": results,
                "count": len(results)
            }

    except Exception as e:
        logger.error("Semantic search failed", query=query, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embedding-stats")
async def get_embedding_stats():
    """Get statistics about embeddings in the graph."""
    try:
        graphrag = get_graphrag_service()
        await graphrag.initialize()

        async with graphrag.driver.session() as session:
            # Count nodes with embeddings
            result = await session.run("""
                MATCH (le:LabEvent)
                WITH count(le) as total,
                     sum(CASE WHEN le.summary_embedding IS NOT NULL THEN 1 ELSE 0 END) as with_embedding,
                     sum(CASE WHEN le.summary IS NOT NULL THEN 1 ELSE 0 END) as with_summary
                RETURN total, with_embedding, with_summary,
                       total - with_embedding as missing_embedding
            """)

            stats = await result.single()

            # Check if vector index exists
            index_result = await session.run("SHOW INDEXES")
            indexes = [record async for record in index_result]

            vector_indexes = [
                idx for idx in indexes
                if idx.get('type') == 'VECTOR' or 'vector' in str(idx.get('type', '')).lower()
            ]

            return {
                "total_lab_events": stats['total'],
                "with_embeddings": stats['with_embedding'],
                "with_summaries": stats['with_summary'],
                "missing_embeddings": stats['missing_embedding'],
                "embedding_coverage": f"{(stats['with_embedding'] / stats['total'] * 100):.1f}%" if stats['total'] > 0 else "0%",
                "vector_indexes": len(vector_indexes),
                "vector_index_names": [idx.get('name') for idx in vector_indexes]
            }

    except Exception as e:
        logger.error("Failed to get embedding stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
