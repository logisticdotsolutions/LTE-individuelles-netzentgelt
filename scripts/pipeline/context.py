"""Zentraler Pipeline-Kontext fuer Pfade und Fachparameter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class PipelineContext:
    """Gemeinsamer Kontext fuer Pipeline-Schritte.

    Ziel ist, Pfade und fachliche Standardparameter nicht mehr verstreut in
    mehreren Modulen zu halten. Die Defaults spiegeln den aktuellen Aufbau des
    Netzentgelt-MVP wider.
    """

    root: Path
    raw_dir: Path
    map_dir: Path
    db_dir: Path
    export_dir: Path
    log_dir: Path
    db_path: Path
    db_build_path: Path
    run_id: str
    home_country_iso: str = "DE"
    lookback_months: int = 6
    gap_threshold_minutes: int = 15
    overlap_tolerance_minutes: int = 5

    @classmethod
    def from_project_root(cls, root: Path | None = None) -> "PipelineContext":
        """Kontext ausgehend vom Projektstamm erzeugen."""
        project_root = root or Path(__file__).resolve().parents[2]
        db_dir = project_root / "data" / "02_duckdb"

        return cls(
            root=project_root,
            raw_dir=project_root / "data" / "00_raw",
            map_dir=project_root / "data" / "01_mapping",
            db_dir=db_dir,
            export_dir=project_root / "data" / "03_exports",
            log_dir=project_root / "data" / "04_logs",
            db_path=db_dir / "netzentgelt.duckdb",
            db_build_path=db_dir / "netzentgelt_build.duckdb",
            run_id=datetime.now(timezone.utc).strftime("RUN_%Y%m%d_%H%M%S"),
        )

    def ensure_directories(self) -> None:
        """Alle Standardordner anlegen, falls sie fehlen."""
        for directory in [
            self.raw_dir,
            self.map_dir,
            self.db_dir,
            self.export_dir,
            self.log_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
