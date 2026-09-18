"""Maps a checker_key prefix (e.g. "digico:quantum" -> "digico") to the
module that knows how to resolve it."""
from app.checkers import allenheath, dante, dbaudio, digico, shure, ssl, yamaha

MODULES = {
    "digico": digico,
    "yamaha": yamaha,
    "shure": shure,
    "ah": allenheath,
    "dante": dante,
    "db": dbaudio,
    "ssl": ssl,
}


def module_for(checker_key: str):
    if not checker_key or ":" not in checker_key:
        return None
    prefix = checker_key.split(":", 1)[0]
    return MODULES.get(prefix)
