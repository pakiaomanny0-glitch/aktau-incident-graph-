import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Railway PostgreSQL: DATABASE_URL env var автоматты түрде беріледі.
# Локалды тестілеу үшін .env-ге DATABASE_URL қойыңыз (немесе fallback SQLite).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_dev.db")

# Railway кейде "postgres://" қайтарады, SQLAlchemy 2.x "postgresql://" талап етеді
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
