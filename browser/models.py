from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class BrowserRunResult:
    requested_url: str
    final_url: str | None
    page_title: str | None
    navigation_status: int | None
    started_at: datetime
    completed_at: datetime
    status: str
    before_screenshot_path: Path | None
    after_screenshot_path: Path | None
    dom_snapshot_path: Path | None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "page_title": self.page_title,
            "navigation_status": self.navigation_status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "status": self.status,
            "before_screenshot_path": (
                str(self.before_screenshot_path) if self.before_screenshot_path else None
            ),
            "after_screenshot_path": (
                str(self.after_screenshot_path) if self.after_screenshot_path else None
            ),
            "dom_snapshot_path": (
                str(self.dom_snapshot_path) if self.dom_snapshot_path else None
            ),
            "error_message": self.error_message,
        }

