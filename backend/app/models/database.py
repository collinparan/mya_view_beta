"""
Database connection management for PostgreSQL and Neo4j.
"""

from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from neo4j import AsyncGraphDatabase, AsyncDriver
import structlog

from app.config import settings

logger = structlog.get_logger()

# =============================================================================
# SQLAlchemy (PostgreSQL)
# =============================================================================

Base = declarative_base()

# Async engine
engine = create_async_engine(
    settings.postgres_url,
    echo=settings.LOG_LEVEL == "DEBUG",
    pool_size=5,
    max_overflow=10,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# =============================================================================
# Neo4j
# =============================================================================

_neo4j_driver: Optional[AsyncDriver] = None


async def get_neo4j_driver() -> AsyncDriver:
    """Get or create Neo4j driver."""
    global _neo4j_driver
    if _neo4j_driver is None:
        user, password = settings.neo4j_credentials
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_url,
            auth=(user, password),
        )
    return _neo4j_driver


@asynccontextmanager
async def neo4j_session():
    """Context manager for Neo4j sessions."""
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        yield session


async def run_cypher(query: str, parameters: dict = None):
    """Execute a Cypher query and return results."""
    async with neo4j_session() as session:
        result = await session.run(query, parameters or {})
        return [record.data() async for record in result]


# =============================================================================
# Initialization
# =============================================================================

async def init_db():
    """Initialize database connections."""
    logger.info("Initializing database connections")

    # Test PostgreSQL connection
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection successful")
    except Exception as e:
        logger.error("PostgreSQL connection failed", error=str(e))
        raise

    # Test Neo4j connection
    try:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            await session.run("RETURN 1")
        logger.info("Neo4j connection successful")
    except Exception as e:
        logger.error("Neo4j connection failed", error=str(e))
        # Don't raise - Neo4j might not be required for all operations


async def close_db():
    """Close database connections."""
    global _neo4j_driver

    # Close SQLAlchemy engine
    await engine.dispose()
    logger.info("PostgreSQL connection closed")

    # Close Neo4j driver
    if _neo4j_driver:
        await _neo4j_driver.close()
        _neo4j_driver = None
        logger.info("Neo4j connection closed")
