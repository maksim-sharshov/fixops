from typing import TypeVar, Generic, Sequence
from datetime import datetime

from sqlalchemy.exc import NoResultFound
from sqlalchemy import Integer, Text, JSON, DateTime
from sqlalchemy.sql import select, update as sqlalchemy_update
from sqlalchemy.orm import Mapped, selectinload, load_only, mapped_column

from core.database import async_db_session, Base

from db.psql.models.enum import *
from db.psql.models.mapped_columns import *


T = TypeVar("T")


class ModelAdmin(Generic[T]):

    class DoesNotExists(Exception):
        pass

    @classmethod
    async def create(cls, **kwargs) -> T:
        """
        # Создает новый объект и возвращает его.
        :param kwargs: Поля и значения для объекта.
        :return: Созданный объект.
        """

        async with async_db_session() as session:
            obj = cls(**kwargs)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj

    @classmethod
    async def add(cls, **kwargs) -> None:
        """
        # Создает новый объект.
        :param kwargs: Поля и значения для объекта.
        """

        async with async_db_session() as session:
            session.add(cls(**kwargs))
            await session.commit()

    async def update(self, **kwargs) -> None:
        """
        # Обновляет текущий объект.
        :param kwargs: Поля и значения, которые надо поменять.
        """

        async with async_db_session() as session:
            await session.execute(
                sqlalchemy_update(self.__class__), [{"id": self.id, **kwargs}]
            )
            await session.commit()

    async def delete(self) -> None:
        """
        # Удаляет объект.
        """
        async with async_db_session() as session:
            await session.delete(self)
            await session.commit()

    @classmethod
    async def get(cls, select_in_load: str | None = None, **kwargs) -> T | None:
        """
        # Возвращает одну запись, которая удовлетворяет введенным параметрам.

        :param select_in_load: Загрузить сразу связанную модель.
        :param kwargs: Поля и значения.
        :return: Объект или None если не найдено.
        """

        params = [getattr(cls, key) == val for key, val in kwargs.items()]
        query = select(cls).where(*params)

        if select_in_load:
            query.options(selectinload(getattr(cls, select_in_load)))

        try:
            async with async_db_session() as session:
                results = await session.execute(query)
                (result,) = results.one()
                return result
        except NoResultFound:
            return None

    @classmethod
    async def filter(cls, select_in_load: str | None = None, **kwargs) -> Sequence[T]:
        """
        # Возвращает все записи, которые удовлетворяют фильтру.

        :param select_in_load: Загрузить сразу связанную модель.
        :param kwargs: Поля и значения.
        :return: Перечень записей.
        """

        params = [getattr(cls, key) == val for key, val in kwargs.items()]
        query = select(cls).where(*params)

        if select_in_load:
            query.options(selectinload(getattr(cls, select_in_load)))

        try:
            async with async_db_session() as session:
                results = await session.execute(query)
                return results.scalars().all()
        except NoResultFound:
            return ()

    @classmethod
    async def all(
            cls, select_in_load: str = None, values: list[str] = None
    ) -> Sequence[T]:
        """
        # Получает все записи.

        :param select_in_load: Загрузить сразу связанную модель.
        :param values: Список полей, которые надо вернуть, если нет, то все (default None).
        """

        if values and isinstance(values, list):
            # Определенные поля
            values = [getattr(cls, val) for val in values if isinstance(val, str)]
            query = select(cls).options(load_only(*values))
        else:
            # Все поля
            query = select(cls)

        if select_in_load:
            query.options(selectinload(getattr(cls, select_in_load)))

        async with async_db_session() as session:
            result = await session.execute(query)
            return result.scalars().all()


class IncidentResult(Base, ModelAdmin):

    __tablename__ = 'incident_results'

    id: Mapped[intpk]

    job_id: Mapped[str] = mapped_column(
        index=True,
        unique=True,
        comment='ID задачи'
    )

    container_id: Mapped[str | None] = mapped_column(
        comment='ID Docker-контейнера'
    )
    container_name: Mapped[str | None] = mapped_column(
        comment='Имя Docker-контейнера'
    )
    project: Mapped[str | None] = mapped_column(
        comment='Название проекта'
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        comment='Сообщение об ошибке'
    )
    error_location: Mapped[str | None] = mapped_column(
        Text,
        comment='Местоположение ошибки'
    )

    status: Mapped[str] = mapped_column(
        comment='Статус инцидента'
    )

    steps: Mapped[list | None] = mapped_column(
        JSON,
        comment='Шаги выполнения workflow'
    )

    llm_prompt: Mapped[str | None] = mapped_column(
        Text,
        comment='Промпт для LLM'
    )
    ai_context: Mapped[str | None] = mapped_column(
        Text,
        comment='Контекст, переданный AI'
    )

    fixed_file: Mapped[str | None] = mapped_column(
        Text,
        comment='Исправленный файл'
    )
    fix_diff: Mapped[str | None] = mapped_column(
        Text,
        comment='Diff применённого исправления'
    )

    tests_passed: Mapped[bool | None] = mapped_column(
        comment='Пройдены ли тесты'
    )
    test_return_code: Mapped[int | None] = mapped_column(
        Integer,
        comment='Код возврата тестов'
    )
    test_result_type: Mapped[str | None] = mapped_column(
        comment='Тип результата тестирования'
    )
    reproduction_passed: Mapped[bool | None] = mapped_column(
        comment='Успешно ли воспроизведена ошибка'
    )
    test_stdout: Mapped[str | None] = mapped_column(
        Text,
        comment='Стандартный вывод тестов'
    )
    test_stderr: Mapped[str | None] = mapped_column(
        Text,
        comment='Ошибки тестов'
    )
    generated_tests: Mapped[list | None] = mapped_column(
        JSON,
        comment='Сгенерированные тесты'
    )

    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment='Когда исправление было применено'
    )
    apply_output: Mapped[str | None] = mapped_column(
        Text,
        comment='Вывод применения исправления'
    )
    rolled_back_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment='Когда исправление было откатано'
    )

    created_at: Mapped[created_at]
