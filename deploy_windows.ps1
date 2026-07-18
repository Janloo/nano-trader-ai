<#
.SYNOPSIS
deploy_windows.ps1 - Automated Windows Task Scheduler Deployment Script for nano-trader-ai

.DESCRIPTION
This script mimics the behavior of deploy_cron.sh for Windows environments.
It checks for the virtual environment and schedules main_macro.py to run every hour.
#>

$ErrorActionPreference = "Stop"
Write-Host "=== Starting Windows Deployment (Task Scheduler Mode) ===" -ForegroundColor Cyan

# 1. Detect project directory
$ProjectDir = $PSScriptRoot
Write-Host "Project Directory: $ProjectDir"
Set-Location -Path $ProjectDir

# 2. Check for or create the Python virtual environment
if (-Not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "Found existing virtual environment (.venv)." -ForegroundColor Green
}

# 3. Define the scheduled task parameters
$TaskName = "NanoTraderAI_MacroCycle"
$ActionPath = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$ActionArg = Join-Path $ProjectDir "main_macro.py"
$WorkingDirectory = $ProjectDir

Write-Host "Setting up Scheduled Task '$TaskName' to run every hour..." -ForegroundColor Yellow

# Remove existing task if it exists
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed previous task."
}

# Create new task
$Action = New-ScheduledTaskAction -Execute $ActionPath -Argument "`"$ActionArg`"" -WorkingDirectory $WorkingDirectory

# Trigger every hour
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)

# Settings (run in background, start when available, etc)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Runs main_macro.py every hour for Nano Trader AI" | Out-Null

Write-Host "Scheduled task successfully registered! main_macro.py will run every hour." -ForegroundColor Green
Write-Host ""
Write-Host "To manage it, open 'Task Scheduler' (Utilit`à di Pianificazione) in Windows." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
