param(
    [string]$EntryPoint = "",
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
$DistRoot = Join-Path $Root 'dist'
$DistDir = Join-Path $DistRoot 'NetzentgeltMVP'
$ZipPath = Join-Path $DistRoot 'NetzentgeltMVP_Windows_Portable.zip'

function Write-Section([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 78)
    Write-Host $Text
    Write-Host ('=' * 78)
}

function Test-PythonModule([string]$ModuleName) {
    & $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)" | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Add-DataIfExists([System.Collections.Generic.List[string]]$Args, [string]$RelativePath, [string]$Destination) {
    $FullPath = Join-Path $Root $RelativePath
    if (Test-Path $FullPath) {
        $Args.Add('--add-data')
        $Args.Add("$FullPath;$Destination")
    }
}

Write-Section 'Netzentgelt MVP - Windows EXE Paket bauen'
Write-Host "Projekt: $Root"
Write-Host "Python:  $Python"

if (-not (Test-Path $Launcher)) {
    throw "Launcher nicht gefunden: $Launcher"
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
$PyInstallerArgs.AddRange(@(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--clean',
    '--onedir',
    '--contents-directory', '.',
    '--name', 'NetzentgeltMVP',
    '--console',
    '--copy-metadata', 'streamlit'
))

foreach ($Module in @('streamlit', 'altair', 'duckdb', 'pandas', 'openpyxl', 'pypdf', 'yaml', 'pyarrow')) {
    if (Test-PythonModule $Module) {
        $PyInstallerArgs.Add('--collect-all')
        $PyInstallerArgs.Add($Module)
    }
}

Add-DataIfExists $PyInstallerArgs 'requirements.txt' '.'
Add-DataIfExists $PyInstallerArgs 'packaging\netzentgelt_entrypoint.txt' 'packaging'
Add-DataIfExists $PyInstallerArgs 'scripts' 'scripts'
Add-DataIfExists $PyInstallerArgs 'data' 'data'
Add-DataIfExists $PyInstallerArgs 'config' 'config'
Add-DataIfExists $PyInstallerArgs 'templates' 'templates'
Add-DataIfExists $PyInstallerArgs '.streamlit' '.streamlit'

$PyInstallerArgs.Add($Launcher)

& $Python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path $DistDir)) {
    throw "Build-Ordner wurde nicht gefunden: $DistDir"
}

Write-Section 'Erzeuge portables ZIP-Paket'
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $DistDir '*') -DestinationPath $ZipPath -Force

Write-Host "Fertig. Dieses ZIP an Kollegen senden:"
Write-Host $ZipPath
Write-Host ''
Write-Host 'Kollege: ZIP entpacken und NetzentgeltMVP.exe starten.'
