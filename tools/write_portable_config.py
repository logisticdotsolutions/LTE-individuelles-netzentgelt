from __future__ import annotations

import argparse
import json
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=str(ROOT / "config" / "portable_runtime.enc"))
    parser.add_argument("--runtime-key", default=str(ROOT / "config" / "portable_runtime.key"))
    args = parser.parse_args()

    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    token = Fernet.generate_key()
    encrypted = Fernet(token).encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_bytes(encrypted)
    Path(args.runtime_key).write_text(token.decode("ascii") + "\n", encoding="utf-8")
    print("OK: portable_runtime.enc und portable_runtime.key wurden erzeugt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
