# Netzentgelt MVP – Lösungsstempel und lokale Zeitanzeige

Dieser kleine Hotfix basiert auf dem GitHub-Stand `1bce27cac9286cc2e14b80cb6a0af7de5ef8bed9` und verändert ausschließlich `app/app.py`.

## Änderungen

- sichtbarer Hinweis: `Konzeption, Fachlogik & Umsetzung: Christoph Orgl`
- transparenter Zusatz: `KI-gestützte Entwicklung mit OpenAI ChatGPT als Engineering-Copilot`
- eingeklappter Seitenleistenbereich `Über dieses Tool`
- Anzeige des letzten Imports in lokaler Systemzeit statt UTC
- gespeicherte UTC-Auditzeitstempel bleiben unverändert

## Reihenfolge

```powershell
.\01_DRY_RUN_ATTRIBUTION_TIMEZONE_HOTFIX.bat
.\02_APPLY_ATTRIBUTION_TIMEZONE_HOTFIX.bat
.\03_VERIFY_ATTRIBUTION_TIMEZONE_HOTFIX.bat
.\04_RUN_ATTRIBUTION_TIMEZONE_HOTFIX_TESTS.bat
```

Rollback:

```powershell
.\05_ROLLBACK_ATTRIBUTION_TIMEZONE_HOTFIX.bat
```
