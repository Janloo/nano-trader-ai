#!/usr/bin/env bash
# ==============================================================================
# start_server.sh - Headless Background HTTP Dashboard Server Launcher
# ==============================================================================

# Exit immediately if any command fails
set -e

# 1. Detect project directory absolute path
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 2. Terminate any pre-existing server instance running on port 8080
echo "Checking for existing servers running on port 8080..."
pkill -f "server.py --port 8080" || true

# Wait a brief moment for cleanup
sleep 1

# Ensure data log folder exists
mkdir -p data

# 3. Start standalone server on host 0.0.0.0 (accessible remotely) and port 8080
echo "Starting Standalone Control Room server on http://0.0.0.0:8080..."
nohup .venv/bin/python server.py --port 8080 --host 0.0.0.0 > data/server.log 2>&1 &

echo "=== Control Room Server Started in Background ==="
echo "Access the dashboard remotely using your server IP address on port 8080."
echo "Logs are available at: data/server.log"
