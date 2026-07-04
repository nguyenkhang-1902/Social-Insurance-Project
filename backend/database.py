from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "app.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    try:
        from .models import Base
    except ImportError:
        from models import Base

    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        existing_columns = conn.execute(text("PRAGMA table_info(payroll_history)")).fetchall()
        column_names = {row[1] for row in existing_columns}
        if "resign_date" not in column_names:
            conn.execute(text("ALTER TABLE payroll_history ADD COLUMN resign_date DATE"))
