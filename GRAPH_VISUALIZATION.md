# Graph Visualization & GraphRAG Features

## What's Visible in the Graph Explorer

### Current Graph Page (`/graph`)

The existing graph explorer will show **all the same nodes and relationships** as before. GraphRAG doesn't change the graph structure - it just adds properties to existing nodes.

**What You'll See:**

1. **Existing Nodes** (unchanged):
   - `Person` - Family members
   - `LabEvent` - Medical events/lab results
   - `Condition` - Medical conditions
   - `Medication` - Medications
   - `Appointment` - Healthcare appointments
   - `Alias` - Name variations
   - `Provider` - Healthcare providers

2. **Existing Relationships** (unchanged):
   - `HAD_LAB_EVENT` - Person → LabEvent
   - `HAS_CONDITION` - Person → Condition
   - `TAKES` - Person → Medication
   - `HAS_APPOINTMENT` - Person → Appointment
   - `HAS_ALIAS` - Person → Alias
   - `INCLUDES` - LabEvent → LabResult

3. **New Properties** (on LabEvent nodes):
   - `summary_embedding` - Vector array [768 floats]
   - Example: `[0.023, -0.145, 0.891, ...]`

**Note:** The embedding array will show in the property inspector but isn't human-readable (it's just 768 numbers). The magic happens when we use these embeddings for semantic search!

---

## New GraphRAG API Endpoints

I've added new endpoints to visualize **semantic relationships** that aren't explicitly in the graph:

### 1. Find Similar Nodes

**Endpoint:** `GET /api/graphrag/similar/{node_id}?top_k=5`

Finds medical events that are semantically similar, even if not directly connected.

**Example:**
```bash
curl http://localhost:8000/api/graphrag/similar/lab_abc123?top_k=5
```

**Response:**
```json
{
  "source_node_id": "lab_abc123",
  "similar_nodes": [
    {
      "id": "lab_xyz789",
      "labels": ["LabEvent"],
      "properties": {
        "summary": "Follow-up labs show A1C improvement...",
        "date": "2024-10-15"
      },
      "similarity_score": 0.89
    }
  ],
  "count": 5
}
```

**Use Case:** "Show me other lab events similar to this one"

---

### 2. Semantic Search

**Endpoint:** `GET /api/graphrag/semantic-search?query=...&top_k=5`

Search the graph using natural language, finds relevant medical events.

**Example:**
```bash
curl "http://localhost:8000/api/graphrag/semantic-search?query=cholesterol+and+liver+health&top_k=5"
```

**Response:**
```json
{
  "query": "cholesterol and liver health",
  "results": [
    {
      "id": "lab_abc123",
      "summary": "Lipid panel shows elevated LDL, liver enzymes...",
      "date": "2024-11-20",
      "patient_name": "Collin Paran",
      "similarity_score": 0.87,
      "conditions": ["Prediabetes", "Elevated Liver Enzymes"],
      "lab_results": [
        {"test": "LDL", "value": "145", "flag": "high"},
        {"test": "ALT", "value": "52", "flag": "high"}
      ]
    }
  ],
  "count": 1
}
```

**Use Case:** "Find all events related to cholesterol and liver"

---

### 3. Embedding Stats

**Endpoint:** `GET /api/graphrag/embedding-stats`

Check how many documents have been embedded.

**Example:**
```bash
curl http://localhost:8000/api/graphrag/embedding-stats
```

**Response:**
```json
{
  "total_lab_events": 42,
  "with_embeddings": 38,
  "with_summaries": 42,
  "missing_embeddings": 4,
  "embedding_coverage": "90.5%",
  "vector_indexes": 1,
  "vector_index_names": ["medical_content_vector"]
}
```

**Use Case:** "How complete is my embedding coverage?"

---

## Visualizing Semantic Similarity (Future Enhancement)

Want to **see semantic relationships** in the graph UI? Here are some ideas:

### Option 1: Virtual Relationships

Show dotted lines between semantically similar nodes:

```
┌──────────────┐                    ┌──────────────┐
│  Lab Event   │────────────────────│  Lab Event   │
│  Nov 2024    │  HAS_CONDITION     │  Oct 2024    │
│  A1C: 5.8%   │                    │  A1C: 6.0%   │
└──────────────┘                    └──────────────┘
       ║                                   ║
       ║ SEMANTICALLY_SIMILAR (0.89)       ║
       ╚═══════════════════════════════════╝

       (solid line = actual relationship)
       (dashed line = semantic similarity)
```

### Option 2: Similarity Heatmap

Color-code nodes by similarity to a selected node:
- **Dark green** = very similar (0.8+)
- **Light green** = similar (0.6-0.8)
- **Gray** = not similar (<0.6)

### Option 3: Cluster View

Group semantically similar events together:

```
┌─────────────────────────────────────┐
│  Diabetes Management Cluster        │
│  ┌──────┐  ┌──────┐  ┌──────┐      │
│  │ A1C  │  │ A1C  │  │ A1C  │      │
│  │ Nov  │  │ Oct  │  │ Sep  │      │
│  └──────┘  └──────┘  └──────┘      │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Cholesterol Management Cluster     │
│  ┌──────┐  ┌──────┐                │
│  │ Lipid│  │ Lipid│                │
│  │ Panel│  │ Panel│                │
│  └──────┘  └──────┘                │
└─────────────────────────────────────┘
```

---

## Implementation Example

To add semantic similarity visualization to the graph page:

1. **Add a "Show Similar" button** to node inspector
2. **Call the API** when clicked:
   ```javascript
   async function showSimilar(nodeId) {
     const response = await fetch(`/api/graphrag/similar/${nodeId}?top_k=5`);
     const data = await response.json();

     // Draw dotted lines to similar nodes
     data.similar_nodes.forEach(node => {
       drawVirtualEdge(nodeId, node.id, {
         style: 'dashed',
         color: getSimilarityColor(node.similarity_score),
         label: `${(node.similarity_score * 100).toFixed(0)}%`
       });
     });
   }
   ```

3. **Color code by similarity**:
   ```javascript
   function getSimilarityColor(score) {
     if (score > 0.8) return '#5B8A72'; // Dark green
     if (score > 0.6) return '#7BA896'; // Medium green
     return '#B8C9C0';                  // Light green
   }
   ```

---

## Testing the New Features

### 1. Check Embedding Coverage

```bash
curl http://localhost:8000/api/graphrag/embedding-stats
```

If coverage is low, run:
```bash
python scripts/embed_documents.py
```

### 2. Test Semantic Search

```bash
# Search for diabetes-related events
curl "http://localhost:8000/api/graphrag/semantic-search?query=diabetes+blood+sugar&top_k=3"

# Search for specific family member
curl "http://localhost:8000/api/graphrag/semantic-search?query=cholesterol&family_member_id=collin-paran-001"
```

### 3. Find Similar Documents

First, get a node ID from the graph explorer, then:

```bash
curl http://localhost:8000/api/graphrag/similar/lab_abc123?top_k=5
```

---

## Summary

**What's in the Current Graph:**
- ✅ All nodes and relationships (same as before)
- ✅ Embeddings visible as properties
- ✅ Can explore with existing Cypher queries

**New GraphRAG Capabilities:**
- ✅ Semantic similarity search (API endpoint)
- ✅ Natural language graph search (API endpoint)
- ✅ Embedding statistics (API endpoint)
- ⏳ Visual similarity indicators (optional enhancement)

The graph structure is **unchanged** - we just added the ability to find **hidden semantic relationships** that aren't explicit in the graph!

---

*Want me to implement the visual similarity features in the graph UI? Let me know and I can add them!*
