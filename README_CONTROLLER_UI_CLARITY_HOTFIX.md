# Netzentgelt Controller-UI Klartext-Hotfix

Geprüfter GitHub-Stand: `f959b1c5ce9eb20ad06dc81f26b9423997c33a35`

## Scope

- R012-Dummy-Fälle werden in der Controller-UI klar als `Dummy-Lok` bezeichnet.
- Echte fehlende Loknummern bleiben separat als `Loknummer fehlt` sichtbar.
- Systemvorschläge erhalten für GAP-bezogene Fälle die zusätzliche Spalte `GAP-Minuten`.
- Keine Änderung an Rule Engine, Quality Gate, Rohdaten, DuckDB oder Exporten.

## Installation

```powershell
cd C:\00_Projects\LTE-individuelles-netzentgelt
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\Netzentgelt_Controller_UI_Clarity_Hotfix.zip" -DestinationPath . -Force
.\06_PACKAGE_SELFTEST_CONTROLLER_UI_CLARITY_HOTFIX.bat
.\00_INSTALL_CONTROLLER_UI_CLARITY_HOTFIX.bat
```

Danach Streamlit neu starten.

## Rollback

```powershell
.\05_ROLLBACK_CONTROLLER_UI_CLARITY_HOTFIX.bat
```
