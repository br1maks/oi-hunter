import os
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base
DATA_DIR = Path(__file__).parent.parent.parent / 'data'
DB_PATH = DATA_DIR / 'oi_hunter.db'

class DatabaseManager:
    _instance = None
    _engine = None
    _session_factory = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db_url = f'sqlite:///{DB_PATH}'
        self._engine = create_engine(db_url, echo=False, pool_pre_ping=True, connect_args={'check_same_thread': False})
        self._session_factory = sessionmaker(bind=self._engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(self._engine)
        self._initialized = True

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self) -> Session:
        return self._session_factory()

    @property
    def engine(self):
        return self._engine

    @property
    def db_path(self) -> Path:
        return DB_PATH

    def close(self):
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False
            DatabaseManager._instance = None

def get_database() -> DatabaseManager:
    return DatabaseManager()