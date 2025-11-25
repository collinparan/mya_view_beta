-- Medical LLM PostgreSQL Schema
-- Requires pgvector extension

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- FAMILY MEMBERS
-- =============================================================================
CREATE TABLE family_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL,  -- 'parent', 'child', 'grandparent', etc.
    date_of_birth DATE,
    gender VARCHAR(20),
    blood_type VARCHAR(10),

    -- Privacy settings per member
    share_mental_health BOOLEAN DEFAULT FALSE,

    -- LoRA adapter reference
    adapter_name VARCHAR(100),
    adapter_version INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- DOCUMENTS (Medical Records, Lab Results, etc.)
-- =============================================================================
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    family_member_id UUID REFERENCES family_members(id) ON DELETE CASCADE,

    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255),
    mime_type VARCHAR(100),
    file_size_bytes INTEGER,

    document_type VARCHAR(50),  -- 'lab_result', 'prescription', 'medical_record', 'imaging', etc.
    document_date DATE,
    provider_name VARCHAR(255),

    -- OCR/extracted text
    extracted_text TEXT,

    -- Privacy classification
    privacy_category VARCHAR(50) DEFAULT 'auto_share',  -- 'auto_share', 'consent_required', 'member_controlled'

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- DOCUMENT CHUNKS (For RAG)
-- =============================================================================
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    family_member_id UUID REFERENCES family_members(id) ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,

    -- Vector embedding (1024 dimensions for BGE-M3)
    embedding vector(1024),

    -- Metadata for filtering
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for vector similarity search
CREATE INDEX idx_chunks_embedding ON document_chunks
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Index for filtering by family member
CREATE INDEX idx_chunks_family_member ON document_chunks(family_member_id);

-- =============================================================================
-- CHAT HISTORY
-- =============================================================================
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    family_member_id UUID,  -- References Neo4j Person node, no FK constraint

    title VARCHAR(255),
    sort_order INTEGER DEFAULT 0,  -- For drag-and-drop reordering (lower = higher priority)
    is_pinned BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_sessions_sort ON chat_sessions(family_member_id, is_pinned DESC, sort_order, updated_at DESC);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,

    role VARCHAR(20) NOT NULL,  -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,

    -- For vision messages
    has_image BOOLEAN DEFAULT FALSE,
    image_path VARCHAR(500),

    -- Model used for this response
    model_used VARCHAR(100),

    -- RAG context used
    rag_context JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_session ON chat_messages(session_id);

-- =============================================================================
-- AUDIT LOG (For HIPAA-adjacent compliance)
-- =============================================================================
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    action VARCHAR(50) NOT NULL,  -- 'view', 'create', 'update', 'delete', 'query', 'export'
    entity_type VARCHAR(50),      -- 'document', 'chat', 'family_member', etc.
    entity_id UUID,

    family_member_id UUID,        -- Who performed the action

    details JSONB,
    ip_address INET,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_created ON audit_log(created_at);
CREATE INDEX idx_audit_member ON audit_log(family_member_id);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
CREATE TRIGGER update_family_members_updated_at
    BEFORE UPDATE ON family_members
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
