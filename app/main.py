import datetime as dt
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dashboard_data import build_dashboard_context
from app.database import Base, engine, get_db, run_light_migrations
from app.models import Equipment
from app.runner import check_all, check_equipment, clear_update_flag, record_manual_check
from app.scheduler import (
    CHECK_INTERVAL_HOURS,
    schedule_first_run,
    shutdown_scheduler,
    start_scheduler,
)
from app.seed import seed
from app.timeutil import to_pacific

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="HTA Firmware Tracker")

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Cache-busting: a fresh value each time the server process starts, appended
# as ?v=... to every static asset URL. Without this, browsers can keep
# serving an old cached style.css/app.js/logo even after we've shipped
# changes and restarted - this forces a refetch on the very next page load
# instead of requiring a manual hard-refresh.
BUILD_VERSION = str(int(time.time()))
templates.env.globals["v"] = BUILD_VERSION
templates.env.filters["pacific"] = to_pacific


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_light_migrations()
    seed()
    start_scheduler()
    schedule_first_run(delay_seconds=5)


@app.on_event("shutdown")
def on_shutdown():
    shutdown_scheduler()


@app.get("/sw.js")
def service_worker():
    # Served from the root, not /static/sw.js - a service worker's default
    # max scope is the directory it's served from, so this is what lets it
    # register with scope "/" (covering the dashboard page itself, not just
    # static assets) without needing a Service-Worker-Allowed header.
    return FileResponse(APP_DIR / "static" / "sw.js", media_type="application/javascript")


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    items = db.query(Equipment).order_by(Equipment.manufacturer, Equipment.model).all()
    context = build_dashboard_context(items)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "now": dt.datetime.utcnow(),
            "check_interval_hours": CHECK_INTERVAL_HOURS,
            "interactive": True,
            **context,
        },
    )


@app.post("/api/check-now")
def api_check_now(db: Session = Depends(get_db)):
    n = check_all(db)
    return {"checked": n}


@app.post("/api/check/{equipment_id}")
def api_check_one(equipment_id: int, db: Session = Depends(get_db)):
    item = db.query(Equipment).get(equipment_id)
    if not item:
        return {"error": "not found"}
    check_equipment(db, [item])
    return item.to_dict()


@app.post("/api/acknowledge/{equipment_id}")
def api_acknowledge(equipment_id: int, db: Session = Depends(get_db)):
    item = clear_update_flag(db, equipment_id)
    return item.to_dict() if item else {"error": "not found"}


class ManualCheckIn(BaseModel):
    version: str
    release_date: Optional[str] = None


@app.post("/api/manual-check/{equipment_id}")
def api_manual_check(equipment_id: int, body: ManualCheckIn, db: Session = Depends(get_db)):
    try:
        item = record_manual_check(db, equipment_id, body.version, body.release_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    return item.to_dict()


@app.get("/api/equipment")
def api_equipment(db: Session = Depends(get_db)):
    items = db.query(Equipment).order_by(Equipment.manufacturer, Equipment.model).all()
    return [i.to_dict() for i in items]


@app.post("/check-now")
def check_now_redirect(db: Session = Depends(get_db)):
    check_all(db)
    return RedirectResponse(url="/", status_code=303)
