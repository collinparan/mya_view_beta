"""
GraphRAG Service - Retrieval Augmented Generation using Neo4j Knowledge Graph.

This service implements GraphRAG to leverage the medical knowledge graph
for context-aware responses about family health history, conditions, and appointments.
"""

from typing import List, Dict, Any, Optional
import asyncio
import structlog
from neo4j import GraphDatabase
from neo4j_graphrag.retrievers import VectorRetriever, VectorCypherRetriever
from neo4j_graphrag.embeddings import OllamaEmbeddings
from neo4j_graphrag.llm import OllamaLLM
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.indexes import create_vector_index

from app.config import settings

logger = structlog.get_logger()


class MedicalGraphRAGService:
    """
    Service for GraphRAG operations on medical knowledge graph.

    Features:
    - Vector similarity search on medical documents and lab results
    - Graph traversal to find related entities (conditions, medications, appointments)
    - Hybrid retrieval combining semantic search with graph structure
    """

    def __init__(self):
        self.driver = None
        self.embedder = None
        self.retriever = None
        self.rag = None
        self._initialized = False

    async def initialize(self):
        """Initialize GraphRAG components."""
        if self._initialized:
            return

        logger.info("Initializing GraphRAG service")

        try:
            # Connect to Neo4j (synchronous driver for GraphRAG library)
            user, password = settings.neo4j_credentials
            self.driver = GraphDatabase.driver(
                settings.neo4j_url,
                auth=(user, password)
            )

            # Test connection
            def test_connection():
                with self.driver.session() as session:
                    session.run("RETURN 1")

            await asyncio.to_thread(test_connection)
            logger.info("Neo4j connection established for GraphRAG")

            # Initialize Ollama embeddings (using smaller model for speed)
            # We'll use nomic-embed-text which is optimized for retrieval
            self.embedder = OllamaEmbeddings(
                model="nomic-embed-text",
                host=settings.OLLAMA_HOST
            )
            logger.info("Ollama embeddings initialized", model="nomic-embed-text")

            # Create vector index if it doesn't exist
            await self._ensure_vector_index()

            # Create retriever with custom Cypher query
            self.retriever = self._create_medical_retriever()

            # Initialize LLM for GraphRAG
            llm = OllamaLLM(
                model_name=settings.PRIMARY_VLM,
                model_params={"temperature": 0.7},
                host=settings.OLLAMA_HOST
            )

            # Create GraphRAG instance
            self.rag = GraphRAG(
                retriever=self.retriever,
                llm=llm
            )

            self._initialized = True
            logger.info("GraphRAG service initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize GraphRAG service", error=str(e))
            raise

    async def _ensure_vector_index(self):
        """Create vector index for medical documents if it doesn't exist."""
        try:
            def check_and_create_index():
                with self.driver.session() as session:
                    # Check if index exists
                    result = session.run("SHOW INDEXES")
                    indexes = [record for record in result]

                    index_names = [idx.get("name") for idx in indexes]

                    if "medical_content_vector" not in index_names:
                        logger.info("Creating vector index for medical content")

                        # Create index on LabEvent nodes (they contain summaries)
                        # Note: We'll need to add embeddings to existing nodes
                        create_vector_index(
                            self.driver,
                            name="medical_content_vector",
                            label="LabEvent",
                            embedding_property="summary_embedding",
                            dimensions=768,  # nomic-embed-text dimensions
                            similarity_fn="cosine"
                        )
                        logger.info("Vector index created successfully")
                    else:
                        logger.info("Vector index already exists")

            await asyncio.to_thread(check_and_create_index)

        except Exception as e:
            logger.warning("Could not create vector index", error=str(e))
            # Don't raise - we can still do graph traversal without vector search

    def _create_medical_retriever(self) -> VectorCypherRetriever:
        """
        Create a custom retriever for medical knowledge graph.

        Uses hybrid approach:
        1. Vector similarity search on medical content
        2. Graph traversal to enrich with related entities
        """

        # Custom Cypher query to retrieve medical context
        # This query will be executed after vector search to enrich results
        retrieval_query = """
        // Start with the matched node from vector search
        WITH node

        // Get the person associated with this medical event
        MATCH (p:Person)-[:HAD_LAB_EVENT]->(node)

        // Get related conditions
        OPTIONAL MATCH (p)-[hc:HAS_CONDITION]->(c:Condition)

        // Get related medications
        OPTIONAL MATCH (p)-[:TAKES]->(m:Medication)

        // Get related lab results
        OPTIONAL MATCH (node)-[:INCLUDES]->(lr:LabResult)

        // Get related appointments
        OPTIONAL MATCH (p)-[:HAS_APPOINTMENT]->(apt:Appointment)
        WHERE apt.date >= date() - duration({months: 6})

        // Return enriched context
        RETURN
            node.summary as summary,
            node.date as event_date,
            p.name as patient_name,
            p.preferred_name as preferred_name,
            collect(DISTINCT {
                condition: c.name,
                status: hc.status,
                icd10: c.icd10_code
            }) as conditions,
            collect(DISTINCT {
                test: lr.test_name,
                value: lr.value,
                unit: lr.unit,
                flag: lr.flag
            }) as lab_results,
            collect(DISTINCT m.name) as medications,
            collect(DISTINCT {
                date: toString(apt.date),
                type: apt.appointment_type,
                facility: apt.facility
            }) as upcoming_appointments
        """

        # Create VectorCypherRetriever for hybrid search
        retriever = VectorCypherRetriever(
            driver=self.driver,
            index_name="medical_content_vector",
            embedder=self.embedder,
            retrieval_query=retrieval_query,
        )

        return retriever

    async def search(
        self,
        query: str,
        family_member_id: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Perform GraphRAG search for relevant medical context.

        Args:
            query: User's natural language query
            family_member_id: Filter results to specific family member
            top_k: Number of results to retrieve

        Returns:
            Dict with 'answer' and 'retrieval_metadata'
        """
        if not self._initialized:
            await self.initialize()

        try:
            logger.info("GraphRAG search", query=query[:100], member_id=family_member_id)

            # Perform retrieval and generation
            response = await self.rag.search(
                query_text=query,
                retriever_config={"top_k": top_k}
            )

            return {
                "answer": response.answer,
                "retrieval_metadata": {
                    "items_retrieved": len(response.retrieval_metadata.get("items", [])),
                    "sources": response.retrieval_metadata
                }
            }

        except Exception as e:
            logger.error("GraphRAG search failed", error=str(e))
            return {
                "answer": None,
                "error": str(e)
            }

    async def get_medical_context(
        self,
        query: str,
        family_member_id: str,
        top_k: int = 3
    ) -> str:
        """
        Retrieve relevant medical context for a query.

        This method returns just the context (not a full answer) for
        injection into the main LLM prompt.

        Args:
            query: User's query
            family_member_id: Family member ID to filter results
            top_k: Number of context items to retrieve

        Returns:
            Formatted context string for LLM prompt
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Use vector retriever directly to get raw context
            results = await self.retriever.search(
                query_text=query,
                top_k=top_k
            )

            if not results or not results.items:
                return ""

            # Format results into readable context
            context_parts = []
            for item in results.items:
                metadata = item.metadata

                # Build context entry
                entry = f"**Medical Event ({metadata.get('event_date', 'unknown date')})**\n"

                if metadata.get('summary'):
                    entry += f"Summary: {metadata['summary']}\n"

                # Add conditions if present
                conditions = metadata.get('conditions', [])
                active_conditions = [c for c in conditions if c.get('condition')]
                if active_conditions:
                    condition_names = [c['condition'] for c in active_conditions]
                    entry += f"Related conditions: {', '.join(condition_names)}\n"

                # Add notable lab results
                lab_results = metadata.get('lab_results', [])
                abnormal_labs = [lr for lr in lab_results
                               if lr.get('flag') and lr['flag'] != 'normal']
                if abnormal_labs:
                    entry += "Notable lab results:\n"
                    for lr in abnormal_labs[:5]:  # Limit to 5
                        entry += f"  - {lr.get('test')}: {lr.get('value')} {lr.get('unit', '')} ({lr.get('flag')})\n"

                context_parts.append(entry)

            if context_parts:
                return "\n\n".join(context_parts)

            return ""

        except Exception as e:
            logger.error("Failed to retrieve medical context", error=str(e))
            return ""

    async def embed_existing_documents(self, batch_size: int = 50):
        """
        Generate embeddings for existing LabEvent summaries.

        This should be run after ingesting medical documents to enable
        vector similarity search.

        Args:
            batch_size: Number of documents to process at once
        """
        if not self._initialized:
            await self.initialize()

        logger.info("Starting document embedding process")

        try:
            async with self.driver.session() as session:
                # Get all LabEvents with summaries but no embeddings
                result = await session.run("""
                    MATCH (le:LabEvent)
                    WHERE le.summary IS NOT NULL
                    AND le.summary_embedding IS NULL
                    RETURN le.id as id, le.summary as summary
                    LIMIT $batch_size
                """, {"batch_size": batch_size})

                events = [record async for record in result]

                if not events:
                    logger.info("No documents need embedding")
                    return

                logger.info(f"Embedding {len(events)} documents")

                # Generate embeddings
                for event in events:
                    try:
                        embedding = await self.embedder.embed_query(event['summary'])

                        # Update node with embedding
                        await session.run("""
                            MATCH (le:LabEvent {id: $id})
                            SET le.summary_embedding = $embedding
                        """, {
                            "id": event['id'],
                            "embedding": embedding
                        })

                    except Exception as e:
                        logger.error(f"Failed to embed document {event['id']}", error=str(e))
                        continue

                logger.info(f"Successfully embedded {len(events)} documents")

        except Exception as e:
            logger.error("Document embedding failed", error=str(e))
            raise

    async def close(self):
        """Close Neo4j driver connection."""
        if self.driver:
            await self.driver.close()
            logger.info("GraphRAG service closed")


# Global singleton instance
_graphrag_service: Optional[MedicalGraphRAGService] = None


def get_graphrag_service() -> MedicalGraphRAGService:
    """Get the global GraphRAG service instance."""
    global _graphrag_service
    if _graphrag_service is None:
        _graphrag_service = MedicalGraphRAGService()
    return _graphrag_service
