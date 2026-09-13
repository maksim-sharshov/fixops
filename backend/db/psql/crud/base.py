from typing import Any, Type

from pydantic import BaseModel

from core.database import async_db_session, engine, Base
from core.logging import app_logger as logger
import db.psql.models.models  # noqa: F401  # регистрирует таблицы в Base.metadata


async def create_tables() -> bool:
    """
        Create all tables in the core
    :return: True or False
    """
    async with async_db_session() as s:
        try:
            # await s.run_sync(
            #     lambda s_value: Base.metadata.drop_all(
            #         bind=s_value.bind
            #     )
            # )

            await s.run_sync(
                lambda s_value: Base.metadata.create_all(
                    bind=s_value.bind
                )
            )

            return True

        except Exception as e:
            logger.exception(e)
            return False


async def close_connections() -> bool:
    """
        Close pool of db connections
    :return: True or False
    """
    async with async_db_session() as s:
        try:
            await engine.dispose()

            return True

        except Exception as e:
            logger.exception(e)
            return False


async def to_pydantic(pydantic_class: Type[BaseModel], data: Any, to_json: bool = False) -> list[BaseModel] | list[dict]:
    """
        Making pydantic class or json from SQLAlchemy table data
    :param pydantic_class: subclass of Pydantic BaseModel
    :param data: result of select() SQLAlchemy request
    :param to_json: make from tabel data json or not
    :return: pydantic model or dict
    """
    if not issubclass(pydantic_class, BaseModel):
        raise ValueError("pydantic_class must be a subclass of BaseModel")

    try:
        if not to_json:
            result = [
                pydantic_class.model_validate(row, from_attributes=True)
                for row in data
            ]

        else:
            result = [
                pydantic_class.model_validate(row, from_attributes=True).model_dump_json()
                for row in data
            ]

        return result

    except Exception as e:
        logger.exception(e)
        raise e
