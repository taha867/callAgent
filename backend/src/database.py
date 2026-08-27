from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(str(settings.DATABASE_URL), echo=settings.DEBUG, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """For non-request contexts — Temporal activities, scripts/seed_demo_data.py — that
    need a session without going through FastAPI's Depends() machinery."""
    return SessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
