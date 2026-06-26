<#
.SYNOPSIS
    Renders a GlyphViz node CSV headlessly inside the glyphviz-linux Docker
    image, using the host's NVIDIA GPU.  Proves out the Linux/NVIDIA port
    (see Dockerfile.linux) without needing a desktop window.

.EXAMPLE
    .\tools\run_linux_smoketest.ps1 -Csv examples\Surface_Example\Surface_Example_gv_node.csv -Out smoke.png
#>
param(
    [Parameter(Mandatory=$true)][string]$Csv,
    [Parameter(Mandatory=$true)][string]$Out
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$outDirRaw = Split-Path -Parent $Out
if (-not $outDirRaw) { $outDirRaw = "." }
New-Item -ItemType Directory -Force -Path $outDirRaw | Out-Null
$outDir = Resolve-Path -Path $outDirRaw
$outFile = Split-Path -Leaf $Out
$csvUnix = $Csv -replace '\\', '/'

docker run --rm --gpus all `
    -v "${repoRoot}:/app" `
    -v "${outDir}:/out" `
    glyphviz-linux sh -c "Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp & sleep 2 && python3 tools/export_frame.py --csv $csvUnix --out /out/$outFile"

Write-Host "Wrote $outDir\$outFile"
