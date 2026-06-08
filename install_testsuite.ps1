param(
    [ValidateSet('DryRun','Apply','Rollback','Commit')]
    [string]$Mode = 'DryRun',
    [string]$TargetRoot = (Get-Location).Path,
    [string]$Manifest = ''
)

$ErrorActionPreference = 'Stop'
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $TargetRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path $VenvPython) { $VenvPython } else { 'python' }
$ModeMap = @{
    'DryRun' = 'dry-run'
    'Apply' = 'apply'
    'Rollback' = 'rollback'
    'Commit' = 'commit'
}
$Args = @((Join-Path $ScriptRoot 'apply_netzentgelt_test_suite.py'), '--mode', $ModeMap[$Mode], '--target', $TargetRoot)
if ($Manifest) { $Args += @('--manifest', $Manifest) }
& $Python @Args
exit $LASTEXITCODE
