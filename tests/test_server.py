import pytest
from unittest.mock import patch, MagicMock
import urllib.request
import json
import socket
import os
from server import DashboardServer

def test_server_config_and_status_endpoints():
    """Verify that DashboardServer config and status REST endpoints respond correctly."""
    # Find a free TCP port dynamically
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    
    server = DashboardServer(host="127.0.0.1", port=port)
    server.start()
    
    local_creds_path = os.path.join("config", "local_credentials.json")
    # Backup existing local credentials if any
    backup_data = None
    if os.path.exists(local_creds_path):
        with open(local_creds_path, "r", encoding="utf-8") as f:
            backup_data = f.read()
            
    try:
        # 1. Test POST /api/config
        config_payload = {
            "api_key": "unit_test_id",
            "secret_key": "unit_test_secret",
            "base_url": "https://paper-api.alpaca.markets",
            "gemini_key": "unit_test_gemini"
        }
        
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/config",
            data=json.dumps(config_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=5) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            assert res_data["status"] == "success"
            
        # Verify settings were persisted
        assert os.path.exists(local_creds_path)
        with open(local_creds_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
            assert saved["api_key"] == "unit_test_id"

        # 2. Test GET /api/status (mock keys checking should fail)
        status_url = (
            f"http://127.0.0.1:{port}/api/status"
            f"?api_key=unit_test_id&secret_key=unit_test_secret"
            f"&base_url=https://paper-api.alpaca.markets&gemini_key=unit_test_gemini"
        )
        
        with urllib.request.urlopen(status_url, timeout=5) as resp:
            status_data = json.loads(resp.read().decode("utf-8"))
            # Fictional credentials fail validation pings
            assert status_data["alpaca"] == "failed"
            assert status_data["gemini"] == "failed"
            
    finally:
        server.stop()
        # Restore backed up configurations if they existed
        if backup_data is not None:
            with open(local_creds_path, "w", encoding="utf-8") as f:
                f.write(backup_data)
        elif os.path.exists(local_creds_path):
            os.remove(local_creds_path)
