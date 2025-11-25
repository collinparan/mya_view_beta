#!/usr/bin/env python3
"""
Embed Existing Medical Documents

This script generates embeddings for existing LabEvent summaries in Neo4j
to enable GraphRAG semantic search.

Usage:
    python scripts/embed_documents.py [--batch-size 50] [--force]

Options:
    --batch-size    Number of documents to process per batch (default: 50)
    --force         Re-embed all documents, even if they already have embeddings
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.graphrag import get_graphrag_service
import structlog

logger = structlog.get_logger()


async def embed_all_documents(batch_size: int = 50, force: bool = False):
    """
    Embed all medical documents in the Neo4j graph.

    Args:
        batch_size: Number of documents to process at once
        force: If True, re-embed all documents
    """
    logger.info("Starting document embedding", batch_size=batch_size, force=force)

    try:
        # Get GraphRAG service
        graphrag = get_graphrag_service()
        await graphrag.initialize()

        # Count total documents
        async with graphrag.driver.session() as session:
            if force:
                result = await session.run("""
                    MATCH (le:LabEvent)
                    WHERE le.summary IS NOT NULL
                    RETURN count(le) as total
                """)
            else:
                result = await session.run("""
                    MATCH (le:LabEvent)
                    WHERE le.summary IS NOT NULL
                    AND le.summary_embedding IS NULL
                    RETURN count(le) as total
                """)

            record = await result.single()
            total = record['total'] if record else 0

        logger.info(f"Found {total} documents to embed")

        if total == 0:
            logger.info("No documents need embedding")
            return

        # Process in batches
        processed = 0
        while processed < total:
            logger.info(f"Processing batch {processed // batch_size + 1}",
                       progress=f"{processed}/{total}")

            # Clear embeddings if force mode
            if force:
                async with graphrag.driver.session() as session:
                    await session.run("""
                        MATCH (le:LabEvent)
                        WHERE le.summary IS NOT NULL
                        REMOVE le.summary_embedding
                        WITH le LIMIT $batch_size
                        RETURN count(le) as cleared
                    """, {"batch_size": batch_size})

            # Embed batch
            await graphrag.embed_existing_documents(batch_size=batch_size)
            processed += batch_size

            # Brief pause to avoid overwhelming the system
            await asyncio.sleep(0.5)

        logger.info("Document embedding complete!", total_processed=total)

        # Close connection
        await graphrag.close()

    except Exception as e:
        logger.error("Document embedding failed", error=str(e))
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Embed existing medical documents for GraphRAG"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of documents to process per batch (default: 50)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed all documents, even if they already have embeddings"
    )

    args = parser.parse_args()

    # Run async function
    asyncio.run(embed_all_documents(
        batch_size=args.batch_size,
        force=args.force
    ))


if __name__ == "__main__":
    main()
