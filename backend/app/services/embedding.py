"""
Embedding Service - Generate and manage document embeddings for RAG.
"""

from typing import List, Optional
import structlog
from sentence_transformers import SentenceTransformer
import torch
import asyncio
from functools import lru_cache

from app.config import settings

logger = structlog.get_logger()


class EmbeddingService:
    """
    Service for generating embeddings from text.

    Uses sentence-transformers for local, privacy-preserving embeddings.
    Default model: all-MiniLM-L6-v2 (384 dimensions, fast, good quality)
    Alternative: BAAI/bge-small-en-v1.5 (384 dimensions, better quality)
    Future: BAAI/bge-m3 (1024 dimensions, multilingual, best quality)
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize the embedding service.

        Args:
            model_name: HuggingFace model name (defaults to config or all-MiniLM-L6-v2)
        """
        self.model_name = model_name or getattr(settings, 'EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        self.model: Optional[SentenceTransformer] = None
        self._loading = False

        # Model dimension mapping
        self.model_dimensions = {
            'all-MiniLM-L6-v2': 384,
            'all-MiniLM-L12-v2': 384,
            'BAAI/bge-small-en-v1.5': 384,
            'BAAI/bge-base-en-v1.5': 768,
            'BAAI/bge-m3': 1024,
            'bge-m3': 1024,
        }

    @property
    def dimensions(self) -> int:
        """Get the embedding dimensions for the current model."""
        return self.model_dimensions.get(self.model_name, 384)

    async def initialize(self):
        """Load the embedding model."""
        if self.model is not None or self._loading:
            return

        self._loading = True
        logger.info("Loading embedding model", model=self.model_name)

        try:
            # Load model in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                self._load_model
            )
            logger.info("Embedding model loaded successfully",
                       model=self.model_name,
                       dimensions=self.dimensions)
        except Exception as e:
            logger.error("Failed to load embedding model", error=str(e))
            raise
        finally:
            self._loading = False

    def _load_model(self) -> SentenceTransformer:
        """Load model synchronously (runs in thread pool)."""
        device = self._get_device()
        logger.info("Loading embedding model on device", device=device, model=self.model_name)

        model = SentenceTransformer(self.model_name)
        model.to(device)

        return model

    def _get_device(self) -> str:
        """Determine which device to use for embeddings."""
        if settings.DEVICE != "auto":
            return settings.DEVICE

        # Auto-detect best device
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():  # Apple Silicon
            return "mps"
        else:
            return "cpu"

    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if not text or not text.strip():
            logger.warning("Attempted to embed empty text")
            return [0.0] * self.dimensions

        if self.model is None:
            await self.initialize()

        # Truncate very long texts
        max_length = 512  # Most models support this
        if len(text) > max_length * 4:  # Rough token estimate
            text = text[:max_length * 4]
            logger.debug("Truncated long text for embedding", original_length=len(text))

        try:
            # Run encoding in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self.model.encode(
                    text,
                    convert_to_tensor=False,
                    show_progress_bar=False,
                    normalize_embeddings=True,  # L2 normalize for cosine similarity
                )
            )

            return embedding.tolist()

        except Exception as e:
            logger.error("Failed to generate embedding", error=str(e))
            # Return zero vector as fallback
            return [0.0] * self.dimensions

    async def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for encoding (adjust based on GPU memory)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        if self.model is None:
            await self.initialize()

        # Filter out empty texts but remember their positions
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            logger.warning("No valid texts to embed in batch")
            return [[0.0] * self.dimensions] * len(texts)

        try:
            logger.info("Embedding batch", count=len(valid_texts), batch_size=batch_size)

            # Run batch encoding in thread pool
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: self.model.encode(
                    valid_texts,
                    batch_size=batch_size,
                    convert_to_tensor=False,
                    show_progress_bar=len(valid_texts) > 100,
                    normalize_embeddings=True,
                )
            )

            # Reconstruct full list with zero vectors for empty inputs
            result = [[0.0] * self.dimensions] * len(texts)
            for i, embedding in zip(valid_indices, embeddings):
                result[i] = embedding.tolist()

            return result

        except Exception as e:
            logger.error("Failed to generate batch embeddings", error=str(e))
            return [[0.0] * self.dimensions] * len(texts)

    async def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1, higher is more similar)
        """
        if len(embedding1) != len(embedding2):
            logger.error("Embedding dimension mismatch",
                        dim1=len(embedding1),
                        dim2=len(embedding2))
            return 0.0

        # Cosine similarity (embeddings are already normalized)
        import numpy as np
        return float(np.dot(embedding1, embedding2))


# Global singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
