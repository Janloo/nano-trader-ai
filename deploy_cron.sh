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

# ==============================================================================
# 4. Generate Cron-Job configuration
# ==============================================================================
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python3"
MAIN_SCRIPT="$PROJECT_DIR/main_macro.py"
CRON_LOG="$PROJECT_DIR/data/cron.log"

# Ensure data log folder exists
mkdir -p "$PROJECT_DIR/data"

# ------------------------------------------------------------------------------
# Scheduling strategy:
#
# EQUITY HOURS (NYSE): Mon-Fri  09:30-16:00 ET  =  13:30-20:00 UTC (EDT, Apr-Oct)
#                               09:30-16:00 ET  =  14:30-21:00 UTC (EST, Nov-Mar)
#
# We schedule on the :30 of each hour during market hours (UTC):
#   13:30, 14:30, 15:30, 16:30, 17:30, 18:30, 19:30 UTC   (EDT, summer)
#   = cron hours: 13,14,15,16,17,18,19 at minute :30 Mon-Fri
#
# CRYPTO COVERAGE: BTCUSD/ETHUSD trade 24/7 — we run off-hours too once per hour
#   Hours outside equity window: 0,1,2,3,4,5,6,7,8,9,10,11,12,20,21,22,23
#   These will run the DAS bot (equity will be skipped by market hours guard).
# ------------------------------------------------------------------------------

# Equity / market hours: Mon-Fri at :30 during 13:00-20:00 UTC
CRON_EQUITY="30 13,14,15,16,17,18,19 * * 1-5 cd $PROJECT_DIR && $PYTHON_BIN $MAIN_SCRIPT >> $CRON_LOG 2>&1"

# Crypto off-hours: every day at :00 for all hours (bot will skip equities automatically)
CRON_CRYPTO="0 * * * * cd $PROJECT_DIR && $PYTHON_BIN $MAIN_SCRIPT >> $CRON_LOG 2>&1"

# ==============================================================================
# 5. Inject into crontab safely without overwriting other jobs
# ==============================================================================
echo "Updating crontab entries..."
(
    crontab -l 2>/dev/null | grep -Fv "main.py" | grep -Fv "main_macro.py"
    echo "# nano-trader-ai: NYSE market hours (Mon-Fri, 13:30-19:30 UTC)"
    echo "$CRON_EQUITY"
    echo "# nano-trader-ai: Crypto 24/7 off-hours coverage"
    echo "$CRON_CRYPTO"
) | crontab -

# ==============================================================================
# 6. Launch Real-time WebSocket Executor in background
# ==============================================================================
echo "Checking WebSocket executor background process..."
WS_PID_FILE="$PROJECT_DIR/data/realtime_executor.pid"
WS_LOG_FILE="$PROJECT_DIR/data/realtime_executor.log"

# Kill any existing instances
if [ -f "$WS_PID_FILE" ]; then
    OLD_PID=$(cat "$WS_PID_FILE")
    if kill -0 $OLD_PID >/dev/null 2>&1; then
        echo "Stopping existing WebSocket executor (PID: $OLD_PID)..."
        kill $OLD_PID || kill -9 $OLD_PID
    fi
    rm -f "$WS_PID_FILE"
fi

# Launch new instance
echo "Starting WebSocket executor in background..."
nohup $PYTHON_BIN "$PROJECT_DIR/realtime_executor.py" > "$WS_LOG_FILE" 2>&1 &
echo $! > "$WS_PID_FILE"
echo "WebSocket executor started with PID: $(cat "$WS_PID_FILE")"

echo ""
echo "=== Deployment Completed Successfully ==="
echo ""
echo "Cron Jobs registered:"
echo "  [EQUITY]  $CRON_EQUITY"
echo "  [CRYPTO]  $CRON_CRYPTO"
echo ""
echo "Background WebSocket Executor:"
echo "  PID File: $WS_PID_FILE"
echo "  Log File: $WS_LOG_FILE"
echo ""
echo "Verify status with:"
echo "  crontab -l"
echo "  ps -p \$(cat $WS_PID_FILE)"
