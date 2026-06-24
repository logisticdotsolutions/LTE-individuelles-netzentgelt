$ErrorActionPreference = 'Stop'

$ArtifactDir = '_keyuser_package'
$ArtifactZip = Join-Path $ArtifactDir 'NetzentgeltMVP_KeyUser.zip'
$ReleaseZips = Get-ChildItem -Path '_release' -Filter 'NetzentgeltMVP_KeyUser.zip' -Recurse -File -ErrorAction SilentlyContinue

if (-not $ReleaseZips) {
    throw 'Kein portables Release-ZIP unter _release gefunden.'
}

$LatestReleaseZip = $ReleaseZips | Sort-Object LastWriteTime -Descending | Select-Object -First 1

New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
Copy-Item -Path $LatestReleaseZip.FullName -Destination $ArtifactZip -Force
Get-Item $ArtifactZip | Select-Object FullName, Length
