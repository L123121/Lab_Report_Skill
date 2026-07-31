<#
.SYNOPSIS
    Computer Lab Report Skill - install screenshot dependencies
#>
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path (Join-Path $scriptDir ".venv"))) {
    Write-Host "Creating virtual environment..."
    & python -m venv (Join-Path $scriptDir ".venv")
}

$python = Join-Path $scriptDir ".venv" "Scripts" "python.exe"
$pip = Join-Path $scriptDir ".venv" "Scripts" "pip.exe"
Write-Host "Installing Python dependencies..."
& $pip install -r (Join-Path $scriptDir "requirements.txt")

Write-Host ""
Write-Host "Screenshot and terminal-capture dependencies installed."
Write-Host ""
Write-Host "Recommended usage:"
Write-Host "  $python $scriptDir\scripts\code_shot.py --help"
Write-Host "  $python $scriptDir\scripts\term_shot.py --help"
Write-Host "  $python $scriptDir\scripts\docx_format_guard.py --help"
Write-Host ""
Write-Host "DOCX editing is provided by the host Agent environment; format verification is bundled."
