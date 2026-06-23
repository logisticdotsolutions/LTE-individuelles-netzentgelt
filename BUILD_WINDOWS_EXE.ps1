param(
    [string]$EntryPoint = "app\secure_app_portable.py",
    [switch]$SkipDependencyInstall
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
$Launcher = Join-Path $Root 'packaging\streamlit_exe_launcher.py'
$EntryConfig = Join-Path $Root 'packaging\netzentgelt_entrypoint.txt'
$PortableRuntimeTemplate = Join-Path $Root 'config\portable_runtime.template.json'
$PackageCheckScript = Join-Path $Root 'scripts\check_keyuser_package.py'
$DistRoot = Join-Path $Root 'dist'
$DistDir = Join-Path $DistRoot 'NetzentgeltMVP'
$InternalZipPath = Join-Path $DistRoot 'NetzentgeltMVP_Windows_Portable.zip'
$KeyUserRoot = Join-Path $Root '_keyuser_package'
$KeyUserDir = Join-Path $KeyUserRoot 'NetzentgeltMVP_KeyUser'
$KeyUserZipPath = Join-Path $KeyUserRoot 'NetzentgeltMVP_KeyUser.zip'
$BuildStamp = Get-Date -Format 'yyyyMMddTHHmmss'
$KeyUserBuildParent = Join-Path (Join-Path $KeyUserRoot '_build') $BuildStamp
$KeyUserStagingDir = Join-Path $KeyUserBuildParent 'NetzentgeltMVP_KeyUser'
$KeyUserReadme = Join-Path $KeyUserStagingDir 'START_HIER.txt'

function Write-Section([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 78)
    Write-Host $Text
    Write-Host ('=' * 78)
}

function Add-Argument([System.Collections.Generic.List[string]]$ArgumentList, [string]$Value) {
    [void]$ArgumentList.Add($Value)
}

function Add-Arguments([System.Collections.Generic.List[string]]$ArgumentList, [string[]]$Values) {
    foreach ($Value in $Values) {
        Add-Argument $ArgumentList $Value
    }
}

function Test-PythonModule([string]$ModuleName) {
    & $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)" | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Add-DataIfExists([System.Collections.Generic.List[string]]$ArgumentList, [string]$RelativePath, [string]$Destination) {
    $FullPath = Join-Path $Root $RelativePath
    if (Test-Path $FullPath) {
        Add-Argument $ArgumentList '--add-data'
        Add-Argument $ArgumentList "$FullPath;$Destination"
    }
}

