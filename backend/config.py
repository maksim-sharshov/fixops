import os
from typing import Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


class AnalysisConfig(BaseSettings):
    """Конфигурация для анализатора ошибок."""

    EXTRA_IGNORE_DIRS: Tuple[str, ...] = ()
    LOG_TAIL_LINES: int = 50
    REQUIRED_ERROR_KEYS: Tuple[str, ...] = ("file", "function", "line", "error")
    MAX_FIX_ATTEMPTS: int = 3

    # Современный способ задания настроек источника конфигурации
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ANALYSIS_",
        extra="ignore",
        env_file_encoding="utf-8",
    )


class DeepSeekConfig(BaseSettings):
    """Конфигурация для DeepSeek API."""

    TOKEN: str = ''

    model_config = SettingsConfigDict(
        env_prefix="DEEPSEEK_",
        env_file=".env",
        extra="ignore"
    )


class RedisConfig(BaseSettings):
    """Конфигурация для Redis."""

    HOST: str = "localhost"
    PORT: int = 6379
    PASSWORD: str = ""
    NAME: str = "0"  # В Redis имя базы — это число от 0 до 15

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        extra="ignore",
        env_file_encoding="utf-8",
    )

    @property
    def URL(self) -> str:
        # Если пароль есть — формируем URL с ним, если нет — без авторизации
        if self.PASSWORD:
            return f"redis://:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.NAME}"
        return f"redis://{self.HOST}:{self.PORT}/{self.NAME}"


class PostgresConfig(BaseSettings):
    NAME: str
    HOST: str
    PORT: int
    PASSWORD: str
    USER: str

    @property
    def URL(self) -> str:
        return f"postgresql+asyncpg://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.NAME}"

    model_config = SettingsConfigDict(
        env_prefix='POSTGRES_',
        env_file='.env',
        extra='ignore',
    )


class LoggingConfig(BaseSettings):
    """Конфигурация логирования."""
    SERVICE_NAME: str = "fixops"
    ENV: str = "production"
    LOG_DIR: str = "logs"  # Относительный путь к папке логов

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        extra="ignore",
        env_file_encoding="utf-8",
    )


class PathConfig(BaseSettings):
    """Конфигурация путей к проектам."""

    HOST_PROJECTS_ROOT: str = "/home/virtu/projects"
    FIXOPS_PROJECTS_ROOT: str = "/projects"

    model_config = SettingsConfigDict(
        env_prefix="PATH_",
        env_file=".env",
        extra="ignore",
        env_file_encoding="utf-8",
    )


class Settings:
    paths = PathConfig()
    analysis = AnalysisConfig()
    deepseek = DeepSeekConfig()
    redis = RedisConfig()
    postgres = PostgresConfig()
    logging = LoggingConfig()


settings = Settings()
