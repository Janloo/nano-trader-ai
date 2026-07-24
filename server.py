import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from config.settings import logger

class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default server logs in terminal to keep outputs clean
        pass

    def handle_error(self, request, client_address):
        """Suppress BrokenPipe/ConnectionReset errors — client simply closed the tab."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return  # Silently ignore — browser closed before response was complete
        super().handle_error(request, client_address)

    def _safe_write(self, data: bytes):
        """Write response bytes, silently ignoring disconnected clients."""
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split("?")[0]
        
        # Serve analytics
        if clean_path == "/analytics":
            filepath = "analytics.html"
            if not os.path.exists(filepath):
                self.send_error(404, "analytics.html not found")
                return
            try:
                with open(filepath, "rb") as f:
                    file_content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(file_content)
            except Exception as e:
                self.send_error(500, f"Server error: {e}")
            return

        # Serve dashboard
        if clean_path in ["/", "/dashboard.html"]:
            filepath = "dashboard.html"
            if not os.path.exists(filepath):
                self.send_error(404, "dashboard.html not found")
                return
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(content)
            return

        # Serve checkpoints
        if clean_path == "/data/checkpoints.json":
            filepath = "data/archives/daily_checkpoints.json"
            if not os.path.exists(filepath):
                content = b'[]'
            else:
                with open(filepath, "rb") as f:
                    content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(content)
            return

        # Serve static database file trades.json
        if clean_path == "/data/trades.json":
            try:
                from data.db import get_trades
                content = json.dumps(get_trades(limit=500)).encode("utf-8")
            except Exception:
                content = b'[]'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(content)
            return

        # Serve static database file ai_analytics_logs.json
        if clean_path == "/data/ai_analytics_logs.json":
            try:
                from data.db import get_ai_analytics
                content = json.dumps(get_ai_analytics(limit=500)).encode("utf-8")
            except Exception:
                content = b'[]'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(content)
            return

        # Connection health checks
        if clean_path == "/api/status":
            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)
            
            api_key = params.get("api_key", [None])[0]
            secret_key = params.get("secret_key", [None])[0]
            base_url = params.get("base_url", ["https://paper-api.alpaca.markets"])[0]
            gemini_key = params.get("gemini_key", [None])[0]
            
            alpaca_status = "failed"
            alpaca_error = ""
            gemini_status = "failed"
            gemini_error = ""
            
            cache_file = os.path.join("data", "state", "api_key_cache.json")
            cache_data = {}
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                except Exception:
                    pass
            
            # Check Alpaca Key ID / Secret Key connection
            if api_key and secret_key:
                if "your_api" in api_key.lower() or "your_api" in secret_key.lower():
                    alpaca_status = "failed"
                    alpaca_error = "API key or Secret key is using default placeholder values."
                else:
                    cache_key_alpaca = f"{api_key}:{secret_key}:{base_url}"
                    if cache_data.get("alpaca_key") == cache_key_alpaca and cache_data.get("alpaca_status") == "connected":
                        alpaca_status = "connected"
                    else:
                        try:
                            from alpaca.trading.client import TradingClient
                            is_paper = "paper" in base_url.lower()
                            tc = TradingClient(
                                api_key=api_key.strip(),
                                secret_key=secret_key.strip(),
                                paper=is_paper,
                                url_override=base_url.strip()
                            )
                            tc.get_account()
                            alpaca_status = "connected"
                            cache_data["alpaca_key"] = cache_key_alpaca
                            cache_data["alpaca_status"] = "connected"
                        except Exception as e:
                            logger.warning(f"Connection check failed for Alpaca API: {e}")
                            alpaca_error = str(e)
                            cache_data["alpaca_key"] = cache_key_alpaca
                            cache_data["alpaca_status"] = "failed"

            # Check Gemini Key connection
            if gemini_key:
                if "your_gemini" in gemini_key.lower() or gemini_key.strip() == "":
                    gemini_status = "failed"
                    gemini_error = "Gemini key is missing or using default placeholder value."
                else:
                    if cache_data.get("gemini_key") == gemini_key and cache_data.get("gemini_status") == "connected":
                        gemini_status = "connected"
                    else:
                        try:
                            from google import genai
                            client = genai.Client(api_key=gemini_key.strip())
                            # list_models() returns an iterator; evaluate the first element to force the API call
                            next(client.models.list(), None)
                            gemini_status = "connected"
                            cache_data["gemini_key"] = gemini_key
                            cache_data["gemini_status"] = "connected"
                        except Exception as e:
                            logger.warning(f"Connection check failed for Gemini API: {e}")
                            gemini_error = str(e)
                            cache_data["gemini_key"] = gemini_key
                            cache_data["gemini_status"] = "failed"

            try:
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache_data, f)
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(json.dumps({
                "alpaca": alpaca_status,
                "alpaca_error": alpaca_error,
                "gemini": gemini_status,
                "gemini_error": gemini_error
            }).encode("utf-8"))
            return

        if clean_path == "/api/risk-settings":
            filepath = os.path.join("config", "risk_settings.json")
            if not os.path.exists(filepath):
                content = b'{}'
            else:
                with open(filepath, "rb") as f:
                    content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(content)
            return

        
        # Serve paginated HTML rows for lazy loading
        
        # Serve Performance Comparison Data
        if self.path.startswith("/api/performance_comparison"):
            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)
            asset = params.get("asset", ["ALL"])[0]
            
            from data.db import get_db
            with get_db() as conn:
                cursor = conn.cursor()
                
                # Fetch Real Logs
                if asset == "ALL":
                    cursor.execute("SELECT timestamp, return_1h, return_4h FROM ai_analytics WHERE action NOT LIKE 'SHADOW_%' AND return_1h IS NOT NULL ORDER BY timestamp ASC")
                else:
                    cursor.execute("SELECT timestamp, return_1h, return_4h FROM ai_analytics WHERE action NOT LIKE 'SHADOW_%' AND return_1h IS NOT NULL AND asset = ? ORDER BY timestamp ASC", (asset,))
                real_logs = [dict(row) for row in cursor.fetchall()]
                
                # Fetch Shadow Logs
                if asset == "ALL":
                    cursor.execute("SELECT timestamp, return_1h, return_4h FROM ai_analytics WHERE action LIKE 'SHADOW_%' AND return_1h IS NOT NULL ORDER BY timestamp ASC")
                else:
                    cursor.execute("SELECT timestamp, return_1h, return_4h FROM ai_analytics WHERE action LIKE 'SHADOW_%' AND return_1h IS NOT NULL AND asset = ? ORDER BY timestamp ASC", (asset,))
                shadow_logs = [dict(row) for row in cursor.fetchall()]
                
            # Process Real Logs
            def simulate_portfolio(logs, starting_equity=100000.0, max_alloc_pct=0.15):
                from datetime import datetime, timedelta
                cash = starting_equity
                equity = starting_equity
                active_trades = []
                curve = []
                wins = 0
                executed = 0
                
                for log in logs:
                    ret = log.get('return_1h')
                    if ret is None:
                        continue
                        
                    current_time = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
                    
                    # Free up cash from exited trades
                    still_active = []
                    for trade in active_trades:
                        if trade['exit_time'] <= current_time:
                            cash += trade['invested'] + trade['profit']
                            equity += trade['profit']
                        else:
                            still_active.append(trade)
                    active_trades = still_active

                    # Allocate new trade if cash > 1000
                    if cash >= 1000:
                        alloc = min(cash, starting_equity * max_alloc_pct)
                        cash -= alloc
                        profit = alloc * (ret / 100.0)
                        active_trades.append({
                            'exit_time': current_time + timedelta(hours=1),
                            'invested': alloc,
                            'profit': profit
                        })
                        executed += 1
                        if ret > 0: wins += 1
                        
                    # Calculate current equity (realized + unrealized)
                    current_equity = cash + sum(t['invested'] + t['profit'] for t in active_trades)
                    pnl_pct = ((current_equity - starting_equity) / starting_equity) * 100.0
                    curve.append({'x': log['timestamp'], 'y': round(pnl_pct, 2)})

                # Close remaining
                for trade in active_trades:
                    equity += trade['profit']
                
                final_pnl = ((equity - starting_equity) / starting_equity) * 100.0
                win_rate = (wins / executed * 100) if executed > 0 else 0
                return curve, win_rate, executed, final_pnl

            # Read dynamic allocation from risk config
            max_alloc_pct = 0.15
            try:
                with open('data/state/risk_config.json', 'r') as f:
                    rconfig = json.load(f)
                    max_alloc_pct = rconfig.get('max_capital_per_trade_pct', 0.15)
            except:
                pass

            real_curve, real_win_rate, real_trades, real_pnl = simulate_portfolio(real_logs, max_alloc_pct=max_alloc_pct)
            shadow_curve, shadow_win_rate, shadow_trades, shadow_pnl = simulate_portfolio(shadow_logs, max_alloc_pct=max_alloc_pct)
            
            result = {
                "real": {
                    "curve": real_curve,
                    "win_rate": round(real_win_rate, 2),
                    "total_trades": len(real_logs),
                    "final_pnl": round(real_pnl, 2)
                },
                "shadow": {
                    "curve": shadow_curve,
                    "win_rate": round(shadow_win_rate, 2),
                    "total_trades": len(shadow_logs),
                    "final_pnl": round(shadow_pnl, 2)
                }
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(json.dumps(result).encode("utf-8"))
            return

        if self.path.startswith("/api/logs_html?"):
            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)
            log_type = params.get("type", [""])[0]
            offset = int(params.get("offset", ["0"])[0])
            limit = int(params.get("limit", ["20"])[0])
            
            from reporting.generator import get_trades_rows_html, get_ai_rows_html, get_shadow_rows_html
            
            html_output = ""
            if log_type == "trades":
                html_output = get_trades_rows_html(offset, limit)
            elif log_type == "ai":
                html_output = get_ai_rows_html(offset, limit)
            elif log_type == "shadow":
                html_output = get_shadow_rows_html(offset, limit)
                
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(html_output.encode("utf-8"))
            return

        if clean_path == "/api/dashboard_fragments":
            try:
                from reporting.generator import get_dashboard_data
                from data.db import get_portfolio_history
                
                data = get_dashboard_data()
                history = get_portfolio_history(limit=500)
                starting_equity = data.get('starting_equity', 0)
                
                data['portfolio_times'] = [h['timestamp'] for h in history]
                data['portfolio_pnl'] = [h['equity'] - starting_equity for h in history]
                data['portfolio_sentiment'] = [h.get('average_sentiment', 0.0) for h in history]
                
                content = json.dumps(data).encode("utf-8")
            except Exception as e:
                import traceback
                logger.error(f"Error building dashboard fragments: {e}\n{traceback.format_exc()}")
                content = b'{}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self._safe_write(content)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/config":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                config_data = json.loads(post_data.decode('utf-8'))
                
                config_path = os.path.join("config", "local_credentials.json")
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4)
                    
                logger.info("Local configuration sync complete from dashboard settings.")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(json.dumps({"status": "success"}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error saving local synced config: {e}")
                self.send_response(500)
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        if self.path == "/api/risk-settings":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                risk_data = json.loads(post_data.decode('utf-8'))
                
                config_path = os.path.join("config", "risk_settings.json")
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(risk_data, f, indent=4)
                    
                logger.info("Risk settings updated from dashboard.")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(json.dumps({"status": "success"}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error saving risk settings: {e}")
                self.send_response(500)
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        if self.path == "/api/close-position":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                req_data = json.loads(post_data.decode('utf-8'))
                
                symbol = req_data.get("symbol")
                api_key = req_data.get("api_key")
                secret_key = req_data.get("secret_key")
                base_url = req_data.get("base_url")
                
                if not all([symbol, api_key, secret_key]):
                    raise ValueError("Missing symbol or credentials")

                from alpaca.trading.client import TradingClient
                is_paper = "paper" in base_url.lower() if base_url else True
                tc = TradingClient(api_key=api_key.strip(), secret_key=secret_key.strip(), paper=is_paper, url_override=base_url.strip() if base_url else None)
                
                from alpaca.trading.requests import GetOrdersRequest
                from alpaca.trading.enums import QueryOrderStatus
                
                # First cancel any open orders for this symbol
                req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
                open_orders = tc.get_orders(filter=req)
                for order in open_orders:
                    tc.cancel_order_by_id(order.id)
                    logger.info(f"Dashboard cancelled open order {order.id} for {symbol}")
                
                tc.close_position(symbol_or_asset_id=symbol)
                logger.info(f"Dashboard manually closed position for {symbol}")
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(json.dumps({"status": "success"}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error closing position {req_data.get('symbol', 'unknown')}: {e}")
                self.send_response(500)
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_error(404, "Not Found")

class DashboardServer:
    def __init__(self, host="127.0.0.1", port=8000):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        def serve():
            self.server = HTTPServer((self.host, self.port), DashboardHTTPHandler)
            self.server.serve_forever()

        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()
        logger.info(f"Control Room HTTP backend server listening on http://{self.host}:{self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Control Room HTTP server stopped.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Standalone Control Room HTTP Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to listen on (default: 0.0.0.0)")
    args = parser.parse_args()
    
    server = HTTPServer((args.host, args.port), DashboardHTTPHandler)
    logger.info(f"Standalone Control Room HTTP server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Standalone Control Room HTTP server...")
        server.shutdown()
        server.server_close()
