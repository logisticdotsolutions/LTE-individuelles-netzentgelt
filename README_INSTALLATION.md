# Netzentgelt MVP – additive Testsuite Phase 7A

## Zweck

Dieses ZIP installiert eine vollautomatische lokale Testsuite für den gepushten Phase-6D-Stand des Repositories `logisticdotsolutions/LTE-individuelles-netzentgelt`.

Die Installation ist absichtlich **rein additiv**:

- vorhandene Projektdateien werden nicht überschrieben,
- produktive CSV-Rohdaten werden nicht verändert,
- produktive DuckDB-Dateien werden nicht verändert,
- vorhandene lokale Änderungen bleiben unangetastet,
- ein Rollback löscht nur unveränderte, durch dieses Paket neu hinzugefügte Dateien,
- ein lokaler Commit kann erstellt werden, aber es erfolgt niemals automatisch ein Push.


## Empfohlene Ablage des Installationspakets

Das ZIP in einen separaten Ordner außerhalb des Repositorys entpacken, z. B.:

```text
C:\00_Projects\_patches\Netzentgelt_MVP_Phase7A_TestSuite_Additive_Patch_v1_1
```

Die BAT-Dateien anschließend aus dem separaten Paketordner starten, während PowerShell im Repository-Stamm steht.
Der Installer verarbeitet ausschließlich die im Paketmanifest freigegebenen Dateien. Zusätzliche Altdateien in einem lokalen `payload`-Ordner werden als WARNING angezeigt und ignoriert.

## Installation

ZIP in einen beliebigen temporären Ordner entpacken. Danach PowerShell oder CMD im Stammordner des lokalen Repositories öffnen, beispielsweise:

```bat
cd C:\00_Projects\LTE-individuelles-netzentgelt
```

Dann die BAT-Dateien aus dem entpackten Paket mit vollständigem Pfad ausführen.

### 1. Dry-Run

```bat
C:\Pfad\zum\entpackten\Paket\01_DRY_RUN_TEST_SUITE.bat
```

Der Dry-Run prüft:

- kompatiblen Repository-Stand über Sentinel-Dateien,
- Python-Syntax des vollständigen Payloads,
- Windows-CRLF,
- Dateikollisionen,
- rein additive Installation.

### 2. Anwenden

```bat
C:\Pfad\zum\entpackten\Paket\02_APPLY_TEST_SUITE.bat
```

### 3. Testabhängigkeiten einmalig installieren und Tests starten

```bat
RUN_TESTS.bat -InstallDependencies
RUN_TESTS.bat
```

### 4. Lokalen Commit erstellen

```bat
C:\Pfad\zum\entpackten\Paket\04_CREATE_LOCAL_COMMIT.bat
```

Alternativ nach der Installation direkt im Repository:

```bat
CREATE_TEST_SUITE_COMMIT.bat
```

Commit-Message:

```text
test: add automated Netzentgelt MVP regression suite
```

Es wird bewusst **nicht gepusht**.

### 5. Rollback

```bat
C:\Pfad\zum\entpackten\Paket\03_ROLLBACK_TEST_SUITE.bat
```

Der Rollback verwendet das jüngste Manifest unter `.patch_backups/`. Manuell veränderte Testsuite-Dateien werden nicht gelöscht, sondern als WARNING gemeldet.

## Neue Dateien im Repository

- `RUN_TESTS.bat`, `RUN_TESTS.ps1`
- `CREATE_TEST_SUITE_COMMIT.bat`
- `requirements-test.txt`, `pytest.ini`
- `tests/**`
- `docs/TESTSUITE_ARCHITEKTUR.md`
- `.github/workflows/netzentgelt-tests.yml.example`

## Wichtiger offener Punkt

Der aktuelle Phase-6D-Stand enthält Datei-Hashes, aber noch keine persistierte `source_row_hash` je Rohdatenzeile. Die Suite prüft bereits den deterministischen Referenzvertrag und meldet die fehlende Produktivintegration als `W001_SOURCE_ROW_HASH_NOT_INTEGRATED`.
