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
            self.wfile.write(content)
            return

        # Serve static database file trades.json
        if clean_path == "/data/trades.json":
            filepath = "data/archives/trades.jsonl"
            if not os.path.exists(filepath):
                content = b'{"portfolio_history": [], "trades": []}'
            else:
                with open(filepath, "rb") as f:
                    content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
            return

        # Serve static database file ai_analytics_logs.json
        if clean_path == "/data/ai_analytics_logs.json":
            filepath = "data/archives/ai_analytics_logs.jsonl"
            if not os.path.exists(filepath):
                content = b'[]'
            else:
                with open(filepath, "rb") as f:
                    content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
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
            
            # Check Alpaca Key ID / Secret Key connection
            if api_key and secret_key:
                if "your_api" in api_key.lower() or "your_api" in secret_key.lower():
                    alpaca_status = "failed"
                    alpaca_error = "API key or Secret key is using default placeholder values."
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
                    except Exception as e:
                        logger.warning(f"Connection check failed for Alpaca API: {e}")
                        alpaca_error = str(e)

            # Check Gemini Key connection
            if gemini_key:
                if "your_gemini" in gemini_key.lower() or gemini_key.strip() == "":
                    gemini_status = "failed"
                    gemini_error = "Gemini key is missing or using default placeholder value."
                else:
                    try:
                        import google.generativeai as genai
                        genai.configure(api_key=gemini_key.strip())
                        # genai.list_models() is a generator; evaluate the first element to force the API call
                        next(iter(genai.list_models()), None)
                        gemini_status = "connected"
                    except Exception as e:
                        logger.warning(f"Connection check failed for Gemini API: {e}")
                        gemini_error = str(e)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "alpaca": alpaca_status,
                "alpaca_error": alpaca_error,
                "gemini": gemini_status,
                "gemini_error": gemini_error
            }).encode("utf-8"))
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
                self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error saving local synced config: {e}")
                self.send_response(500)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
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
