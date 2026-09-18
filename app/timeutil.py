"""Pacific-time display helpers.

All timestamps are stored in the database as naive UTC (datetime.utcnow()) -
that part doesn't change, it's still the correct way to store them. This
module only handles the *display* conversion to Pacific time, and does it
properly (via the IANA zone, not a fixed UTC-8 offset) so it automatically
shows PST in winter and PDT in summer instead of being wrong half the year.
"""
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
PACIFIC = ZoneInfo("America/Los_Angeles")


def to_pacific(naive_utc_dt, fmt="%b %-d, %I:%M %p %Z"):
    """naive UTC datetime -> formatted Pacific-time string, or None."""
    if naive_utc_dt is None:
        return None
    aware = naive_utc_dt.replace(tzinfo=UTC).astimezone(PACIFIC)
    return aware.strftime(fmt)
