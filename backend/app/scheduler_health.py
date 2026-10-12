from datetime import datetime
from .db import Session
from .models import Setting, now

with Session() as db:
    item = db.get(Setting, "scheduler_heartbeat")
    if (
        not item
        or (now() - datetime.fromisoformat(item.value["at"])).total_seconds() > 180
    ):
        raise SystemExit(1)
