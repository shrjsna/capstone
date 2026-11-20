"""
cloud/backend/database.py
=========================
SQLAlchemy database session, connection setup, and schema migration for SQLite.
Enforces WAL mode, foreign key checks, and append-only database triggers for audit logs.
"""

import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from cloud.backend.models import Base

DB_PATH = os.environ.get("DB_PATH", "cloud_backend.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Idempotently initialize all ORM tables, triggers, and indices.
    Safe on existing databases with pre-existing alerts.
    """
    Base.metadata.create_all(bind=engine)

    # SQLite specific triggers and constraints for strict RBAC compliance
    with engine.begin() as conn:
        # 1. Audit log append-only triggers
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE rejected');
            END;
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only: DELETE rejected');
            END;
        """))

        # 2. Case-insensitive index for users.username if not collated
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_users_username_nocase
            ON users(username COLLATE NOCASE);
        """))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
