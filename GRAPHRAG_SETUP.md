# GraphRAG Setup Guide

This guide explains how to set up and use GraphRAG (Graph Retrieval Augmented Generation) with Mya View.

## What is GraphRAG?

GraphRAG combines the power of Neo4j's knowledge graph with semantic search to provide contextually rich, accurate responses. Instead of just searching text, GraphRAG:

1. **Understands relationships** - Knows how conditions, medications, appointments, and family members relate
2. **Retrieves connected context** - When you ask about a lab result, it also retrieves related conditions and medications
3. **Maintains privacy** - All data stays local on your machine

## Architecture

```
User Query
    ↓
Query Embedding (Ollama: nomic-embed-text)
    ↓
Vector Similarity Search (Neo4j Vector Index)
    ↓
Graph Traversal (Cypher Queries)
    ↓
Contextual Retrieval (Conditions + Meds + Labs + Appointments)
    ↓
LLM Response Generation (Ollama: llama3.2-vision)
```

## Prerequisites

1. **Docker services running** (Neo4j, PostgreSQL, Redis)
2. **Ollama installed** with required models
3. **Medical documents ingested** into Neo4j

## Setup Steps

### 1. Pull Required Ollama Models

```bash
# Embedding model for semantic search (required for GraphRAG)
ollama pull nomic-embed-text

# Primary LLM (if not already installed)
ollama pull llama3.2-vision:11b
```

**Why nomic-embed-text?**
- Optimized specifically for retrieval tasks
- 768 dimensions (good balance of quality and speed)
- Fast inference on CPU and GPU
- Open-source and privacy-preserving

### 2. Start Docker Services

```bash
cd docker
docker-compose up -d
```

Verify services are running:
```bash
docker-compose ps
```

You should see:
- `mya-view-api` (FastAPI backend)
- `mya-view-neo4j` (Neo4j graph database)
- `mya-view-postgres` (PostgreSQL with pgvector)
- `mya-view-redis` (Redis cache)

### 3. Ingest Medical Documents

If you haven't already, ingest your medical documents into Neo4j:

```bash
source backend/venv/bin/activate
python scripts/ingest_documents.py data/uploads/collin/ --member-id collin-paran-001
```

This creates:
- Person nodes
- LabEvent nodes with summaries
- Condition, Medication, and Appointment nodes
- Relationships connecting everything

### 4. Generate Embeddings for Existing Documents

Run the embedding script to enable vector search:

```bash
source backend/venv/bin/activate
python scripts/embed_documents.py --batch-size 50
```

This will:
- Create a vector index in Neo4j (if it doesn't exist)
- Generate embeddings for all LabEvent summaries
- Store embeddings in the `summary_embedding` property

**Options:**
- `--batch-size N` - Process N documents at a time (default: 50)
- `--force` - Re-embed all documents, even if they already have embeddings

### 5. Restart the API

```bash
cd docker
docker-compose restart api
```

The API will now initialize GraphRAG on startup.

## Usage

### In Chat Interface

GraphRAG is automatically enabled when you chat with Mya. Simply ask questions like:

- "What were my A1C results from last year?"
- "Show me the connection between my cholesterol and liver enzymes"
- "When is my next appointment and what should I discuss?"

The system will:
1. Embed your question
2. Find similar medical events in the graph
3. Retrieve related entities (conditions, meds, appointments)
4. Inject this context into the LLM prompt
5. Generate an informed, specific response

### Direct GraphRAG Search (Python)

```python
from app.services.graphrag import get_graphrag_service

graphrag = get_graphrag_service()
await graphrag.initialize()

# Full search (retrieval + generation)
result = await graphrag.search(
    query="What were my cholesterol levels last year?",
    family_member_id="collin-paran-001",
    top_k=5
)
print(result['answer'])

# Context retrieval only (for custom prompts)
context = await graphrag.get_medical_context(
    query="Tell me about my prediabetes",
    family_member_id="collin-paran-001",
    top_k=3
)
print(context)
```

## How It Works

### Vector Index

GraphRAG creates a vector index on `LabEvent.summary_embedding`:

```cypher
CREATE VECTOR INDEX medical_content_vector
FOR (le:LabEvent)
ON (le.summary_embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }
}
```

### Retrieval Query

When you ask a question, GraphRAG:

1. **Embeds your query** using nomic-embed-text
2. **Finds similar LabEvents** using vector similarity
3. **Enriches with graph traversal**:

```cypher
MATCH (p:Person)-[:HAD_LAB_EVENT]->(node)
OPTIONAL MATCH (p)-[hc:HAS_CONDITION]->(c:Condition)
OPTIONAL MATCH (p)-[:TAKES]->(m:Medication)
OPTIONAL MATCH (node)-[:INCLUDES]->(lr:LabResult)
OPTIONAL MATCH (p)-[:HAS_APPOINTMENT]->(apt:Appointment)
WHERE apt.date >= date() - duration({months: 6})

RETURN
    node.summary,
    conditions,
    lab_results,
    medications,
    upcoming_appointments
```

This gives the LLM rich, connected context instead of isolated facts.

## Configuration

### Adjust Retrieval Settings

Edit `backend/app/services/llm.py`:

```python
rag_context = await graphrag.get_medical_context(
    query=message,
    family_member_id=family_member_id,
    top_k=3  # Increase for more context (may be slower)
)
```

### Change Embedding Model

Edit `backend/app/services/graphrag.py`:

```python
self.embedder = OllamaEmbeddings(
    model="nomic-embed-text",  # Or: mxbai-embed-large, snowflake-arctic-embed
    base_url=settings.OLLAMA_HOST
)
```

Then re-run `embed_documents.py --force` to regenerate embeddings.

### Customize Retrieval Query

Edit the `retrieval_query` in `backend/app/services/graphrag.py` to add:
- More relationships (e.g., FAMILY_HISTORY_OF)
- Time-based filtering
- Specific entity types

## Troubleshooting

### "Model not found: nomic-embed-text"

Pull the model:
```bash
ollama pull nomic-embed-text
```

### "Vector index does not exist"

Run the embedding script to create it:
```bash
python scripts/embed_documents.py
```

### Slow Queries

1. Reduce `top_k` in retrieval settings
2. Add more specific filters to the Cypher query
3. Use a smaller embedding model

### No Context Retrieved

1. Check that documents have summaries:
   ```cypher
   MATCH (le:LabEvent)
   WHERE le.summary IS NOT NULL
   RETURN count(le)
   ```

2. Verify embeddings exist:
   ```cypher
   MATCH (le:LabEvent)
   WHERE le.summary_embedding IS NOT NULL
   RETURN count(le)
   ```

3. Check Neo4j connection in logs

## Performance Tips

1. **Batch embedding** - Use `--batch-size 100` for faster initial setup
2. **GPU acceleration** - Ollama will automatically use your GPU (Apple Silicon, CUDA, etc.)
3. **Cache warm-up** - Run a few test queries to warm up the model cache
4. **Index tuning** - For large datasets (1000+ documents), adjust vector index parameters

## Next Steps

- [ ] Add cross-family member queries (e.g., "Does anyone in my family have diabetes?")
- [ ] Implement consent-based retrieval for sensitive topics
- [ ] Add temporal queries (e.g., "Show trends in my blood sugar over the past year")
- [ ] Create visualization of retrieved graph context

## References

- [neo4j-graphrag-python Documentation](https://neo4j.com/docs/neo4j-graphrag-python/current/)
- [Ollama Embeddings](https://ollama.com/library/nomic-embed-text)
- [Neo4j Vector Search](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)

---

*Last Updated: November 2025*
