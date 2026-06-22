"""Reset the Streamlit rebuild status file."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from pipeline.status import reset_status  # noqa: E402


def main() -> None:
    reset_status(ROOT, reason="manual_cli_status_reset")
    print("Rebuild status reset to CURRENT.")


if __name__ == "__main__":
    main()
