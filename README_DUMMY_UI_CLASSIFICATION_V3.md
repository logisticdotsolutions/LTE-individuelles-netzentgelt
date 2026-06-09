# Netzentgelt Dummy-UI-Klassifikation V3

Dieses Paket erweitert die Dummy-Lok-Klassifikation in der Controller-UI.

Wesentliche Änderung gegenüber V2:
- `data/01_mapping/dummy_locomotives.csv` ist eine pflegbare Konfigurationsdatei.
- Lokale Katalogeinträge werden beim Dry-Run nicht mehr als Fehler bewertet.
- Bestehende lokale Einträge bleiben erhalten.
- `91806189000-3` wird nur ergänzt, falls die Lok noch nicht vorhanden ist.
- Code-Dateien werden weiterhin streng gegen den geprüften GitHub-Stand validiert.

Installation:
1. `00_INSTALL_DUMMY_UI_CLASSIFICATION_V3.bat`
2. danach bewusst separat `05_RUN_PIPELINE_AND_VERIFY_DUMMY_UI_CLASSIFICATION_V3.bat`