function Remove-DirectoryBestEffort([string]$Path) {
    if (-not (Test-Path $Path)) {
        return $true
    }
    try {
        Remove-Item $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch {
        Write-Warning "Ordner konnte nicht entfernt werden: $Path"
        Write-Warning "Grund: $($_.Exception.Message)"
        Write-Warning "Vermutlich laeuft noch eine alte NetzentgeltMVP.exe oder ein Prozess haelt Dateien im Paketordner offen."
        return $false
    }
}

function Copy-PortableRuntimeTemplate([string]$PackageRoot) {
    if (-not (Test-Path $PortableRuntimeTemplate)) {
        throw "Portable Runtime Template fehlt: $PortableRuntimeTemplate"
    }

    $PackageRootPath = [System.IO.Path]::GetFullPath($PackageRoot)
    $PackageConfigDir = Join-Path $PackageRootPath 'config'
    New-Item -ItemType Directory -Path $PackageConfigDir -Force | Out-Null

    $TargetConfig = Join-Path $PackageConfigDir 'portable_runtime.template.json'
    $TargetRoot = Join-Path $PackageRootPath 'portable_runtime.template.json'

    Copy-Item -Path $PortableRuntimeTemplate -Destination $TargetConfig -Force
    Copy-Item -Path $PortableRuntimeTemplate -Destination $TargetRoot -Force

    Write-Host "Portable Runtime Template kopiert: $TargetConfig"
    Write-Host "Portable Runtime Template kopiert: $TargetRoot"
}

function Write-KeyUserReadme([string]$Path) {
    $Text = @'
NETZENTGELT MVP - STARTANLEITUNG FUER KEY USER

1. Diesen gesamten Ordner lokal entpacken bzw. kopieren.
   Beispiel: C:\LTE\NetzentgeltMVP_KeyUser

2. NetzentgeltMVP.exe per Doppelklick starten.

3. Es oeffnet sich ein Browserfenster mit der lokalen Anwendung.
   Falls kein Browser aufgeht, im Konsolenfenster die angezeigte Adresse oeffnen.
   Beispiel: http://127.0.0.1:8501

4. Wichtig:
   - Nicht direkt aus dem ZIP starten.
   - Den gesamten Ordner zusammenlassen.
   - Keine Dateien aus Unterordnern loeschen oder verschieben.
   - Fuer Speichern/Export braucht der Ordner Schreibrechte.

5. Bei Problemen bitte Screenshot vom Konsolenfenster und vom Browserfehler senden.
'@
    Set-Content -Path $Path -Value $Text -Encoding UTF8
}

Write-Section 'Netzentgelt MVP - Windows EXE Paket bauen'
Write-Host "Projekt: $Root"
Write-Host "Python:  $Python"

if (-not (Test-Path $Launcher)) {
    throw "Launcher nicht gefunden: $Launcher"
}

if (-not (Test-Path $PortableRuntimeTemplate)) {
    throw "Portable Runtime Template fehlt: $PortableRuntimeTemplate"
}

if ($EntryPoint.Trim().Length -gt 0) {
    $NormalizedEntry = $EntryPoint.Trim().Replace('/', '\')
    $EntryFullPath = Join-Path $Root $NormalizedEntry
    if (-not (Test-Path $EntryFullPath)) {
        throw "Angegebener Streamlit-Einstieg wurde nicht gefunden: $NormalizedEntry"
    }
    Set-Content -Path $EntryConfig -Value $NormalizedEntry -Encoding UTF8
    Write-Host "Streamlit-Einstieg: $NormalizedEntry"
} else {
    if (Test-Path $EntryConfig) {
        Remove-Item $EntryConfig -Force
    }
    Write-Host 'Streamlit-Einstieg: automatische Erkennung beim Start der EXE'
}

if (-not $SkipDependencyInstall) {
    Write-Section 'Installiere Build-Abhaengigkeiten'
    & $Python -m pip install -r (Join-Path $Root 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Section 'Baue EXE mit PyInstaller'
$PyInstallerArgs = [System.Collections.Generic.List[string]]::new()
Add-Arguments $PyInstallerArgs ([string[]]@(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--clean',
    '--onedir',
    '--contents-directory', '.',
    '--name', 'NetzentgeltMVP',
    '--console',
    '--copy-metadata', 'streamlit',
    '--hidden-import', 'azure',
    '--hidden-import', 'azure.core',
    '--hidden-import', 'azure.storage',
    '--hidden-import', 'azure.storage.blob',
    '--hidden-import', 'dotenv'
))

foreach ($Module in @(
    'streamlit',
    'altair',
    'duckdb',
    'pandas',
    'openpyxl',
    'pypdf',
    'yaml',
    'pyarrow',
    'azure',
    'azure.core',
    'azure.storage',
    'azure.storage.blob',
    'dotenv',
    'cryptography',
    'certifi',
    'isodate'
)) {
    if (Test-PythonModule $Module) {
        Add-Argument $PyInstallerArgs '--collect-all'
        Add-Argument $PyInstallerArgs $Module
    }
}

Add-DataIfExists $PyInstallerArgs 'requirements.txt' '.'
Add-DataIfExists $PyInstallerArgs 'packaging\netzentgelt_entrypoint.txt' 'packaging'
Add-DataIfExists $PyInstallerArgs 'app' 'app'
Add-DataIfExists $PyInstallerArgs 'scripts' 'scripts'
Add-DataIfExists $PyInstallerArgs 'data' 'data'
Add-DataIfExists $PyInstallerArgs 'config' 'config'
Add-DataIfExists $PyInstallerArgs 'templates' 'templates'
Add-DataIfExists $PyInstallerArgs '.streamlit' '.streamlit'

Add-Argument $PyInstallerArgs $Launcher

$PyInstallerArgArray = [string[]]$PyInstallerArgs.ToArray()
if ($PyInstallerArgArray.Count -lt 3 -or $PyInstallerArgArray[0] -ne '-m' -or $PyInstallerArgArray[1] -ne 'PyInstaller') {
    throw "Interner Buildfehler: PyInstaller-Argumente wurden nicht korrekt aufgebaut."
}
Write-Host "PyInstaller-Aufruf: $Python $($PyInstallerArgArray -join ' ')"

& $Python @PyInstallerArgArray
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path $DistDir)) {
    throw "Build-Ordner wurde nicht gefunden: $DistDir"
}

# Entrypoint-Config explizit nachkopieren (PyInstaller ignoriert einzelne .txt-Dateien via --add-data)
if (Test-Path $EntryConfig) {
    $DestPackaging = Join-Path $DistDir 'packaging'
    New-Item -ItemType Directory -Path $DestPackaging -Force | Out-Null
    Copy-Item -Path $EntryConfig -Destination $DestPackaging -Force
    Write-Host "Entrypoint-Config kopiert: $EntryConfig -> $DestPackaging"
}

# Runtime-Template explizit in Dist absichern, damit es bei PyInstaller-Layoutaenderungen nicht verloren geht.
Copy-PortableRuntimeTemplate $DistDir

Write-Section 'Erzeuge gesondertes Key-User-Paket'
New-Item -ItemType Directory -Path $KeyUserStagingDir -Force | Out-Null
Copy-Item -Path (Join-Path $DistDir '*') -Destination $KeyUserStagingDir -Recurse -Force
Write-KeyUserReadme $KeyUserReadme
Copy-PortableRuntimeTemplate $KeyUserStagingDir

if (Test-Path $KeyUserZipPath) {
    Remove-Item $KeyUserZipPath -Force
}
Compress-Archive -Path $KeyUserStagingDir -DestinationPath $KeyUserZipPath -Force

$PackageDirForCheck = $KeyUserStagingDir
Write-Section 'Aktualisiere sichtbaren Key-User-Ordner'
if (Remove-DirectoryBestEffort $KeyUserDir) {
    Copy-Item -Path $KeyUserStagingDir -Destination $KeyUserRoot -Recurse -Force
    $PackageDirForCheck = $KeyUserDir
    Write-Host "Sichtbarer Paketordner aktualisiert: $KeyUserDir"
} else {
    Write-Warning "ZIP wurde trotzdem aus frischem Staging erzeugt: $KeyUserZipPath"
    Write-Warning "Frischer Paketordner fuer diese Build-Ausfuehrung: $KeyUserStagingDir"
    Write-Warning "Zum Aktualisieren des sichtbaren Ordners bitte laufende NetzentgeltMVP.exe beenden und Build erneut starten."
}

Write-Section 'Pruefe Key-User-Paket'
if (-not (Test-Path $PackageCheckScript)) {
    throw "Paketcheck-Skript fehlt: $PackageCheckScript"
}
& $Python $PackageCheckScript --package-dir $PackageDirForCheck --zip-path $KeyUserZipPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'FERTIG.'
Write-Host ''
Write-Host 'NUR DIESES ZIP AN KEY USER SENDEN:'
Write-Host "ZIP:    $KeyUserZipPath"
Write-Host ''
Write-Host 'Optionaler Ordner zur lokalen Pruefung:'
Write-Host "Ordner: $PackageDirForCheck"
Write-Host ''
Write-Host 'Key User: ZIP entpacken, START_HIER.txt lesen, NetzentgeltMVP.exe starten.'
