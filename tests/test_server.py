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


def test_server_api_risk_settings_merge():
    """Verify that POST to /api/risk-settings merges the payload with existing settings instead of full overwrite."""
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    
    server = DashboardServer(host="127.0.0.1", port=port)
    server.start()
    
    risk_settings_path = os.path.join("config", "risk_settings.json")
    
    # Backup existing settings
    backup_data = None
    if os.path.exists(risk_settings_path):
        with open(risk_settings_path, "r", encoding="utf-8") as f:
            backup_data = f.read()
    
    try:
        # Create an initial mock config file
        initial_config = {
            "strategy_vwap_enabled": False,
            "max_risk_per_trade_pct": 0.1,
            "other_vital_setting": "do_not_delete_me"
        }
        os.makedirs("config", exist_ok=True)
        with open(risk_settings_path, "w", encoding="utf-8") as f:
            json.dump(initial_config, f)
            
        # Send a partial update
        update_payload = {
            "strategy_vwap_enabled": True,
            "crypto_max_grid_layers": 10
        }
        
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/risk-settings",
            data=json.dumps(update_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=5) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            assert res_data["status"] == "success"
            
        # Verify the file was merged, not overwritten
        with open(risk_settings_path, "r", encoding="utf-8") as f:
            updated_config = json.load(f)
            
        assert updated_config["strategy_vwap_enabled"] == True, "VWAP should be updated"
        assert updated_config["crypto_max_grid_layers"] == 10, "New field should be added"
        assert updated_config.get("other_vital_setting") == "do_not_delete_me", "Pre-existing fields should NOT be deleted!"
            
    finally:
        server.stop()
        if backup_data is not None:
            with open(risk_settings_path, "w", encoding="utf-8") as f:
                f.write(backup_data)
        elif os.path.exists(risk_settings_path):
            os.remove(risk_settings_path)


def test_generator_exposed_capital():
    """Verify that get_dashboard_data correctly calculates exposed capital based on hft_budget_pct."""
    from reporting.generator import get_dashboard_data
    from unittest.mock import patch
    
    risk_settings_path = os.path.join("config", "risk_settings.json")
    
    # Backup existing settings
    backup_data = None
    if os.path.exists(risk_settings_path):
        with open(risk_settings_path, "r", encoding="utf-8") as f:
            backup_data = f.read()
            
    try:
        # Create an initial mock config file with 50% budget
        mock_config = {
            "hft_budget_pct": 0.5
        }
        os.makedirs("config", exist_ok=True)
        with open(risk_settings_path, "w", encoding="utf-8") as f:
            json.dump(mock_config, f)
            
        # Mock database portfolio history
        mock_history = [
            {"timestamp": "2026-08-01T10:00:00", "equity": 100000.00, "buying_power": 400000.00, "unrealized_pnl": 0.00},
            {"timestamp": "2026-08-01T11:00:00", "equity": 105000.00, "buying_power": 400000.00, "unrealized_pnl": 5000.00}
        ]
        
        with patch('data.db.get_portfolio_history', return_value=mock_history):
            with patch('data.db.get_trades', return_value=[]):
                with patch('data.db.get_ai_analytics', return_value=[]):
                    data = get_dashboard_data()
                    
        # Total equity is 105000
        assert data['current_equity'] == 105000.00
        # Allocated should be 105000 * 0.5 = 52500
        assert data['allocated_capital'] == 52500.00
        # PnL is 5000. Starting allocated capital was 100000 * 0.5 = 50000
        # PnL pct should be (5000 / 50000) * 100 = 10.0%
        assert data['pnl_pct'] == 10.0
        
    finally:
        if backup_data is not None:
            with open(risk_settings_path, "w", encoding="utf-8") as f:
                f.write(backup_data)
        elif os.path.exists(risk_settings_path):
            os.remove(risk_settings_path)
