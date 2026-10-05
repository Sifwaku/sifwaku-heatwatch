"""
Database engine and session factory.
"""
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.database.models import Base

_settings = get_settings()
# SQLite needs check_same_thread=False for FastAPI
connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("weather_observations")}
    if "temperature_min_c" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE weather_observations ADD COLUMN temperature_min_c FLOAT"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
