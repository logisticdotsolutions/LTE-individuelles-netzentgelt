"""Laufzeit- und Statusmodell fuer Pipeline-Schritte."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class StepResult:
    """Ergebnis eines Pipeline-Schritts."""

    step_id: str
    status: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    rows_affected: int | None = None
    message: str = ""

    @classmethod
    def success(
        cls,
        step_id: str,
        started_at: datetime,
        message: str = "",
        rows_affected: int | None = None,
    ) -> "StepResult":
        finished_at = datetime.now(timezone.utc)
        return cls(
            step_id=step_id,
            status="SUCCESS",
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            rows_affected=rows_affected,
            message=message,
        )

    @classmethod
    def failed(
        cls,
        step_id: str,
        started_at: datetime,
        exc: BaseException,
    ) -> "StepResult":
        finished_at = datetime.now(timezone.utc)
        return cls(
            step_id=step_id,
            status="FAILED",
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            message=f"{type(exc).__name__}: {exc}",
        )

    def to_log_dict(self) -> dict[str, Any]:
        """JSON-/CSV-taugliche Darstellung fuer Laufprotokolle."""
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat()
        return data
