@echo off
setlocal
if "%~1"=="" (
    echo Error: Please provide a note for the benchmark.
    echo Usage: run_benchmark.bat "Your modification note"
    echo Example: run_benchmark.bat "Baseline test"
    exit /b 1
)
.\.venv\Scripts\python.exe benchmark.py --note "%~1"
.\.venv\Scripts\python.exe benchmark.py --view
