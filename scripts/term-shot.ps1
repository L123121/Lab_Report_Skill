<#
.SYNOPSIS
    term-shot.ps1 - PowerShell wrapper for term_shot.py
#>
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
$python = Join-Path $repoDir ".venv" "Scripts" "python.exe"
if (Test-Path $python) {
    & $python (Join-Path $scriptDir "term_shot.py") @args
} else {
    & python (Join-Path $scriptDir "term_shot.py") @args
}
