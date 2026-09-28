"""ORM models."""
import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    manufacturer = Column(String, index=True, nullable=False)
    model = Column(String, nullable=False)
    # Optional sub-grouping shown within a manufacturer's dashboard section,
    # e.g. "Consoles" vs "I/O Racks" - None means no sub-grouping for that item.
    category = Column(String, nullable=True)

    # dotted key a checker module understands, e.g. "digico:quantum", "yamaha:rivage_pm"
    checker_key = Column(String, nullable=True)
    # human-facing link to the page we scrape
    source_url = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    current_version = Column(String, nullable=True)
    previous_version = Column(String, nullable=True)
    # Kept as free-text exactly as each manufacturer states it (formats vary:
    # "March 27, 2026", "April 2026", "27.05.2026") rather than force-parsed
    # into one date type, which risks silently misreading an ambiguous
    # format like d&b's DD.MM.YYYY. None where no source publishes a date.
    release_date = Column(String, nullable=True)
    # Only for products published as separate per-platform builds with their
    # own versions (Dante Controller); None for everything else. A list of
    # {name, current_version, previous_version, last_changed_at (ISO string,
    # naive UTC), update_pending} dicts. current_version above then holds the
    # newest of them, and status is update_detected if *any* platform has a
    # pending update.
    platforms = Column(JSON, nullable=True)
    # unchecked | ok | update_detected | error
    status = Column(String, nullable=False, default="unchecked")

    last_checked_at = Column(DateTime, nullable=True)
    last_changed_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    logs = relationship(
        "CheckLog", back_populates="equipment", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "category": self.category,
            "checker_key": self.checker_key,
            "source_url": self.source_url,
            "notes": self.notes,
            "current_version": self.current_version,
            "previous_version": self.previous_version,
            "release_date": self.release_date,
            "platforms": self.platforms,
            "status": self.status,
            "last_checked_at": self.last_checked_at.isoformat()
            if self.last_checked_at
            else None,
            "last_changed_at": self.last_changed_at.isoformat()
            if self.last_changed_at
            else None,
            "last_error": self.last_error,
        }


class CheckLog(Base):
    __tablename__ = "check_log"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    checked_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    version_found = Column(String, nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    error = Column(Text, nullable=True)

    equipment = relationship("Equipment", back_populates="logs")
