# Quality Gate Overlap Hotfix

## Zweck

Das Quality Gate darf direkt aneinandergrenzende Bewegungen nicht als Überschneidung bewerten. Bisher wurden Überschneidungen aus gemeinsam berührten 15-Minuten-Slots abgeleitet. Dadurch konnten angrenzende Intervalle fälschlich blockiert werden.

Der Hotfix bildet zuerst echte zeitliche Schnittmengen und verdichtet nur diese anschließend auf 15-Minuten-Slots.

## Geänderte Datei

- `scripts/quality_gate_module.py`

## Reihenfolge

```powershell
.\01_DRY_RUN_QUALITY_GATE_OVERLAP_HOTFIX.bat
.\02_APPLY_QUALITY_GATE_OVERLAP_HOTFIX.bat
.\03_VERIFY_QUALITY_GATE_OVERLAP_HOTFIX.bat
.\04_RUN_QUALITY_GATE_OVERLAP_LOGIC_TESTS.bat
.\05_RUN_PIPELINE_AND_VERIFY_QUALITY_GATE_OVERLAP_HOTFIX.bat
```

Rollback:

```powershell
.\06_ROLLBACK_QUALITY_GATE_OVERLAP_HOTFIX.bat
```

## Erwartetes Ergebnis

- Direkt angrenzende Bewegungen erzeugen keine Überschneidungsminuten mehr.
- Echte Überschneidungen bleiben blockierend sichtbar.
- Andere Sperrgründe, etwa nicht exportfähige Bewegungen, bleiben unverändert.
