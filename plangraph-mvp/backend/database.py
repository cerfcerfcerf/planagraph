from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DB_DEFAULT_PATH = "plangraph.db"


def get_db_url() -> str:
    env_path = os.getenv("DB_PATH", DB_DEFAULT_PATH)
    if env_path.startswith("sqlite://"):
        return env_path
    if os.path.isabs(env_path):
        return f"sqlite:///{env_path}"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return f"sqlite:///{os.path.join(base_dir, env_path)}"


engine = create_engine(
    get_db_url(),
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)
