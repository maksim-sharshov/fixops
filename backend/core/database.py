from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(
    url=settings.postgres.URL,
    # echo=True,
    pool_size=5,
    max_overflow=10
)

async_db_session = async_sessionmaker(engine)


class Base(DeclarativeBase):
    pass
