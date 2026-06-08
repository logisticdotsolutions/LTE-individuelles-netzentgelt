# Netzentgelt MVP - Phase 7B Pipeline- und Testcontroller

Basis: GitHub `main`, Commit `866d98c652fe1ad17e0c231c8708c58735a3d66d` (`test implementiert`).

## Inhalt

Der Patch integriert im bestehenden Streamlit-Tab **⚙️ Technik: Pipeline** drei Aktionen:

1. **Nur Tests starten**
2. **Pipeline + Tests**
3. **Azure-Download + Pipeline + Tests**

Die Ergebnisanzeige enthält PASS / FAIL / WARNING, jeden einzelnen Test mit Status und Laufzeit, Fehlerdetails sowie Downloadbuttons für HTML-, JUnit-, Konsolen- und JSON-Bericht.

Zusätzlich werden die sieben bekannten Phase-7A-Fixture-Probleme korrigiert und die UTF-8-Ausgabe der lokalen Testsuite gehärtet.

## Sicherheitsgrenzen

- Tests verändern keine produktiven Rohdaten oder produktiven DuckDB-Dateien.
- Pipeline-Aktionen sind bewusst produktiv und verwenden weiterhin die bestehende abgesicherte Build- und Replace-Logik.
- Der Installer überschreibt keine unbekannten lokalen Änderungen.
- Vor Änderungen werden Backups unter `.patch_backups/` erstellt.

## Anwendung

Im Repository-Stamm ausführen:

```bat
C:\Pfad\zum\Patch\01_DRY_RUN_PHASE7B_PIPELINE_TEST_UI.bat
C:\Pfad\zum\Patch\02_APPLY_PHASE7B_PIPELINE_TEST_UI.bat
RUN_TESTS.bat
```

Danach Streamlit neu starten oder die Seite neu laden.

## Rollback

```bat
C:\Pfad\zum\Patch\03_ROLLBACK_PHASE7B_PIPELINE_TEST_UI.bat
```

## Lokaler Commit ohne Push

Nach erfolgreichem Testlauf:

```bat
C:\Pfad\zum\Patch\04_CREATE_LOCAL_COMMIT.bat
```
