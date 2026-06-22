from __future__ import annotations

from json import dumps

from mp_id_import_module import run_import


if __name__ == "__main__":
    metadata = run_import()
    print("PASS: DB-Energie-Marktpartner-IDs importiert.")
    print(dumps(metadata, ensure_ascii=False, indent=2))
