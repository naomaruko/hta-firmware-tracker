"""Database setup: SQLite via SQLAlchemy."""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = os.environ.get("FIRMWARE_TRACKER_DB", str(DATA_DIR / "tracker.db"))
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



# Columns added to Equipment after the table already existed in the wild.
# create_all() only creates brand-new tables, it never alters an existing
# one - so each column added here needs a line below too, or upgrading would
# require deleting data/tracker.db instead of just picking up the new field.
_EQUIPMENT_COLUMNS_ADDED_LATER = [
    ("release_date", "VARCHAR"),
    ("category", "VARCHAR"),
    ("platforms", "JSON"),
    ("content_hash", "VARCHAR"),
    ("review_since", "DATETIME"),
]


# Columns dropped from Equipment after the table already existed in the wild.
# The old NOT NULL check_method column has no default at the SQL level, so a
# database that still has it would reject every new row seed() inserts - it
# has to be removed, not just ignored.
_EQUIPMENT_COLUMNS_REMOVED = ["check_method"]


def run_light_migrations():
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "equipment" not in inspector.get_table_names():
        return  # fresh DB - create_all will make it with every column already
    existing_cols = {c["name"] for c in inspector.get_columns("equipment")}
    for name, col_type in _EQUIPMENT_COLUMNS_ADDED_LATER:
        if name not in existing_cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE equipment ADD COLUMN {name} {col_type}"))
    for name in _EQUIPMENT_COLUMNS_REMOVED:
        if name in existing_cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE equipment DROP COLUMN {name}"))
