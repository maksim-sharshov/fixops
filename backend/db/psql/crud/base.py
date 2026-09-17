from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

import db.psql.models.models  # noqa: F401  # регистрирует таблицы в Base.metadata
from core.database import Base, async_db_session, engine
from core.logging import app_logger as logger


async def _add_missing_columns(session) -> None:
    """
    Догоняет схему: create_all создаёт только отсутствующие таблицы и не
    меняет существующие. Здесь добавляются колонки, которые появились в
    моделях после того, как таблица уже была создана.

    Автоматически добавляются только nullable-колонки (и/или с server_default).
    NOT NULL без default требует ручной миграции — по ним пишется warning.
    """
    result = await session.execute(
        text(
            "SELECT table_name, column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        )
    )

    existing: dict[str, set[str]] = {}
    for table_name, column_name in result.all():
        existing.setdefault(table_name, set()).add(column_name)

    dialect = engine.sync_engine.dialect

    for table in Base.metadata.sorted_tables:
        present = existing.get(table.name, set())

        for column in table.columns:
            if column.name in present:
                continue

            if (
                not column.nullable
                and column.server_default is None
                and column.default is None
            ):
                logger.warning(
                    "Column {}.{} is NOT NULL without default — "
                    "add it manually",
                    table.name,
                    column.name,
                )
                continue

            ddl = (
                f'ALTER TABLE "{table.name}" '
                f'ADD COLUMN IF NOT EXISTS "{column.name}" '
                f"{column.type.compile(dialect=dialect)}"
            )

            server_default = column.server_default
            default_arg = getattr(server_default, "arg", None)
            if default_arg is not None and hasattr(default_arg, "text"):
                ddl += f" DEFAULT {default_arg.text}"

            try:
                await session.execute(text(ddl))
                logger.info(
                    "Added missing column {}.{}",
                    table.name,
                    column.name,
                )
            except Exception as e:
                logger.exception(
                    "Failed to add column {}.{}: {}",
                    table.name,
                    column.name,
                    e,
                )


async def create_tables() -> bool:
    """
        Create all tables in the core and sync missing columns
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

            await _add_missing_columns(s)

            await s.commit()

            return True

        except Exception as e:
            logger.exception(e)
            return False


async def close_connections() -> bool:
    """
        Close pool of db connections
    :return: True or False
    """
    async with async_db_session():
        try:
            await engine.dispose()

            return True

        except Exception as e:
            logger.exception(e)
            return False


async def to_pydantic(pydantic_class: type[BaseModel], data: Any, to_json: bool = False) -> list[BaseModel] | list[dict]:
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
