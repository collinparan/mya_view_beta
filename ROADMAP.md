# Mya View - Product Development Roadmap

> A private, local health companion that helps your family prepare for doctor visits, track conditions and medications, and ask better questions during appointments.

**What Mya View IS:**
- A warm, caring health companion that recalls dates, symptoms, and specifics
- A preparation tool for more thorough doctor conversations
- A document reader for prescriptions and lab results
- A family health history tracker with appointment awareness

**What Mya View is NOT:**
- A replacement for medical professionals
- A diagnostic tool
- A treatment recommender

---

## Current Status: GraphRAG-Enhanced MVP Complete

Mya View has achieved a functional MVP with GraphRAG capabilities:
- Chat interface with streaming responses
- **GraphRAG semantic search** - Context-aware responses using Neo4j + embeddings
- Vision/camera analysis for medical documents
- Voice interaction mode
- Family member profiles with Neo4j graph storage
- Document ingestion (Markdown, text, PDF) with automatic embedding
- Appointment tracking
- Medical checkpoint export
- Graph database explorer with semantic similarity API

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Browser)                              │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │   Chat    │  │   Voice   │  │  Stream   │  │   Graph   │  │ Settings  │ │
│  │ index.html│  │ voice.html│  │camera.html│  │graph.html │  │settings.  │ │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └───────────┘ │
│        └──────────────┴──────────────┴──────────────┘                       │
│                              WebSocket/REST API                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
┌──────────────────────────────────────┼──────────────────────────────────────┐
│                                      ▼                                       │
│                           ┌─────────────────┐                               │
│                           │   FastAPI App   │                               │
│                           │   (Port 8000)   │                               │
│                           └────────┬────────┘                               │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐            │
│         │                          │                          │            │
│         ▼                          ▼                          ▼            │
│  ┌──────────────┐          ┌──────────────┐          ┌──────────────┐      │
│  │ LLM Service  │          │Graph Service │          │  Ingestion   │      │
│  │  (Ollama)    │          │   (Neo4j)    │          │   Service    │      │
│  └──────┬───────┘          └──────┬───────┘          └──────┬───────┘      │
│         │                         │                          │              │
│         ▼                         ▼                          ▼              │
│  ┌─────────────┐           ┌───────────┐            ┌─────────────┐        │
│  │   Ollama    │           │   Neo4j   │            │ PostgreSQL  │        │
│  │  (Host)     │           │  :7688    │            │  + pgvector │        │
│  │  :11434     │           │           │            │    :5432    │        │
│  └─────────────┘           └───────────┘            └─────────────┘        │
│                                                                             │
│                         BACKEND (Docker Network)                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Development Phases

### Phase 1: Foundation ✅ COMPLETE
- [x] Project directory structure (`frontend/`, `backend/`, `docker/`, `data/`, `scripts/`)
- [x] Git repository with `.gitignore`
- [x] `requirements.txt` with all dependencies
- [x] Docker infrastructure
  - [x] `docker-compose.yml` with all services
  - [x] PostgreSQL with PGVector extension
  - [x] Neo4j container
  - [x] Volume mounts for persistent data
  - [x] `.env.example` configuration
- [x] Basic FastAPI scaffold
  - [x] Main application entry point (`main.py`)
  - [x] WebSocket endpoint for streaming (`/ws/chat`)
  - [x] Health check endpoint (`/health`)
  - [x] CORS and middleware
- [x] Database schemas
  - [x] Neo4j: Person, Condition, Medication, Appointment, Alias, Location, etc.

### Phase 2: Core Chat Interface ✅ COMPLETE
- [x] Frontend - `index.html`
  - [x] Responsive layout with collapsible sidebar
  - [x] Chat message container with streaming support
  - [x] Input area with send button
  - [x] Family member selector dropdown
  - [x] Dark/light theme toggle
  - [x] Welcome message with feature cards
- [x] Frontend - `app.js`
  - [x] WebSocket connection manager with reconnect
  - [x] Message rendering with markdown support
  - [x] Streaming text handler (token-by-token)
  - [x] Local storage for session persistence
  - [x] Error handling and loading states
- [x] LLM Integration
  - [x] Ollama client for local models
  - [x] Model routing (vision vs text)
  - [x] System prompt with Mya personality
  - [x] Response streaming via WebSocket
  - [x] Family member context injection from Neo4j

### Phase 3: Vision Module ✅ COMPLETE
- [x] Vision Backend
  - [x] VLM model integration (llama3.2-vision:11b)
  - [x] Frame capture endpoint for live camera
  - [x] Image upload endpoint
  - [x] Base64 image handling
- [x] Vision Frontend (`camera.html`)
  - [x] Camera access with preview
  - [x] Image upload with drag-and-drop
  - [x] Real-time streaming analysis
  - [x] Results display in message format
