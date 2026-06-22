param(
    [switch]$InstallDependencies,
    [switch]$Fast,
    [switch]$KeepTemporaryFiles
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONDONTWRITEBYTECODE = '1'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Python = if (Test-Path $VenvPython) { $VenvPython } else { 'python' }
$Timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$ReportDir = Join-Path $Root "_test_reports\$Timestamp"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

function Write-Section([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 78)
    Write-Host $Text
    Write-Host ('=' * 78)
}

Write-Section 'Netzentgelt MVP - automatisierte Testsuite'
Write-Host "Projekt: $Root"
Write-Host "Berichte: $ReportDir"
Write-Host 'Produktive Rohdaten und DuckDB-Dateien werden durch die Tests nicht verändert.'

if ($InstallDependencies) {
    Write-Section 'Installiere Laufzeit- und Test-Abhängigkeiten'
    & $Python -m pip install -r (Join-Path $Root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m pip install -r (Join-Path $Root 'requirements-test.txt')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Section 'Prüfe Test-Abhängigkeiten'
& $Python -c "import duckdb, openpyxl, pypdf, pytest, pytest_html, pytz; print('PASS: Test-Abhängigkeiten verfügbar.')"
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host 'FAIL: Test-Abhängigkeiten fehlen.'
    Write-Host 'Einmalig ausführen: RUN_TESTS.bat -InstallDependencies'
    exit 1
}

Write-Section 'Python-Syntaxprüfung'
& $Python (Join-Path $Root 'tests\support\syntax_check.py') (Join-Path $Root 'scripts') (Join-Path $Root 'tests')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Section 'WARNING-Prüfungen für noch nicht integrierte Verträge'
$WarningReport = Join-Path $ReportDir 'warnings.json'
& $Python (Join-Path $Root 'tests\support\warning_checks.py') --project-root $Root --report $WarningReport
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Section 'pytest-Ausführung'
$PytestArgs = @(
    '-m', 'pytest',
    '-q',
    '--tb=short',
    '--junitxml', (Join-Path $ReportDir 'pytest-junit.xml'),
    '--html', (Join-Path $ReportDir 'pytest-report.html'),
    '--self-contained-html'
)
if ($Fast) {
    $PytestArgs += @('-m', 'not smoke and not regression')
}
$ConsoleLog = Join-Path $ReportDir 'pytest-console.txt'
& $Python @PytestArgs 2>&1 | Tee-Object -FilePath $ConsoleLog
$PytestExit = $LASTEXITCODE

$Warnings = Get-Content $WarningReport -Raw | ConvertFrom-Json
$WarningCount = @($Warnings.warnings).Count
Write-Section 'Zusammenfassung'
if ($PytestExit -eq 0) {
    Write-Host 'PASS: Alle ausgeführten pytest-Tests sind erfolgreich.'
} else {
    Write-Host "FAIL: pytest meldet Fehler. Exit Code: $PytestExit"
}
if ($WarningCount -gt 0) {
    Write-Host "WARNING: $WarningCount Warnung(en). Details: $WarningReport"
} else {
    Write-Host 'WARNING: 0'
}
Write-Host "HTML-Bericht: $(Join-Path $ReportDir 'pytest-report.html')"
Write-Host "JUnit-Bericht: $(Join-Path $ReportDir 'pytest-junit.xml')"
Write-Host "Konsole: $ConsoleLog"

if (-not $KeepTemporaryFiles) {
    Get-ChildItem -Path $Root -Filter '.pytest_cache' -Directory -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
exit $PytestExit
