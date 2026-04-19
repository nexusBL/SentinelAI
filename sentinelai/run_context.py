from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class RunContext:
    run_id: str
    phase: str
    target_url: str
    instruction: str
    created_at: datetime