- [x] Medical Vision Features
  - [x] Prescription text extraction
  - [x] Lab result interpretation
  - [x] Medical document analysis

### Phase 4: Voice Interface ✅ COMPLETE
- [x] Voice Frontend (`voice.html`)
  - [x] Web Speech API integration
  - [x] Push-to-talk microphone button
  - [x] Real-time transcription display
  - [x] Text-to-speech response playback
  - [x] Visual feedback during recording

### Phase 5: Data Management ✅ COMPLETE
- [x] Document Ingestion (`scripts/ingest_documents.py`)
  - [x] Markdown/text file parsing
  - [x] PDF text extraction (pypdf)
  - [x] Lab result extraction
  - [x] Condition identification
  - [x] Appointment parsing
  - [x] Neo4j graph population
- [x] Data Export (`scripts/export_checkpoint.py`)
  - [x] Medical checkpoint generation
  - [x] Human-readable markdown format
  - [x] Personal info, conditions, medications
  - [x] Recent appointments (past year)
  - [x] Healthcare providers & insurance
  - [x] Lab results history
- [x] Graph Explorer (`graph.html`)
  - [x] Interactive canvas visualization
  - [x] Node/edge exploration
  - [x] Cypher query interface
  - [x] Query templates

### Phase 6: Settings & Customization ✅ COMPLETE
- [x] Settings page (`settings.html`)
  - [x] Theme toggle (light/dark)
  - [x] Model selection
  - [x] Server URL configuration
  - [x] Settings persistence

---

## Upcoming Features

### Phase 7: GraphRAG Pipeline ✅ COMPLETE
- [x] **P7.1** Neo4j GraphRAG Integration
  - [x] Installed neo4j-graphrag-python with Ollama support
  - [x] Vector index on medical document summaries
  - [x] Ollama embeddings (nomic-embed-text)
- [x] **P7.2** Hybrid Retrieval
  - [x] Vector similarity search on LabEvent summaries
  - [x] Graph traversal for related entities (conditions, meds, appointments)
  - [x] Custom Cypher queries for medical context
- [x] **P7.3** Context Injection
  - [x] Automatic context retrieval in chat flow
  - [x] Relevant medical history injection
  - [x] Document embedding script for existing data

### Phase 8: Enhanced Family Features
- [ ] **P8.1** Family Profiles UI
  - [ ] Create/edit family member profiles in-app
  - [ ] Allergies and contraindications
  - [ ] Emergency contact information
- [ ] **P8.2** Cross-Member Queries
  - [ ] Hereditary condition awareness
  - [ ] Family history summaries
  - [ ] Privacy controls for sensitive data
- [x] **P8.3** Health Timeline ✅
  - [x] Chronological event display with filtering
  - [x] Medication tracking timeline
  - [x] Appointment history visualization
  - [x] Lab events, conditions, procedures
  - [x] Export to CSV functionality
  - [x] Print-friendly view
  - [x] Date range and event type filters
  - [x] Stats dashboard

### Phase 9: Advanced Intelligence
- [ ] **P9.1** Multi-Model Routing
  - [ ] Query classification
  - [ ] Route to optimal model per query type
  - [ ] Medical text specialist model
- [ ] **P9.2** Per-Member Personalization
  - [ ] LoRA adapters per family member
  - [ ] Personalized response style
  - [ ] Individual medical vocabulary
- [ ] **P9.3** Proactive Insights
  - [ ] Medication interaction alerts
  - [ ] Preventive care reminders
  - [ ] Follow-up tracking

### Phase 10: Security & Privacy
- [ ] **P10.1** Data Protection
  - [ ] AES-256 encryption at rest
  - [ ] Secure backup/restore
  - [ ] Data export formats (FHIR)
- [ ] **P10.2** Access Control
  - [ ] PIN/password authentication
  - [ ] Session timeout
  - [ ] Audit logging

---

## Technical Stack

### Current Implementation

| Component | Technology | Status |
|-----------|------------|--------|
| **Frontend** | HTML/CSS/JS (vanilla) | ✅ Complete |
| **Backend** | FastAPI (Python 3.11+) | ✅ Complete |
| **LLM** | Ollama + llama3.2-vision:11b | ✅ Complete |
| **Graph DB** | Neo4j 5.x Community | ✅ Complete |
| **Vector DB** | PostgreSQL + pgvector | 🔄 Configured |
| **Cache** | Redis | 🔄 Configured |

### Models

| Model | Size | Purpose | Status |
|-------|------|---------|--------|
| llama3.2-vision:11b | 6.4GB | Primary VLM (chat + vision) | ✅ Active |
| nomic-embed-text | 274MB | Semantic embeddings (GraphRAG) | ✅ Active |
| OpenBioLLM 8B | 4.7GB | Medical text specialist | 📋 Planned |

