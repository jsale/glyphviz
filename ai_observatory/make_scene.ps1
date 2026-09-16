<#
.SYNOPSIS
  AI Observatory: turn one prompt into a GlyphViz scene, in one line.

.DESCRIPTION
  Runs the three steps in order and stops at the first failure:
    1. extract.py       (observatory env)  run the model on the prompt
    2. build_scene.py   (glyphviz env)     write the scene folder
    3. verify_scene.py  (glyphviz env)     check it through GlyphViz's loaders

  The scene lands in ai_observatory\scenes\AI_Observatory_GPT2_<Name>\ (or
  AI_Observatory_Gemma_<Name>\ with -Model gemma-2-2b-it); drag its
  _gv_node.csv into GlyphViz.

  Works from any folder. Finds each conda env's python.exe on its own
  (anaconda3, .conda or miniconda3 under your user folder); set
  $env:OBSERVATORY_PYTHON / $env:GLYPHVIZ_PYTHON to override.

.PARAMETER Model
  gpt2-small (default) or gemma-2-2b-it. Gemma needs a Hugging Face login
  that has accepted the Gemma license.

.PARAMETER Chat
  Send the prompt as a chat message (instruction-tuned models only). The scene
  then ends at the moment the model starts its reply.

.EXAMPLE
  .\ai_observatory\make_scene.ps1 "The Eiffel Tower is in the city of" Eiffel

.EXAMPLE
  .\ai_observatory\make_scene.ps1 "Who are you? Please answer in pirate-speak." Pirate -Model gemma-2-2b-it -Chat

.NOTES
  Without -Chat, stop the prompt right before the word you want the model to
  produce, with no trailing space. Each token adds about 1.2 s (GPT-2) or
  1.6 s (Gemma) of animation; 5-25 tokens is comfortable.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Prompt,
    [Parameter(Mandatory = $true, Position = 1)][string]$Name,
    [ValidateSet("gpt2-small", "gemma-2-2b-it")][string]$Model = "gpt2-small",
    [switch]$Chat
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
# (word tokens carry their leading space).
$clean = $Prompt.TrimEnd()
if ($clean -ne $Prompt) { Write-Host "Note: removed trailing whitespace from the prompt." -ForegroundColor Yellow }
if (-not $clean) { throw "The prompt is empty." }
if ($Chat -and $Model -eq "gpt2-small") { throw "-Chat needs an instruction-tuned model, e.g. -Model gemma-2-2b-it." }

$prefix = if ($Model -eq "gpt2-small") { "AI_Observatory_GPT2" } else { "AI_Observatory_Gemma" }
$runsSub = if ($Model -eq "gpt2-small") { "" } else { $Model }
$modelLabel = if ($Model -eq "gpt2-small") { "GPT-2" } else { "Gemma" }

$safe = ($Name -replace '[^A-Za-z0-9_-]', '_').Trim('_')
if (-not $safe) { throw "Name '$Name' has no usable characters." }
if ($safe -like "AI_Observatory_*") { $sceneName = $safe } else { $sceneName = "${prefix}_$safe" }
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

$extractArgs = @((Join-Path $here "extract.py"), $clean, "--model", $Model, "--slug", $slug)
if ($Chat) { $extractArgs += "--chat" }

Write-Host "Prompt: `"$clean`""
Write-Host "Model:  $Model$(if ($Chat) { ' (chat)' })"
Write-Host "Scene:  $sceneName"
Invoke-Step "1/3 Run $modelLabel" $obsPython $extractArgs
Invoke-Step "2/3 Build scene" $gvPython @((Join-Path $here "build_scene.py"), $slug, "--model", $Model, "--name", $sceneName)
Invoke-Step "3/3 Verify" $gvPython @((Join-Path $here "verify_scene.py"), $nodeCsv)

$runDir = if ($runsSub) { Join-Path $here "cache\runs\$runsSub\$slug" } else { Join-Path $here "cache\runs\$slug" }
$run = Get-Content (Join-Path $runDir "run.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$last = $run.predictions[$run.predictions.Count - 1]
$guesses = ($last | Select-Object -First 3 | ForEach-Object { "'{0}' {1:P0}" -f $_[0], $_[1] }) -join ", "
Write-Host "`n${modelLabel}'s prediction after the last token: $guesses" -ForegroundColor Green
Write-Host "Open in GlyphViz: $nodeCsv" -ForegroundColor Green
