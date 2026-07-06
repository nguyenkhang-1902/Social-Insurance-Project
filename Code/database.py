import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "Data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "app.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
BACKUP_DIR = DATA_DIR / "backups"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def backup_database_file(db_path: Path = DATABASE_PATH, backup_dir: Path = BACKUP_DIR) -> Optional[Path]:
    """Snapshot the current DB file before any destructive operation.

    Returns the backup path, or None if there was no existing DB file to back up
    (e.g. very first run). Never raises on a missing source file -- only a real
    copy failure should stop the caller.

    Deliberately does NOT delete old backups. This app is handed off with no
    ongoing maintenance, so automatic cleanup that could silently remove a
    backup nobody is around to double-check is a bigger risk than the modest,
    slowly-growing disk usage of keeping every snapshot (data only grows by a
    few thousand rows per month).
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return None

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


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