### Docker Services

```yaml
services:
  api:       # FastAPI backend (port 8000)
  postgres:  # PostgreSQL 16 + pgvector (port 5432)
  neo4j:     # Neo4j 5.x (ports 7475, 7688)
  redis:     # Redis 7 (port 6379)
```

---

## File Structure

```
mya_view/
├── backend/
│   ├── app/
│   │   ├── config.py           # Environment configuration
│   │   ├── routers/
│   │   │   ├── chat.py         # Chat WebSocket
│   │   │   ├── vision.py       # Vision endpoints
│   │   │   ├── family.py       # Family member API
│   │   │   ├── graph.py        # Graph explorer API
│   │   │   ├── graph_rag.py    # GraphRAG semantic search API
│   │   │   ├── timeline.py     # Health timeline API
│   │   │   └── settings.py     # Settings API
│   │   └── services/
│   │       ├── llm.py          # Ollama LLM integration
│   │       ├── graphrag.py     # GraphRAG service
│   │       ├── embedding.py    # Embedding generation
│   │       └── ingestion.py    # Document parsing
│   ├── static/                 # Deployed frontend
│   ├── main.py                 # FastAPI entry point
│   └── requirements.txt
├── frontend/
│   ├── index.html              # Main chat interface
│   ├── voice.html              # Voice assistant
│   ├── camera.html             # Live vision streaming
│   ├── graph.html              # Graph database explorer
│   ├── timeline.html           # Health timeline
│   ├── settings.html           # App settings
│   └── app.js                  # Shared JavaScript
├── docker/
│   ├── docker-compose.yml
│   └── init-scripts/
├── scripts/
│   ├── ingest_documents.py     # Document ingestion into Neo4j
│   ├── embed_documents.py      # Generate embeddings for GraphRAG
│   └── export_checkpoint.py    # Data export
├── data/
│   ├── uploads/                # User documents
│   └── checkpoints/            # Exported checkpoints
├── AI_Health_Scribe_Aesthetic_Guide.md  # Design system
├── README.md
├── ROADMAP.md
├── GRAPHRAG_SETUP.md           # GraphRAG setup guide
├── GRAPH_VISUALIZATION.md      # Graph features documentation
├── LICENSE                     # Apache 2.0
└── NOTICE                      # Attribution
```

---

## Milestones

| Milestone | Status | Description |
|-----------|--------|-------------|
| M1: Infrastructure | ✅ Complete | Docker, databases, basic API |
| M2: Chat MVP | ✅ Complete | Streaming chat with Mya personality |
| M3: Vision | ✅ Complete | Camera/image analysis |
| M4: Voice | ✅ Complete | Speech-to-text interaction |
| M5: Data Ingestion | ✅ Complete | PDF/document parsing, Neo4j storage |
| M6: Graph Explorer | ✅ Complete | Visual database exploration |
| M7: Checkpoints | ✅ Complete | Medical data export |
| M8: GraphRAG | ✅ Complete | Neo4j GraphRAG, semantic search, context injection |
| M9: Health Timeline | ✅ Complete | Chronological health events, export, filtering |
| M10: Family UI | 📋 Planned | In-app profile management |
| M11: Security | 📋 Planned | Encryption, authentication |

---

## Design Principles

See [AI_Health_Scribe_Aesthetic_Guide.md](./AI_Health_Scribe_Aesthetic_Guide.md) for complete design system.

### Key Design Values
- **Warm, not clinical** - Sage green accent, DM Sans typography
- **Calming, not alarming** - Soft coral errors, breathing animations
- **Private, not paranoid** - Reassuring privacy messaging
- **Helpful, not diagnostic** - Always encourage professional consultation

---

## Quick Start

```bash
# 1. Pull required models
ollama pull llama3.2-vision:11b
ollama pull nomic-embed-text  # For GraphRAG semantic search

# 2. Start services
cd docker && docker-compose up -d

# 3. Ingest documents (optional)
source backend/venv/bin/activate
python scripts/ingest_documents.py data/uploads/collin/ --member-id collin-paran-001

# 4. Generate embeddings for GraphRAG (optional)
python scripts/embed_documents.py

# 5. Open app
open http://localhost:8000
```

**For complete GraphRAG setup:** See [GRAPHRAG_SETUP.md](./GRAPHRAG_SETUP.md)

---

## Contributing

This is a personal health project. If you fork it:
1. Follow the design system guidelines
2. Keep all data local (no cloud services)
3. Maintain the warm, supportive tone
4. Never add diagnostic or treatment features

---

*Last Updated: November 2025*
