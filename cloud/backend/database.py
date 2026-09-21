"""
cloud/backend/database.py
SQLAlchemy database session and connection setup for SQLite.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cloud.backend.models import Base

DB_PATH = os.environ.get("DB_PATH", "cloud_backend.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
