<#
.SYNOPSIS
  AI Observatory: turn one prompt into a GlyphViz scene, in one line.

.DESCRIPTION
  Runs the three steps in order and stops at the first failure:
    1. extract_gpt2.py  (observatory env)  run GPT-2 small on the prompt
    2. build_scene.py   (glyphviz env)     write the scene folder
    3. verify_scene.py  (glyphviz env)     check it through GlyphViz's loaders

  The scene lands in ai_observatory\scenes\AI_Observatory_GPT2_<Name>\ ;
  drag its _gv_node.csv into GlyphViz.

  Works from any folder. Finds each conda env's python.exe on its own
  (anaconda3, .conda or miniconda3 under your user folder); set
  $env:OBSERVATORY_PYTHON / $env:GLYPHVIZ_PYTHON to override.

.EXAMPLE
  .\ai_observatory\make_scene.ps1 "The Eiffel Tower is in the city of" Eiffel

.NOTES
  Stop the prompt right before the word you want GPT-2 to produce, with no
  trailing space. Each token adds about 1.2 s of animation; 5-25 is comfortable.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Prompt,
    [Parameter(Mandatory = $true, Position = 1)][string]$Name
)
$ErrorActionPreference = "Stop"

function Find-EnvPython([string]$envName, [string]$override) {
    if ($override -and (Test-Path $override)) { return $override }
    $candidates = @(
        (Join-Path $env:USERPROFILE "anaconda3\envs\$envName\python.exe"),
        (Join-Path $env:USERPROFILE ".conda\envs\$envName\python.exe"),
        (Join-Path $env:USERPROFILE "miniconda3\envs\$envName\python.exe"))
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    throw "Could not find the '$envName' conda env. Looked in:`n  $($candidates -join "`n  ")"
}

$here = $PSScriptRoot
$obsPython = Find-EnvPython "observatory" $env:OBSERVATORY_PYTHON
$gvPython = Find-EnvPython "glyphviz" $env:GLYPHVIZ_PYTHON

# A trailing space becomes its own token and spoils the prediction
# (GPT-2's word tokens carry their leading space).
$clean = $Prompt.TrimEnd()
if ($clean -ne $Prompt) { Write-Host "Note: removed trailing whitespace from the prompt." -ForegroundColor Yellow }
if (-not $clean) { throw "The prompt is empty." }

$safe = ($Name -replace '[^A-Za-z0-9_-]', '_').Trim('_')
if (-not $safe) { throw "Name '$Name' has no usable characters." }
if ($safe -like "AI_Observatory_*") { $sceneName = $safe } else { $sceneName = "AI_Observatory_GPT2_$safe" }
$slug = $safe.ToLower()
$sceneDir = Join-Path $here "scenes\$sceneName"
$nodeCsv = Join-Path $sceneDir "${sceneName}_gv_node.csv"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

function Invoke-Step([string]$label, [string]$python, [string[]]$arguments) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    $clock = [System.Diagnostics.Stopwatch]::StartNew()
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "$label failed (exit code $LASTEXITCODE)." }
    Write-Host ("--- {0} done in {1:N0} s" -f $label, $clock.Elapsed.TotalSeconds) -ForegroundColor DarkGray
}

Write-Host "Prompt: `"$clean`""
Write-Host "Scene:  $sceneName"
Invoke-Step "1/3 Run GPT-2" $obsPython @((Join-Path $here "extract_gpt2.py"), $clean, "--slug", $slug)
Invoke-Step "2/3 Build scene" $gvPython @((Join-Path $here "build_scene.py"), $slug, "--name", $sceneName)
Invoke-Step "3/3 Verify" $gvPython @((Join-Path $here "verify_scene.py"), $nodeCsv)

$run = Get-Content (Join-Path $here "cache\runs\$slug\run.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$last = $run.predictions[$run.predictions.Count - 1]
$guesses = ($last | Select-Object -First 3 | ForEach-Object { "'{0}' {1:P0}" -f $_[0], $_[1] }) -join ", "
Write-Host "`nGPT-2's prediction after the last token: $guesses" -ForegroundColor Green
Write-Host "Open in GlyphViz: $nodeCsv" -ForegroundColor Green
