# GAP Scope UI Hotfix

## Zweck

Im Korrektur-Cockpit dürfen nur DE-relevante Unterbrechungen als manuell bearbeitbare Prüffälle angeboten werden. Nicht DE-relevante GAP-Zeilen bleiben intern für Audit und Zeitachsenkontext erhalten, werden aber nicht mehr als Korrekturfall angezeigt.

## Geänderte Datei

- `scripts/manual_override_ui_module.py`

## Reihenfolge

```powershell
.\01_DRY_RUN_GAP_SCOPE_UI_HOTFIX.bat
.\02_APPLY_GAP_SCOPE_UI_HOTFIX.bat
.\03_VERIFY_GAP_SCOPE_UI_HOTFIX.bat
.\04_RUN_GAP_SCOPE_UI_HOTFIX_TESTS.bat
```

Rollback:

```powershell
.\05_ROLLBACK_GAP_SCOPE_UI_HOTFIX.bat
```
