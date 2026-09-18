#!/bin/bash
# Starts the HTA Firmware Tracker and opens it in your default browser.
#
# --reload watches app/ and restarts automatically whenever a code/template/
# CSS file changes, so a fresh edit shows up on the next page refresh without
# needing to close and reopen this. Only watches app/ (not data/, where the
# database lives) so routine background checks writing to the DB don't
# trigger restarts. This is a development convenience - when this eventually
# moves to permanent always-on hosting, drop --reload for that launch command
# (auto-reload isn't meant for an unattended production service).
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
open "http://127.0.0.1:8811" &
uvicorn app.main:app --host 127.0.0.1 --port 8811 --reload --reload-dir app
