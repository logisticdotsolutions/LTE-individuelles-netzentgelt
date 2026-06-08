# Netzentgelt MVP – sichtbare Lok-Vormerkung

Basis: GitHub `main` auf Commit `7363ecb3bb81a199e7eb3afbe17ee4dfda940ccc`.

## Änderung

- Der Button `Lok vormerken` schreibt nun in den tatsächlich verwendeten Auswahl-Key `timeline_detail_loco`.
- Zusätzlich bleibt `timeline_bookmarked_loco` für einen sichtbaren Hinweis erhalten.
- Im Reiter `4. Lok prüfen` erscheint:
  `Vorgemerkte Lok: <Loknummer>. Die Lok ist in der Auswahl unten bereits vorbelegt.`
- Nach Wechsel des Arbeitszeitraums wird ein ungültiger Auswahl-State defensiv entfernt.
- Keine Änderung an Berechnung, Timeline, Findings, Quality Gate oder Exporten.

## Reihenfolge

```powershell
.\01_DRY_RUN_LOCO_BOOKMARK_HOTFIX.bat
.\02_APPLY_LOCO_BOOKMARK_HOTFIX.bat
.\03_VERIFY_LOCO_BOOKMARK_HOTFIX.bat
.\04_RUN_LOCO_BOOKMARK_HOTFIX_TESTS.bat
```

Rollback:

```powershell
.\05_ROLLBACK_LOCO_BOOKMARK_HOTFIX.bat
```
