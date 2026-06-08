param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("DryRun", "Apply", "Rollback", "Commit")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$TargetRoot
)

$ErrorActionPreference = "Stop"
$Python = Join-Path $TargetRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Virtuelle Python-Umgebung fehlt: $Python"
}
$Installer = Join-Path $PSScriptRoot "apply_phase7b_pipeline_test_ui.py"
$ModeArg = $Mode.ToLowerInvariant().Replace("dryrun", "dry-run")
& $Python $Installer --mode $ModeArg --target $TargetRoot
exit $LASTEXITCODE
