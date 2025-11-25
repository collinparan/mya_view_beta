"""
Application configuration using Pydantic Settings.
"""

from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database - PostgreSQL
    POSTGRES_USER: str = "mya_view"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_DB: str = "mya_view"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Database - Neo4j
    NEO4J_AUTH: str = "neo4j/changeme"
    NEO4J_HOST: str = "localhost"
    NEO4J_BOLT_PORT: int = 7687
    NEO4J_HTTP_PORT: int = 7474

    # Ollama
    OLLAMA_HOST: str = "http://localhost:11434"

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = True
    LOG_LEVEL: str = "INFO"

    # Security
    SECRET_KEY: str = "changeme_generate_secure_key"
    SESSION_TIMEOUT: int = 60  # minutes

    # Model Configuration
    PRIMARY_VLM: str = "llama3.2-vision:11b"
    MEDICAL_TEXT_MODEL: str = "llama3.2-vision:11b"
    COORDINATOR_MODEL: str = "llama3.2-vision:11b"
    EMBEDDING_MODEL: str = "bge-m3"

    # Privacy
    CONSENT_REQUIRED_CATEGORIES: str = "sexual_health,reproductive,std_history"

    # Hardware
    DEVICE: str = "auto"  # auto, cuda, mps, cpu
    MAX_CONCURRENT_INFERENCE: int = 2

    @property
    def postgres_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def neo4j_url(self) -> str:
        """Construct Neo4j connection URL."""
        return f"bolt://{self.NEO4J_HOST}:{self.NEO4J_BOLT_PORT}"

    @property
    def neo4j_credentials(self) -> tuple:
        """Parse Neo4j credentials."""
        parts = self.NEO4J_AUTH.split("/")
        return (parts[0], parts[1]) if len(parts) == 2 else ("neo4j", "neo4j")

    @property
    def consent_categories(self) -> List[str]:
        """Parse consent required categories."""
        return [c.strip() for c in self.CONSENT_REQUIRED_CATEGORIES.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars not defined in Settings


# Global settings instance
settings = Settings()
