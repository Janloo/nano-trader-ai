#!/usr/bin/env bash
# ==============================================================================
# deploy_cron.sh - Automated Linux Cron-Job Deployment Script for nano-trader-ai
# ==============================================================================

# Exit immediately if any command fails
set -e

echo "=== Starting Headless Deployment (Cron-Job Mode) ==="

# 1. Detect project directory absolute path
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Project Directory: $PROJECT_DIR"
cd "$PROJECT_DIR"

# 2. Check for or create the Python virtual environment
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    if command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "Error: Python is not installed or not found in system PATH." >&2
        exit 1
    fi
fi

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment (.venv) using $PYTHON_CMD..."
    $PYTHON_CMD -m venv .venv
else
    echo "Virtual environment (.venv) already exists."
fi

# 3. Upgrade pip and install dependencies
echo "Installing dependencies from requirements.txt..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 4. Generate Cron-Job configuration
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
MAIN_SCRIPT="$PROJECT_DIR/main.py"
CRON_LOG="$PROJECT_DIR/data/cron.log"

# Ensure data log folder exists
mkdir -p "$PROJECT_DIR/data"

# Setup the cron line to run hourly
CRON_JOB="0 * * * * cd $PROJECT_DIR && $PYTHON_BIN $MAIN_SCRIPT >> $CRON_LOG 2>&1"

# 5. Inject into crontab safely without overwriting other jobs
echo "Updating crontab entries..."
# Retrieve current cron jobs, filter out any existing lines for this project's main.py, append the new job
(crontab -l 2>/dev/null | grep -Fv "$MAIN_SCRIPT"; echo "$CRON_JOB") | crontab -

echo "=== Deployment Completed Successfully ==="
echo "Cron Job set to run hourly:"
echo "  $CRON_JOB"
echo "Log file destination:"
echo "  $CRON_LOG"
