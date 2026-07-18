import json
import os
from datetime import datetime


def read_jsonl(filepath):
    data = []
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
        except Exception as e:
            print(f"Error reading jsonl {filepath}: {e}")
    return data

def generate_dashboard():
    """Reads trades.json and ai_analytics_logs.json to auto-generate an interactive Control Room HTML dashboard."""
    json_path = os.path.join("data", "archives", "trades.jsonl")
    analytics_path = os.path.join("data", "archives", "ai_analytics_logs.jsonl")
    html_path = "dashboard.html"

    # Default structures
    data = {"portfolio_history": [], "trades": []}
    ai_logs = []

    portfolio_path = os.path.join("data", "archives", "portfolio_history.jsonl")
    data["trades"] = read_jsonl(json_path)
    data["portfolio_history"] = read_jsonl(portfolio_path)

    ai_logs = read_jsonl(analytics_path)

    ws_triggers = []
    ws_triggers_path = os.path.join("data", "state", "ws_triggers.json")
    if os.path.exists(ws_triggers_path):
        try:
            with open(ws_triggers_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    ws_triggers = json.loads(content)
        except Exception as e:
            print(f"Error loading ws_triggers.json for reporting: {e}")

    price_history = {}
    price_history_path = os.path.join("data", "state", "realtime_price_history.json")
    if os.path.exists(price_history_path):
        try:
            with open(price_history_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    price_history = json.loads(content)
        except Exception as e:
            print(f"Error loading realtime_price_history.json for reporting: {e}")

    history = data.get("portfolio_history", [])
    trades = data.get("trades", [])

    current_equity = 100000.00
    current_buying_power = 400000.00
    current_unrealized_pnl = 0.00
    starting_equity = 100000.00
    cumulative_pnl = 0.00
    pnl_pct = 0.00

    if history:
        last_snap = history[-1]
        current_equity = last_snap.get("equity", 100000.00)
        current_buying_power = last_snap.get("buying_power", 400000.00)
        current_unrealized_pnl = last_snap.get("unrealized_pnl", 0.00)
        
        starting_snap = history[0]
        starting_equity = starting_snap.get("equity", 100000.00)
        cumulative_pnl = current_equity - starting_equity
        pnl_pct = (cumulative_pnl / starting_equity) * 100.0 if starting_equity > 0 else 0.0

    # Build Trades History HTML Rows
    trades_rows = []
    if trades:
        for t in reversed(trades):
            # Match feedback loop metrics for display
            feedback_str = "<span class='text-slate-500 font-semibold'>No Trade</span>"
            for log in ai_logs:
                log_time = log.get("timestamp", "")
                trade_time = t.get("timestamp", "")
                if log.get("asset") == t["symbol"] and log_time and trade_time:
                    try:
                        t_diff = abs((datetime.fromisoformat(log_time.replace("Z", "+00:00")) - datetime.fromisoformat(trade_time.replace("Z", "+00:00"))).total_seconds())
                        if t_diff < 120:  # matches within 2 minutes
                            fb = log.get("feedback_loop_metric", {})
                            ret_1h = fb.get("return_1h")
                            ret_4h = fb.get("return_4h")
                            parts = []
                            if ret_1h is not None:
                                parts.append(f"+1h: <span class='{'text-emerald-400' if ret_1h >= 0 else 'text-rose-400'} font-mono font-bold'>{ret_1h:+.2f}%</span>")
                            if ret_4h is not None:
                                parts.append(f"+4h: <span class='{'text-emerald-400' if ret_4h >= 0 else 'text-rose-400'} font-mono font-bold'>{ret_4h:+.2f}%</span>")
                            if parts:
                                feedback_str = " / ".join(parts)
                            else:
                                feedback_str = "<span class='text-yellow-500 font-semibold'>Awaiting (+1h)</span>"
                            break
                    except Exception:
                        pass

            exec_type = t.get("execution_type", "cron_macro")
            if exec_type == "hybrid_websocket_trigger":
                type_badge = '<span class="ml-2 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">⚡ WS Trigger</span>'
            else:
                type_badge = '<span class="ml-2 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">Cron Macro</span>'

            trades_rows.append(f"""
            <tr class="hover:bg-slate-900/20 transition-colors">
                <td class="py-3.5 text-slate-400 font-mono text-xs">{datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")}</td>
                <td class="py-3.5"><span class="font-bold text-white">{t["symbol"]}</span></td>
                <td class="py-3.5">
                    <span class="inline-flex items-center rounded-md px-2 py-1 text-xs font-semibold border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                        BUY
                    </span>
                    {type_badge}
                </td>
                <td class="py-3.5 text-right font-mono">{t["qty"]:.6f}</td>
                <td class="py-3.5 text-right font-mono">${t["price"]:.2f}</td>
                <td class="py-3.5 text-right font-mono">${t["notional"]:.2f}</td>
                <td class="py-3.5 text-center font-mono">
                    <span class="px-2 py-0.5 rounded text-xs font-bold {{
                        'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' if t.get('sentiment_score', 0) > 0
                        else 'bg-rose-500/10 text-rose-400 border border-rose-500/20' if t.get('sentiment_score', 0) < 0
                        else 'bg-slate-500/10 text-slate-400 border border-slate-500/20'
                    }}">
                        {t.get('sentiment_score', 0.0):+.2f}
                    </span>
                </td>
                <td class="py-3.5 text-center text-xs">{feedback_str}</td>
                <td class="py-3.5 pl-4 text-slate-400 max-w-[200px] truncate" title="{t.get('reasoning', '')}">{t.get('reasoning', 'N/A')}</td>
            </tr>
            """)
    else:
        trades_rows.append('<tr><td colspan="9" class="py-6 text-center text-slate-500">No executing trades found.</td></tr>')

    # Build AI Telemetry logs HTML Rows
    ai_rows = []
    if ai_logs:
        for log in reversed(ai_logs):
            output = log.get("ai_raw_output", {})
            action = output.get("action", "HOLD").upper()
            confidence = output.get("confidence", 0)
            score = output.get("sentiment_score", 0.0)
            
            fb = log.get("feedback_loop_metric", {})
            ret_1h = fb.get("return_1h")
            ret_4h = fb.get("return_4h")
            parts = []
            if ret_1h is not None:
                parts.append(f"+1h: <span class='{'text-emerald-400' if ret_1h >= 0 else 'text-rose-400'} font-bold'>{ret_1h:+.2f}%</span>")
            if ret_4h is not None:
                parts.append(f"+4h: <span class='{'text-emerald-400' if ret_4h >= 0 else 'text-rose-400'} font-bold'>{ret_4h:+.2f}%</span>")
            feedback_loop_str = " / ".join(parts) if parts else "Awaiting (+1h)"
            
            # Format raw news titles as a tooltip list
            titles = log.get("raw_news_titles", [])
            titles_str = " | ".join(titles) if titles else "No news articles found."
            
            ai_rows.append(f"""
            <tr class="hover:bg-slate-900/20 transition-colors">
                <td class="py-3.5 text-slate-400 font-mono text-xs">{datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")}</td>
                <td class="py-3.5"><span class="font-bold text-white">{log["asset"]}</span></td>
                <td class="py-3.5 text-right font-mono">${log["price"]:.2f}</td>
                <td class="py-3.5 text-center">
                    <span class="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold border {
                        'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' if action == 'BUY'
                        else 'bg-rose-500/10 text-rose-400 border-rose-500/20' if action == 'SELL'
                        else 'bg-slate-500/10 text-slate-400 border-slate-500/20'
                    }">
                        {action}
                    </span>
                </td>
                <td class="py-3.5 text-center font-mono">{confidence}%</td>
                <td class="py-3.5 text-center text-xs">{feedback_loop_str}</td>
                <td class="py-3.5 pl-4 text-slate-400 max-w-[280px] truncate" title="{titles_str}">{titles_str}</td>
            </tr>
            """)
    else:
        ai_rows.append('<tr><td colspan="7" class="py-6 text-center text-slate-500">No AI decision logs found.</td></tr>')


    # 3. Read and format human-readable logbook entries
    logbook_rows = []
    logbook_path = os.path.join("data", "archives", "human_logbook.txt")
    if os.path.exists(logbook_path):
        try:
            with open(logbook_path, "r", encoding="utf-8") as f:
                logbook_entries = f.readlines()
            
            # Show latest 15 logs first
            for log in reversed(logbook_entries[-15:]):
                log = log.strip()
                if not log:
                    continue
                
                # Check for diagnostics tags and color code them accordingly
                if "[API WARNING]" in log:
                    text_class = "text-amber-400"
                    badge = '<span class="px-2 py-0.5 text-[10px] font-bold bg-amber-500/10 text-amber-400 rounded border border-amber-500/20 uppercase tracking-wider">Warning</span>'
                elif "[WEEKEND]" in log:
                    text_class = "text-blue-400"
                    badge = '<span class="px-2 py-0.5 text-[10px] font-bold bg-blue-500/10 text-blue-400 rounded border border-blue-500/20 uppercase tracking-wider">Weekend</span>'
                else:
                    text_class = "text-slate-300"
                    badge = '<span class="px-2 py-0.5 text-[10px] font-bold bg-slate-500/10 text-slate-400 rounded border border-slate-500/20 uppercase tracking-wider">Info</span>'
                
                logbook_rows.append(f"""
                <div class="py-3 flex items-start gap-3 border-b border-slate-800/40 last:border-b-0">
                    <div class="flex-shrink-0 mt-0.5">{badge}</div>
                    <div class="{text_class} text-sm font-medium">{log}</div>
                </div>
                """)
        except Exception as e:
            logger.error(f"Error reading human logbook: {e}")
            
    if not logbook_rows:
        logbook_rows.append('<div class="py-6 text-center text-slate-500 text-sm">No logbook diagnostics recorded yet.</div>')

    # 4. Load AI Live Market Bias data
    daily_selection = {"target_assets": [], "timestamp": "", "macro_articles_analyzed": 0}
    selection_path = os.path.join("data", "state", "market_bias.json")
    if os.path.exists(selection_path):
        try:
            with open(selection_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    daily_selection = json.loads(content)
        except Exception as e:
            print(f"Error loading market_bias.json: {e}")

    # 4.5 Load Market News Feed
    market_news = []
    news_path = "market_news.json"
    if os.path.exists(news_path):
        try:
            with open(news_path, "r", encoding="utf-8") as f:
                market_news = json.load(f)
        except Exception as e:
            print(f"Error loading market_news.json: {e}")

    # Build News Feed HTML
    news_feed_html = ""
    for article in market_news:
        source = article.get("source", "News")
        title = article.get("title", "")
        summary = article.get("summary", "")
        link = article.get("link", "#")
        timestamp_str = article.get("timestamp", "")
        
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            time_formatted = dt.strftime("%Y-%m-%d %H:%M")
        except:
            time_formatted = timestamp_str

        is_alpaca = "Alpaca" in source
        source_color = "text-indigo-400 border-indigo-500/20 bg-indigo-500/10" if is_alpaca else "text-blue-400 border-blue-500/20 bg-blue-500/10"

        news_feed_html += f"""
        <div class="py-3 border-b border-slate-800/40 last:border-0">
            <div class="flex items-center justify-between mb-1">
                <span class="px-2 py-0.5 text-[10px] font-bold {source_color} rounded border uppercase tracking-wider">{source}</span>
                <span class="text-xs text-slate-500 font-mono">{time_formatted}</span>
            </div>
            <a href="{link}" target="_blank" class="text-sm font-semibold text-slate-200 hover:text-white hover:underline block mb-1">
                {title}
            </a>
            <p class="text-xs text-slate-400 line-clamp-2">
                {summary}
            </p>
        </div>
        """
        
    if not news_feed_html:
        news_feed_html = '<div class="py-6 text-center text-slate-500 text-sm">No recent news fetched.</div>'

    # Build DAS selection cards HTML
    das_cards_html = ""
    das_selected_assets = daily_selection.get("target_assets", [])
    das_timestamp = daily_selection.get("timestamp", "")
    das_articles_count = daily_selection.get("macro_articles_analyzed", 0)

    # Format timestamp (always defined for template)
    if das_timestamp:
        try:
            das_dt = datetime.fromisoformat(das_timestamp.replace("Z", "+00:00"))
            das_ts_str = das_dt.strftime("%Y-%m-%d %H:%M UTC")
            
            # Health check: if last run was within the last 2.5 hours
            hours_since = (datetime.now(timezone.utc) - das_dt).total_seconds() / 3600
            if hours_since <= 2.5:
                das_health_badge = '<span class="px-3 py-1 text-[10px] font-bold bg-emerald-500/10 text-emerald-400 rounded-full border border-emerald-500/20 uppercase flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Healthy (Syncing)</span>'
            else:
                das_health_badge = '<span class="px-3 py-1 text-[10px] font-bold bg-amber-500/10 text-amber-400 rounded-full border border-amber-500/20 uppercase flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> Delayed</span>'
        except Exception:
            das_ts_str = das_timestamp
            das_health_badge = '<span class="px-3 py-1 text-[10px] font-bold bg-slate-500/10 text-slate-400 rounded-full border border-slate-500/20 uppercase">Unknown Status</span>'
    else:
        das_health_badge = '<span class="px-3 py-1 text-[10px] font-bold bg-slate-500/10 text-slate-400 rounded-full border border-slate-500/20 uppercase">Awaiting Run</span>'

    if das_selected_assets:
        for asset in das_selected_assets:
            sym = asset.get("symbol", "?")
            asset_type = asset.get("type", "unknown")
            score = asset.get("sentiment_score", 0.0)
            reason = asset.get("reasoning", "")

            # Type badge
            if asset_type == "crypto":
                type_badge = '<span class="px-2 py-0.5 text-[10px] font-bold bg-violet-500/10 text-violet-400 rounded border border-violet-500/20 uppercase tracking-wider">Crypto</span>'
                icon = "&#8383;"
            else:
                type_badge = '<span class="px-2 py-0.5 text-[10px] font-bold bg-blue-500/10 text-blue-400 rounded border border-blue-500/20 uppercase tracking-wider">Equity</span>'
                icon = "&#x1F4C8;"

            # Sentiment score bar
            score_pct = int(abs(score) * 100)
            score_color = "bg-emerald-500" if score >= 0 else "bg-rose-500"
            score_label_color = "text-emerald-400" if score >= 0 else "text-rose-400"
            bias_text = asset.get("bias", "BULLISH" if score >= 0 else "BEARISH").upper()
            strength_label = f"{bias_text} Strength"

            das_cards_html += f"""
            <div class="relative overflow-hidden rounded-2xl border border-slate-700/60 bg-gradient-to-br from-slate-900/80 to-slate-800/40 p-5 backdrop-blur-md">
                <div class="flex items-start justify-between mb-3">
                    <div class="flex items-center gap-3">
                        <div class="flex-shrink-0 w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center text-2xl">{icon}</div>
                        <div>
                            <div class="text-xl font-bold text-white tracking-tight">{sym}</div>
                            <div class="mt-0.5">{type_badge}</div>
                        </div>
                    </div>
                    <div class="text-right">
                        <div class="text-xl font-bold {score_label_color}">{bias_text}</div>
                        <div class="text-[10px] text-slate-500 uppercase tracking-wider">Live Bias</div>
                    </div>
                </div>
                <div class="mb-3">
                    <div class="flex justify-between text-[10px] text-slate-500 mb-1">
                        <span>{strength_label}</span>
                        <span class="{score_label_color} font-bold">{score_pct}%</span>
                    </div>
                    <div class="w-full bg-slate-800 rounded-full h-1.5">
                        <div class="{score_color} h-1.5 rounded-full transition-all" style="width: {score_pct}%"></div>
                    </div>
                </div>
                <p class="text-xs text-slate-400 leading-relaxed line-clamp-2" title="{reason}">{reason}</p>
            </div>
            """
    else:
        das_cards_html = """
        <div class="col-span-full py-8 text-center text-slate-500">
            <div class="text-3xl mb-2">&#x23F3;</div>
            <div class="text-sm font-medium">Waiting for next cycle — no AI selection available yet.</div>
        </div>
        """

    # Build WebSocket Trigger Rows
    ws_rows = []
    if ws_triggers:
        for trig in reversed(ws_triggers[-15:]):
            timestamp_str = trig.get("timestamp", "")
            try:
                dt_str = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt_str = timestamp_str

            sym = trig.get("symbol", "")
            price = trig.get("price", 0.0)
            dip = trig.get("dip_pct", 0.0)
            bias = trig.get("bias", "NEUTRAL")
            score = trig.get("sentiment_score", 0.0)
            executed = trig.get("executed", False)
            reason = trig.get("reasoning", "")

            # Badge color logic
            if executed:
                status_badge = '<span class="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">⚡ EXECUTED</span>'
            elif trig.get("order_id", "") == "FAILED":
                status_badge = '<span class="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold border bg-rose-500/10 text-rose-400 border-rose-500/20">❌ FAILED</span>'
            elif bias == "COOLDOWN":
                status_badge = '<span class="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold border bg-yellow-500/10 text-yellow-400 border-yellow-500/20">COOLDOWN</span>'
            else:
                status_badge = '<span class="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold border bg-slate-500/10 text-slate-400 border-slate-500/20">IGNORED</span>'

            bias_color = "text-emerald-400" if bias == "BULLISH" else "text-rose-400" if bias == "BEARISH" else "text-slate-400"

            ws_rows.append(f"""
            <tr class="hover:bg-slate-900/20 transition-colors border-b border-slate-800/40 last:border-b-0">
                <td class="py-3 text-slate-400 font-mono text-xs">{dt_str}</td>
                <td class="py-3"><span class="font-bold text-white">{sym}</span></td>
                <td class="py-3 text-right font-mono">${price:,.2f}</td>
                <td class="py-3 text-right font-mono text-rose-400">{dip:+.2f}%</td>
                <td class="py-3 text-center"><span class="{bias_color} font-bold text-xs">{bias} ({score:+.2f})</span></td>
                <td class="py-3 text-center">{status_badge}</td>
                <td class="py-3 pl-4 text-slate-400 max-w-[250px] truncate" title="{reason}">{reason}</td>
            </tr>
            """)
    else:
        ws_rows.append('<tr><td colspan="7" class="py-6 text-center text-slate-500 text-sm">No real-time WebSocket trigger logs recorded yet.</td></tr>')

    # Fetch Alpaca Live Orders
    alpaca_orders_rows = []
    try:
        from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL
        if APCA_API_KEY_ID and APCA_API_SECRET_KEY and "your_api" not in APCA_API_KEY_ID.lower():
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            tc = TradingClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY, paper="paper" in APCA_API_BASE_URL.lower(), url_override=APCA_API_BASE_URL)
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=10)
            orders = tc.get_orders(filter=req)
            for o in orders:
                status_color = "text-emerald-400" if o.status.value == "filled" else "text-yellow-400" if o.status.value == "accepted" else "text-slate-400"
                dt_str = o.created_at.strftime('%Y-%m-%d %H:%M:%S')
                qty = str(o.qty) if o.qty else f"${o.notional}" if o.notional else "-"
                filled_qty = str(o.filled_qty) if o.filled_qty else "0"
                avg_price = f"${float(o.filled_avg_price):,.2f}" if getattr(o, "filled_avg_price", None) else "-"
                
                alpaca_orders_rows.append(f"""
                <tr class="hover:bg-slate-900/20 transition-colors border-b border-slate-800/40 last:border-b-0">
                    <td class="py-3 text-slate-400 font-mono text-xs">{dt_str}</td>
                    <td class="py-3"><span class="font-bold text-white">{o.symbol}</span></td>
                    <td class="py-3"><span class="px-2 py-0.5 rounded-md border border-slate-700 bg-slate-800/50 text-slate-300 uppercase font-mono text-xs">{o.side.value}</span></td>
                    <td class="py-3 text-right font-mono text-slate-300">{qty}</td>
                    <td class="py-3 text-right font-mono text-slate-300">{filled_qty}</td>
                    <td class="py-3 text-right font-mono">{avg_price}</td>
                    <td class="py-3 pl-4 font-semibold {status_color} uppercase tracking-wider text-xs">{o.status.value}</td>
                </tr>
                """)
    except Exception as e:
        alpaca_orders_rows.append(f'<tr><td colspan="7" class="py-6 text-center text-rose-500 text-sm">Failed to load Alpaca orders: {e}</td></tr>')
        
    if not alpaca_orders_rows:
        alpaca_orders_rows.append('<tr><td colspan="7" class="py-6 text-center text-slate-500 text-sm">No recent Alpaca orders found.</td></tr>')

    html_template = f"""<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nano-Trader-AI Dashboard</title>
    <!-- Tailwind CSS via CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        brand: {{
                            50: '#f0f7ff',
                            500: '#3b82f6',
                            600: '#2563eb',
                            900: '#1e3a8a',
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <!-- Chart.js via CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
        body {{
            font-family: 'Outfit', sans-serif;
        }}
    </style>
</head>
<body class="h-full bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-black">
    <div class="min-h-full">
        <!-- Navigation -->
        <nav class="border-b border-slate-800/80 bg-slate-950/60 backdrop-blur-md sticky top-0 z-40">
            <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
                <div class="flex h-16 items-center justify-between">
                    <div class="flex items-center gap-3">
                        <div class="h-9 w-9 rounded-xl bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                            <svg class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                            </svg>
                        </div>
                        <div>
                            <span class="text-lg font-bold bg-gradient-to-r from-blue-400 to-indigo-200 bg-clip-text text-transparent">Nano-Trader-AI</span>
                            <span class="ml-1.5 text-xs font-semibold px-2 py-0.5 bg-blue-500/10 text-blue-400 rounded-full border border-blue-500/20">Control Room</span>
                        </div>
                    </div>
                    <div class="flex items-center gap-4">
                        <!-- Market Clock -->
                        <div class="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 hidden sm:flex" id="marketClockContainer">
                            <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">US Market</span>
                            <span id="marketStatus" class="text-xs font-bold text-slate-500">...</span>
                            <span id="marketTimer" class="text-[11px] font-mono text-slate-400 ml-1"></span>
                        </div>
                        <!-- Environment selector -->
                        <div class="flex items-center gap-2">
                            <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider hidden sm:block">Env:</span>
                            <select id="envSelect" onchange="changeEnvironment()" class="bg-slate-900 border border-slate-800 rounded-lg px-2 py-1 text-xs font-bold text-white focus:outline-none focus:border-blue-500 cursor-pointer">
                                <option value="sandbox">Sandbox</option>
                                <option value="production">Live</option>
                            </select>
                        </div>
                        <!-- Live Auto-Refresh toggle -->
                        <button onclick="toggleAutoRefresh()" id="refreshBtn" class="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs font-bold text-slate-400 hover:text-white transition-colors" title="Toggle 5-second auto refresh">
                            <span class="relative flex h-2 w-2">
                                <span id="refreshPing" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 hidden"></span>
                                <span id="refreshDot" class="relative inline-flex rounded-full h-2 w-2 bg-slate-600"></span>
                            </span>
                            Live Update
                        </button>
                        <!-- Configuration Settings toggle -->
                        <button onclick="toggleSettings()" id="settingsBtn" class="p-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl transition-colors">
                            <svg class="h-4.5 w-4.5 text-slate-400 hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        </nav>

        <!-- Main Content -->
        <main class="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
            <!-- Control Room Settings Panel -->
            <div id="settingsPanel" class="hidden mb-8 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-md">
                <h2 class="text-lg font-bold text-white mb-4">Credentials & Environment Settings Manager</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-5 mb-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Alpaca API Key ID</label>
                        <input type="text" id="alpacaKeyId" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors" placeholder="your_api_key_id_here">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Alpaca Secret Key</label>
                        <input type="password" id="alpacaSecretKey" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors" placeholder="your_api_secret_key_here">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Alpaca Base URL</label>
                        <input type="text" id="alpacaBaseUrl" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors" placeholder="https://paper-api.alpaca.markets">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Gemini API Key</label>
                        <input type="password" id="geminiApiKey" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white font-mono text-sm focus:outline-none focus:border-blue-500 transition-colors" placeholder="your_gemini_api_key_here">
                    </div>
                </div>
                <div class="flex justify-end gap-3">
                    <button onclick="toggleSettings()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-medium transition-colors text-sm">Cancel</button>
                    <button onclick="saveSettings()" id="saveBtn" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-medium transition-colors text-sm">Save Configs</button>
                </div>
            </div>

            <!-- Top Alert / LEDs row -->
            <div class="mb-6 flex flex-wrap items-center justify-between gap-4 bg-slate-900/30 border border-slate-800/40 rounded-2xl px-6 py-4 backdrop-blur-md">
                <div class="flex items-center gap-6">
                    <!-- LED 1: Alpaca -->
                    <div onclick="showConnectionError('alpaca')" class="flex items-center gap-2.5 cursor-pointer hover:opacity-80 transition-opacity" title="Click to view Alpaca connection details">
                        <span class="relative flex h-3 w-3">
                            <span id="alpacaLedPing" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75"></span>
                            <span id="alpacaLedColor" class="relative inline-flex rounded-full h-3 w-3 bg-yellow-500"></span>
                        </span>
                        <span class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Alpaca API Connection</span>
                    </div>

                    <!-- LED 2: Gemini -->
                    <div onclick="showConnectionError('gemini')" class="flex items-center gap-2.5 cursor-pointer hover:opacity-80 transition-opacity" title="Click to view Gemini connection details">
                        <span class="relative flex h-3 w-3">
                            <span id="geminiLedPing" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75"></span>
                            <span id="geminiLedColor" class="relative inline-flex rounded-full h-3 w-3 bg-yellow-500"></span>
                        </span>
                        <span class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Gemini API Connection</span>
                    </div>
                    
                    <!-- LED 3: Engine -->
                    <div class="flex items-center gap-2.5 cursor-help" title="Indicates if the Realtime Engine is actively feeding market data.">
                        <span class="relative flex h-3 w-3">
                            <span id="engineLedPing" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75"></span>
                            <span id="engineLedColor" class="relative inline-flex rounded-full h-3 w-3 bg-yellow-500"></span>
                        </span>
                        <span class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Engine Heartbeat</span>
                    </div>
                </div>
                <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Control Room Telemetry Status
                </div>
            </div>

            <!-- Metrics Cards Grid -->
            <div class="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-5 mb-8">
                <div class="relative overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/40 p-6 backdrop-blur-md">
                    <dt class="text-sm font-semibold text-slate-400">Total Portfolio Value</dt>
                    <dd class="mt-2 text-2xl font-bold tracking-tight text-white">${current_equity:,.2f}</dd>
                    <div class="mt-2 flex items-center text-xs font-medium text-slate-500">
                        Starting Balance: ${starting_equity:,.2f}
                    </div>
                </div>

                <div class="relative overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/40 p-6 backdrop-blur-md">
                    <dt class="text-sm font-semibold text-slate-400">Buying Power</dt>
                    <dd class="mt-2 text-2xl font-bold tracking-tight text-white">${current_buying_power:,.2f}</dd>
                    <div class="mt-2 flex items-center text-xs text-slate-500 font-medium font-mono">
                        Active Cash reserves
                    </div>
                </div>

                <div class="relative overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/40 p-6 backdrop-blur-md">
                    <dt class="text-sm font-semibold text-slate-400">Cumulative PnL</dt>
                    <dd class="mt-2 text-2xl font-bold tracking-tight {'text-emerald-400' if cumulative_pnl >= 0 else 'text-rose-400'}">
                        {'+' if cumulative_pnl >= 0 else ''}${cumulative_pnl:,.2f}
                    </dd>
                    <div class="mt-2 flex items-center text-xs font-semibold {'text-emerald-400/80' if pnl_pct >= 0 else 'text-rose-400/80'}">
                        {'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%
                    </div>
                </div>

                <div class="relative overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/40 p-6 backdrop-blur-md">
                    <dt class="text-sm font-semibold text-slate-400">Open Positions PnL</dt>
                    <dd class="mt-2 text-2xl font-bold tracking-tight {'text-emerald-400' if current_unrealized_pnl >= 0 else 'text-rose-400'}">
                        {'+' if current_unrealized_pnl >= 0 else ''}${current_unrealized_pnl:,.2f}
                    </dd>
                    <div class="mt-2 flex items-center text-xs text-slate-500 font-medium">
                        Unrealized open assets
                    </div>
                </div>

                <div class="relative overflow-hidden rounded-2xl border border-slate-800/60 bg-slate-900/40 p-6 backdrop-blur-md">
                    <dt class="text-sm font-semibold text-slate-400">Total Trades Executed</dt>
                    <dd class="mt-2 text-2xl font-bold tracking-tight text-white">{len(trades)}</dd>
                    <div class="mt-2 flex items-center text-xs text-slate-500 font-medium">
                        AI orders triggered
                    </div>
                </div>
            </div>

            <!-- AI Asset Selection of the Day -->
            <div class="mb-8 rounded-2xl border border-slate-700/60 bg-slate-900/30 p-6 backdrop-blur-md">
                <div class="flex items-center justify-between mb-5">
                    <div>
                        <h2 class="text-lg font-bold text-white">&#127916; AI Asset Selection of the Day</h2>
                        <p class="text-xs text-slate-500 mt-0.5">
                            {f'Last updated: {das_ts_str} &nbsp;&bull;&nbsp; {das_articles_count} macro articles analyzed' if das_ts_str else 'Awaiting first DAS cycle...'}
                        </p>
                    </div>
                    <div class="flex items-center gap-2">
                        {das_health_badge}
                        <span class="px-3 py-1 text-xs font-bold bg-indigo-500/10 text-indigo-400 rounded-full border border-indigo-500/20 uppercase tracking-wider">Live AI Selection</span>
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {das_cards_html}
                </div>
            </div>

            <!-- Market News Feed -->
            <div class="mb-8 rounded-2xl border border-slate-700/60 bg-slate-900/30 p-6 backdrop-blur-md">
                <div class="flex items-center justify-between mb-5">
                    <div>
                        <h2 class="text-lg font-bold text-white">📰 Market News Feed</h2>
                        <p class="text-xs text-slate-500 mt-0.5">
                            Real-time intelligence feed consumed by the AI
                        </p>
                    </div>
                </div>
                <div class="overflow-y-auto pr-2" style="max-height: 400px;">
                    {news_feed_html}
                </div>
            </div>

            <!-- Macro Market Context (TradingView) -->
            <div class="mb-8 rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md">
                <div class="flex items-center justify-between mb-4">
                    <div>
                        <h2 class="text-lg font-bold text-white">📈 Macro Market Context</h2>
                        <p class="text-xs text-slate-500 mt-0.5">Interactive Multi-Timeframe Chart powered by TradingView</p>
                    </div>
                </div>
                <div class="h-[500px] w-full relative rounded-xl overflow-hidden border border-slate-800/50">
                    <!-- TradingView Widget BEGIN -->
                    <div class="tradingview-widget-container" style="height:100%;width:100%">
                      <div id="tradingview_chart" style="height:calc(100% - 32px);width:100%"></div>
                      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                      <script type="text/javascript">
                      new TradingView.widget(
                      {{
                      "autosize": true,
                      "symbol": "CRYPTO:BTCUSD",
                      "interval": "D",
                      "timezone": "Etc/UTC",
                      "theme": "dark",
                      "style": "1",
                      "locale": "en",
                      "enable_publishing": false,
                      "backgroundColor": "rgba(15, 23, 42, 0.4)",
                      "gridColor": "rgba(30, 41, 59, 0.5)",
                      "hide_top_toolbar": false,
                      "hide_legend": false,
                      "save_image": false,
                      "container_id": "tradingview_chart"
                    }}
                      );
                      </script>
                    </div>
                    <!-- TradingView Widget END -->
                </div>
            </div>

            <!-- Real-Time WebSocket Activity (Live Price Chart + Trigger Logs) -->
            <div class="grid grid-cols-1 gap-6 lg:grid-cols-3 mb-8">
                <!-- Live Price Chart -->
                <div class="lg:col-span-2 rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md">
                    <div class="flex items-center justify-between mb-4">
                        <div>
                            <h2 class="text-lg font-bold text-white">📊 WebSocket Live Price & AI Trigger Points</h2>
                            <p class="text-xs text-slate-500 mt-0.5">Real-time micro price tracking with AI execution points overlay</p>
                        </div>
                        <!-- Tabs / Symbol Selectors -->
                        <div class="flex gap-2 bg-slate-950 p-1 rounded-xl border border-slate-800/60">
                            <button id="wsTabBTC" onclick="switchWSSymbol('BTCUSD')" class="px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-600 text-white transition-all">BTCUSD</button>
                            <button id="wsTabETH" onclick="switchWSSymbol('ETHUSD')" class="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-white transition-all">ETHUSD</button>
                        </div>
                    </div>
                    <div class="h-80 w-full">
                        <canvas id="wsRealtimeChart"></canvas>
                    </div>
                </div>

                <!-- Trigger Logs -->
                <div class="rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md overflow-hidden flex flex-col">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-bold text-white">⚡ WS Trigger Logs</h2>
                        <span class="relative flex h-2 w-2">
                            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                        </span>
                    </div>
                    <div class="flex-grow overflow-x-auto overflow-y-auto max-h-[320px]">
                        <table class="min-w-full divide-y divide-slate-800/50">
                            <thead>
                                <tr class="text-[10px] font-semibold text-slate-400 text-left uppercase tracking-wider">
                                    <th class="pb-2">Time</th>
                                    <th class="pb-2">Asset</th>
                                    <th class="pb-2 text-right">Price</th>
                                    <th class="pb-2 text-right">Dip%</th>
                                    <th class="pb-2 text-center">Bias</th>
                                    <th class="pb-2 text-center">Status</th>
                                    <th class="pb-2 pl-4">Reasoning</th>
                                </tr>
                            </thead>
                            <tbody id="wsTableBody" class="divide-y divide-slate-800/40 text-xs font-medium text-slate-300">
                                {"".join(ws_rows)}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Charts Section -->
            <div class="grid grid-cols-1 gap-6 lg:grid-cols-3 mb-8">
                <div class="lg:col-span-2 rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md">
                    <h2 class="text-lg font-bold text-white mb-4">Correlation: Portfolio PnL vs. AI Sentiment Score</h2>
                    <div class="h-72 w-full">
                        <canvas id="correlationChart"></canvas>
                    </div>
                </div>

                <div class="rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md overflow-hidden">
                    <h2 class="text-lg font-bold text-white mb-4">Trades Distribution by Symbol</h2>
                    <div class="h-72 w-full">
                        <canvas id="distributionChart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Alpaca Live Orders Table -->
            <div id="alpacaOrdersSection" class="rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md overflow-hidden mb-8">
                <h2 class="text-lg font-bold text-white mb-4"><span class="text-yellow-400">🦙</span> Alpaca Broker Orders (Live API)</h2>
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-slate-800/50">
                        <thead>
                            <tr class="text-xs font-semibold text-slate-400 text-left uppercase tracking-wider">
                                <th class="pb-3 pt-2">Created At</th>
                                <th class="pb-3 pt-2">Asset</th>
                                <th class="pb-3 pt-2">Side</th>
                                <th class="pb-3 pt-2 text-right">Qty/Notional</th>
                                <th class="pb-3 pt-2 text-right">Filled Qty</th>
                                <th class="pb-3 pt-2 text-right">Avg Price</th>
                                <th class="pb-3 pt-2 pl-4">Status</th>
                            </tr>
                        </thead>
                        <tbody id="alpacaOrdersBody" class="divide-y divide-slate-800/40 text-sm font-medium text-slate-300">
                            {"".join(alpaca_orders_rows)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Trade History Table -->
            <div class="rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md overflow-hidden mb-8">
                <h2 class="text-lg font-bold text-white mb-4">Trades Execution logs</h2>
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-slate-800/50">
                        <thead>
                            <tr class="text-xs font-semibold text-slate-400 text-left uppercase tracking-wider">
                                <th class="pb-3 pt-2">Timestamp</th>
                                <th class="pb-3 pt-2">Symbol</th>
                                <th class="pb-3 pt-2">Type</th>
                                <th class="pb-3 pt-2 text-right">Quantity</th>
                                <th class="pb-3 pt-2 text-right">Price</th>
                                <th class="pb-3 pt-2 text-right">Notional</th>
                                <th class="pb-3 pt-2 text-center">Sentiment</th>
                                <th class="pb-3 pt-2 text-center">Feedback PnL</th>
                                <th class="pb-3 pt-2 pl-4">AI Reasoning</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800/40 text-sm font-medium text-slate-300">
                            {"".join(trades_rows)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- AI Telemetry logs Table -->
            <div class="rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md overflow-hidden">
                <h2 class="text-lg font-bold text-white mb-4">AI Decision & Telemetry Logs</h2>
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-slate-800/50">
                        <thead>
                            <tr class="text-xs font-semibold text-slate-400 text-left uppercase tracking-wider">
                                <th class="pb-3 pt-2">Timestamp</th>
                                <th class="pb-3 pt-2">Asset</th>
                                <th class="pb-3 pt-2 text-right">Execution Price</th>
                                <th class="pb-3 pt-2 text-center">Decision</th>
                                <th class="pb-3 pt-2 text-center">Confidence</th>
                                <th class="pb-3 pt-2 text-center">Feedback PnL</th>
                                <th class="pb-3 pt-2 pl-4">Raw News Titles Analyzed</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800/40 text-sm font-medium text-slate-300">
                            {"".join(ai_rows)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Human Logbook Panel -->
            <div class="mb-8 rounded-2xl border border-slate-800/60 bg-slate-900/30 p-6 backdrop-blur-md overflow-hidden">
                <h2 class="text-lg font-bold text-white mb-4">Human Logbook & Warning Diagnostics</h2>
                <div id="logbookContainer" class="max-h-[300px] overflow-y-auto">
                    {"".join(logbook_rows)}
                </div>
            </div>
        </main>
        <!-- Toast Notification Container -->
        <div id="toastContainer" class="fixed bottom-5 right-5 z-50 flex flex-col gap-3"></div>
    </div>

    <!-- Data Injection & Chart Script -->
    <script id="appData" type="application/json">
    {{
        "portfolioData": {json.dumps(history)},
        "tradesData": {json.dumps(trades)},
        "priceHistoryData": {json.dumps(price_history)},
        "wsTriggersData": {json.dumps(ws_triggers)}
    }}
    </script>
    <script>
        const appDataEl = document.getElementById("appData");
        const appData = JSON.parse(appDataEl.textContent);
        
        let portfolioData = appData.portfolioData;
        let tradesData = appData.tradesData;
        let priceHistoryData = appData.priceHistoryData;
        let wsTriggersData = appData.wsTriggersData;

        let wsChartInstance = null;
        let activeWSSymbol = 'BTCUSD';

        function renderWSRealtimeChart(symbol, isSilentUpdate = false) {{
            const ctx = document.getElementById('wsRealtimeChart').getContext('2d');
            if (!ctx) return;
            
            const history = priceHistoryData[symbol] || [];
            const labels = history.map(h => {{
                const date = new Date(h.timestamp);
                return date.toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}});
            }});
            const prices = history.map(h => h.price);

            const symbolTriggers = wsTriggersData.filter(t => t.symbol === symbol && t.executed);
            
            const triggerPoints = [];
            symbolTriggers.forEach(trig => {{
                const trigTime = new Date(trig.timestamp).getTime();
                let closestIndex = -1;
                let minDiff = Infinity;
                history.forEach((h, idx) => {{
                    const diff = Math.abs(new Date(h.timestamp).getTime() - trigTime);
                    if (diff < minDiff && diff < 120000) {{ // within 2 mins
                        minDiff = diff;
                        closestIndex = idx;
                    }}
                }});

                if (closestIndex !== -1) {{
                    triggerPoints.push({{
                        x: labels[closestIndex],
                        y: prices[closestIndex],
                        reason: trig.reasoning,
                        dip: trig.dip_pct
                    }});
                }}
            }});

            if (wsChartInstance) {{
                if (isSilentUpdate) {{
                    wsChartInstance.data.labels = labels.length > 0 ? labels : ['No Data'];
                    wsChartInstance.data.datasets[0].label = `${{symbol}} Price ($)`;
                    wsChartInstance.data.datasets[0].data = prices.length > 0 ? prices : [0.0];
                    wsChartInstance.data.datasets[1].data = triggerPoints;
                    wsChartInstance.update('none');
                    return;
                }} else {{
                    wsChartInstance.destroy();
                }}
            }}

            wsChartInstance = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels.length > 0 ? labels : ['No Data'],
                    datasets: [
                        {{
                            label: `${{symbol}} Price ($)`,
                            data: prices.length > 0 ? prices : [0.0],
                            borderColor: '#818cf8',
                            borderWidth: 2,
                            pointRadius: 0,
                            tension: 0.15,
                            fill: false
                        }},
                        {{
                            label: '⚡ AI Buy Trigger',
                            data: triggerPoints,
                            type: 'scatter',
                            backgroundColor: '#10b981',
                            borderColor: '#34d399',
                            borderWidth: 2,
                            pointRadius: 8,
                            pointStyle: 'triangle',
                            showLine: false
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        x: {{
                            grid: {{ display: false }},
                            ticks: {{ color: '#64748b', font: {{ family: 'Outfit' }} }}
                        }},
                        y: {{
                            grid: {{ color: '#1e293b' }},
                            ticks: {{ color: '#64748b', font: {{ family: 'Outfit' }} }}
                        }}
                    }},
                    plugins: {{
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    if (context.datasetIndex === 1) {{
                                        const pt = triggerPoints[context.dataIndex];
                                        return `⚡ BUY TRIGGER: $${{pt.y.toFixed(2)}} (DIP: ${{pt.dip.toFixed(2)}}%)`;
                                    }}
                                    return `Price: $${{context.raw.toFixed(2)}}`;
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        }}

        function switchWSSymbol(symbol) {{
            activeWSSymbol = symbol;
            
            const btcBtn = document.getElementById('wsTabBTC');
            const ethBtn = document.getElementById('wsTabETH');
            
            if (symbol === 'BTCUSD') {{
                btcBtn.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-600 text-white transition-all";
                ethBtn.className = "px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-white transition-all";
            }} else {{
                ethBtn.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-600 text-white transition-all";
                btcBtn.className = "px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-white transition-all";
            }}
            
            renderWSRealtimeChart(symbol);
        }}

        // Initialize WS chart
        window.addEventListener("DOMContentLoaded", () => {{
            renderWSRealtimeChart(activeWSSymbol);
        }});

        // Render Correlation Chart
        const correlationCtx = document.getElementById('correlationChart').getContext('2d');
        const labels = portfolioData.map(snap => {{
            const date = new Date(snap.timestamp);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}});
        }});
        const startingEquity = portfolioData.length > 0 ? portfolioData[0].equity : 100000.00;
        const pnlValues = portfolioData.map(snap => snap.equity - startingEquity);
        const sentimentValues = portfolioData.map(snap => snap.average_sentiment !== undefined ? snap.average_sentiment : 0.0);

        new Chart(correlationCtx, {{
            type: 'line',
            data: {{
                labels: labels.length > 0 ? labels : ['No Data'],
                datasets: [
                    {{
                        label: 'Cumulative PnL ($)',
                        data: pnlValues.length > 0 ? pnlValues : [0.0],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.05)',
                        borderWidth: 3,
                        yAxisID: 'yPnL',
                        tension: 0.25,
                        fill: true
                    }},
                    {{
                        label: 'AI Sentiment Score',
                        data: sentimentValues.length > 0 ? sentimentValues : [0.0],
                        borderColor: '#3b82f6',
                        borderWidth: 2.5,
                        borderDash: [5, 5],
                        yAxisID: 'ySentiment',
                        tension: 0.25,
                        fill: false
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    yPnL: {{
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {{
                            display: true,
                            text: 'PnL ($)',
                            color: '#94a3b8',
                            font: {{ family: 'Outfit', weight: 'bold' }}
                        }},
                        grid: {{ color: '#1e293b' }},
                        ticks: {{ color: '#64748b', font: {{ family: 'Outfit' }} }}
                    }},
                    ySentiment: {{
                        type: 'linear',
                        display: true,
                        position: 'right',
                        min: -1.0,
                        max: 1.0,
                        title: {{
                            display: true,
                            text: 'AI Sentiment Score',
                            color: '#94a3b8',
                            font: {{ family: 'Outfit', weight: 'bold' }}
                        }},
                        grid: {{ drawOnChartArea: false }},
                        ticks: {{ color: '#64748b', font: {{ family: 'Outfit' }} }}
                    }},
                    x: {{
                        grid: {{ display: false }},
                        ticks: {{ color: '#64748b', font: {{ family: 'Outfit' }} }}
                    }}
                }}
            }}
        }});

        // Render Distribution Chart
        const distCtx = document.getElementById('distributionChart').getContext('2d');
        const tradeCounts = {{}};
        tradesData.forEach(t => {{
            tradeCounts[t.symbol] = (tradeCounts[t.symbol] || 0) + 1;
        }});
        const distLabels = Object.keys(tradeCounts);
        const distValues = Object.values(tradeCounts);

        new Chart(distCtx, {{
            type: 'bar',
            data: {{
                labels: distLabels.length > 0 ? distLabels : ['No Trades'],
                datasets: [{{
                    label: 'Trades Count',
                    data: distValues.length > 0 ? distValues : [0],
                    backgroundColor: 'rgba(99, 102, 241, 0.75)',
                    borderColor: '#6366f1',
                    borderWidth: 1.5,
                    borderRadius: 8
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{
                        grid: {{ display: false }},
                        ticks: {{ color: '#64748b', font: {{ family: 'Outfit' }} }}
                    }},
                    y: {{
                        grid: {{ color: '#1e293b' }},
                        ticks: {{ color: '#64748b', precision: 0, font: {{ family: 'Outfit' }} }}
                    }}
                }}
            }}
        }});

        // Credentials and LED Manager Logic
        function loadSavedCredentials() {{
            const env = localStorage.getItem("trading_env") || "sandbox";
            document.getElementById("envSelect").value = env;
            
            document.getElementById("alpacaKeyId").value = localStorage.getItem("alpaca_key_id") || "";
            document.getElementById("alpacaSecretKey").value = localStorage.getItem("alpaca_secret_key") || "";
            document.getElementById("alpacaBaseUrl").value = localStorage.getItem("alpaca_base_url") || (env === "production" ? "https://api.alpaca.markets" : "https://paper-api.alpaca.markets");
            document.getElementById("geminiApiKey").value = localStorage.getItem("gemini_key") || "";
            
            triggerConnectionCheck();
        }}

        function toggleSettings() {{
            const panel = document.getElementById("settingsPanel");
            panel.classList.toggle("hidden");
        }}

        function changeEnvironment() {{
            const env = document.getElementById("envSelect").value;
            localStorage.setItem("trading_env", env);
            
            const baseUrlField = document.getElementById("alpacaBaseUrl");
            if (env === "production") {{
                baseUrlField.value = "https://api.alpaca.markets";
            }} else {{
                baseUrlField.value = "https://paper-api.alpaca.markets";
            }}
            saveSettings(false);
        }}

        function showNotification(message, type = "info") {{
            const container = document.getElementById("toastContainer");
            const toast = document.createElement("div");
            
            const bgClass = type === "error" ? "bg-rose-500/90 text-white border border-rose-500/20" : "bg-slate-900/95 text-white border border-blue-500/20";
            
            toast.className = `${{bgClass}} backdrop-blur-md px-4 py-3 rounded-xl shadow-xl flex items-center gap-2.5 transition-all duration-300 transform translate-y-5 opacity-0 text-sm font-semibold`;
            toast.innerHTML = `
                <span class="h-2 w-2 rounded-full ${{type === 'error' ? 'bg-rose-400' : 'bg-blue-400'}}"></span>
                <span>${{message}}</span>
            `;
            
            container.appendChild(toast);
            
            setTimeout(() => {{
                toast.classList.remove("translate-y-5", "opacity-0");
            }}, 10);
            
            setTimeout(() => {{
                toast.classList.add("translate-y-5", "opacity-0");
                setTimeout(() => {{
                    toast.remove();
                }}, 300);
            }}, 3000);
        }}

        function saveSettings(showAlert = true) {{
            const keyId = document.getElementById("alpacaKeyId").value.trim();
            const secretKey = document.getElementById("alpacaSecretKey").value.trim();
            const baseUrl = document.getElementById("alpacaBaseUrl").value.trim();
            const geminiKey = document.getElementById("geminiApiKey").value.trim();
            const env = document.getElementById("envSelect").value;

            // Set LEDs to checking immediately
            setLedState("alpaca", "checking");
            setLedState("gemini", "checking");

            localStorage.setItem("alpaca_key_id", keyId);
            localStorage.setItem("alpaca_secret_key", secretKey);
            localStorage.setItem("alpaca_base_url", baseUrl);
            localStorage.setItem("gemini_key", geminiKey);
            localStorage.setItem("trading_env", env);

            fetch("/api/config", {{
                method: "POST",
                headers: {{
                    "Content-Type": "application/json"
                }},
                body: JSON.stringify({{
                    api_key: keyId,
                    secret_key: secretKey,
                    base_url: baseUrl,
                    gemini_key: geminiKey,
                    env: env
                }})
            }})
            .then(res => res.json())
            .then(data => {{
                // Instantly trigger connection verification check
                triggerConnectionCheck();
                
                if (showAlert) {{
                    showNotification("Configurations synced successfully! Running verification...", "info");
                    setTimeout(() => {{
                        const panel = document.getElementById("settingsPanel");
                        if (!panel.classList.contains("hidden")) {{
                            toggleSettings();
                        }}
                    }}, 1500);
                }}
            }})
            .catch(err => {{
                console.error("Failed to sync config to python server backend:", err);
                // Still trigger validation for local browser storage
                triggerConnectionCheck();
                if (showAlert) {{
                    showNotification("Saved in browser storage, but sync failed.", "error");
                }}
            }});
        }}

        function triggerConnectionCheck() {{
            setLedState("alpaca", "checking");
            setLedState("gemini", "checking");

            const keyId = localStorage.getItem("alpaca_key_id") || "";
            const secretKey = localStorage.getItem("alpaca_secret_key") || "";
            const baseUrl = localStorage.getItem("alpaca_base_url") || "https://paper-api.alpaca.markets";
            const geminiKey = localStorage.getItem("gemini_key") || "";

            const queryParams = new URLSearchParams({{
                api_key: keyId,
                secret_key: secretKey,
                base_url: baseUrl,
                gemini_key: geminiKey
            }});

            fetch(`/api/status?${{queryParams.toString()}}`)
                .then(res => res.json())
                .then(data => {{
                    window.alpacaError = data.alpaca_error || "";
                    window.geminiError = data.gemini_error || "";
                    
                    setLedState("alpaca", data.alpaca === "connected" ? "connected" : "failed");
                    setLedState("gemini", data.gemini === "connected" ? "connected" : "failed");
                    
                    // Automatically display a detailed popup alert dialog detailing the exact error message
                    if (data.alpaca === "failed" || data.gemini === "failed") {{
                        let errMsg = "Connection Verification Failure Details:\\n\\n";
                        if (data.alpaca === "failed") {{
                            errMsg += `[Alpaca API] Check Failed:\\n${{data.alpaca_error || "Unknown error"}}\\n\\n`;
                        }}
                        if (data.gemini === "failed") {{
                            errMsg += `[Gemini API] Check Failed:\\n${{data.gemini_error || "Unknown error"}}\\n\\n`;
                        }}
                        errMsg += "Please review your settings in the Configurations panel and try again.";
                        alert(errMsg);
                    }} else {{
                        showNotification("API Connection Verification Successful!", "info");
                    }}
                }})
                .catch(err => {{
                    console.error("Error pinging local status API:", err);
                    window.alpacaError = "Local Python server is not listening or returned a network error.";
                    window.geminiError = "Local Python server is not listening or returned a network error.";
                    setLedState("alpaca", "failed");
                    setLedState("gemini", "failed");
                    
                    alert("Connection Verification Failure:\\n\\nCould not establish connection to the local Python server.\\n\\nPlease ensure that the bot server is currently running on your system.");
                }});
        }}

        function setLedState(service, state) {{
            const colorElem = document.getElementById(`${{service}}LedColor`);
            const pingElem = document.getElementById(`${{service}}LedPing`);

            if (state === "connected") {{
                colorElem.className = "relative inline-flex rounded-full h-3 w-3 bg-emerald-500 shadow-md shadow-emerald-500/50";
                pingElem.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75";
            }} else if (state === "failed") {{
                colorElem.className = "relative inline-flex rounded-full h-3 w-3 bg-rose-500 shadow-md shadow-rose-500/50";
                pingElem.className = "absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-0";
            }} else {{
                colorElem.className = "relative inline-flex rounded-full h-3 w-3 bg-yellow-500 shadow-md shadow-yellow-500/50";
                pingElem.className = "animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75";
            }}
        }}
        function showConnectionError(service) {{
            if (service === 'engine') return;
            const error = service === 'alpaca' ? window.alpacaError : window.geminiError;
            if (error && error.trim() !== "") {{
                alert(`${{service.toUpperCase()}} Connection Failure Details:\\n\\n${{error}}`);
            }} else if (error === "") {{
                alert(`${{service.toUpperCase()}} Connection Status:\\n\\nVerification check completed successfully! API keys are active and functional.`);
            }} else {{
                alert(`${{service.toUpperCase()}} Status:\\n\\nVerification check pending... Please save configurations first.`);
            }}
        }}

        function checkEngineHeartbeat() {{
            let isAlive = false;
            try {{
                if (priceHistoryData && priceHistoryData[activeWSSymbol]) {{
                    const history = priceHistoryData[activeWSSymbol];
                    if (history.length > 0) {{
                        const lastTickStr = history[history.length - 1].timestamp;
                        // For Z timestamps, this parses correctly as UTC
                        const lastTick = new Date(lastTickStr).getTime();
                        const now = new Date().getTime();
                        // 3 minutes threshold for stale data (bars are 1 minute)
                        if (now - lastTick < 180000) {{
                            isAlive = true;
                        }}
                    }}
                }}
            }} catch(e) {{}}
            setLedState("engine", isAlive ? "connected" : "failed");
        }}
        setInterval(checkEngineHeartbeat, 5000);
        setTimeout(checkEngineHeartbeat, 1000);

        let refreshInterval = null;
        function toggleAutoRefresh() {{
            const btn = document.getElementById("refreshBtn");
            const ping = document.getElementById("refreshPing");
            const dot = document.getElementById("refreshDot");
            
            if (refreshInterval) {{
                clearInterval(refreshInterval);
                refreshInterval = null;
                ping.classList.add("hidden");
                dot.className = "relative inline-flex rounded-full h-2 w-2 bg-slate-600";
                btn.classList.remove("border-emerald-500/50", "text-emerald-400");
                btn.classList.add("border-slate-800", "text-slate-400");
                localStorage.setItem("auto_refresh", "false");
                showNotification("Live Auto-Refresh Disabled", "info");
            }} else {{
                refreshInterval = setInterval(() => {{
                    fetch(window.location.href)
                        .then(res => res.text())
                        .then(html => {{
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(html, "text/html");
                            
                            // 1. Update WS Triggers table body
                            const currentWsTbody = document.getElementById("wsTableBody");
                            const newWsTbody = doc.getElementById("wsTableBody");
                            if (currentWsTbody && newWsTbody) currentWsTbody.innerHTML = newWsTbody.innerHTML;
                            
                            // 1b. Update Alpaca Orders table body
                            const currentAlpacaBody = document.getElementById("alpacaOrdersBody");
                            const newAlpacaBody = doc.getElementById("alpacaOrdersBody");
                            if (currentAlpacaBody && newAlpacaBody) currentAlpacaBody.innerHTML = newAlpacaBody.innerHTML;
                            
                            // 2. Update Human Logbook
                            const currentLogbook = document.getElementById("logbookContainer");
                            const newLogbook = doc.getElementById("logbookContainer");
                            if (currentLogbook && newLogbook) currentLogbook.innerHTML = newLogbook.innerHTML;
                            
                            // 3. Extract JSON data from script and update chart
                            const newAppDataEl = doc.getElementById("appData");
                            if (newAppDataEl) {{
                                const newAppData = JSON.parse(newAppDataEl.textContent);
                                priceHistoryData = newAppData.priceHistoryData;
                                wsTriggersData = newAppData.wsTriggersData;
                                if (typeof renderWSRealtimeChart === 'function') {{
                                    renderWSRealtimeChart(activeWSSymbol, true);
                                }}
                            }}
                        }})
                        .catch(err => console.error("Auto-refresh fetch failed", err));
                }}, 5000);
                ping.classList.remove("hidden");
                dot.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
                btn.classList.remove("border-slate-800", "text-slate-400");
                btn.classList.add("border-emerald-500/50", "text-emerald-400");
                localStorage.setItem("auto_refresh", "true");
                showNotification("Live Auto-Refresh Enabled (5s)", "info");
            }}
        }}

        window.addEventListener("DOMContentLoaded", () => {{
            loadSavedCredentials();
            if (localStorage.getItem("auto_refresh") !== "false") {{
                // Instantly start interval and update visuals without showing the toggle notification again
                const btn = document.getElementById("refreshBtn");
                const ping = document.getElementById("refreshPing");
                const dot = document.getElementById("refreshDot");
                refreshInterval = setInterval(() => {{
                    fetch(window.location.href)
                        .then(res => res.text())
                        .then(html => {{
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(html, "text/html");
                            const currentWsTbody = document.getElementById("wsTableBody");
                            const newWsTbody = doc.getElementById("wsTableBody");
                            if (currentWsTbody && newWsTbody) currentWsTbody.innerHTML = newWsTbody.innerHTML;
                            const currentLogbook = document.getElementById("logbookContainer");
                            const newLogbook = doc.getElementById("logbookContainer");
                            if (currentLogbook && newLogbook) currentLogbook.innerHTML = newLogbook.innerHTML;
                            const newAppDataEl = doc.getElementById("appData");
                            if (newAppDataEl) {{
                                const newAppData = JSON.parse(newAppDataEl.textContent);
                                priceHistoryData = newAppData.priceHistoryData;
                                wsTriggersData = newAppData.wsTriggersData;
                                if (typeof renderWSRealtimeChart === 'function') renderWSRealtimeChart(activeWSSymbol, true);
                            }}
                        }})
                        .catch(err => console.error("Auto-refresh fetch failed", err));
                }}, 5000);
                ping.classList.remove("hidden");
                dot.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
                btn.classList.remove("border-slate-800", "text-slate-400");
                btn.classList.add("border-emerald-500/50", "text-emerald-400");
            }}
        }});

        // Market Clock Logic
        function updateMarketClock() {{
            const now = new Date();
            const nyTimeString = now.toLocaleString("en-US", {{timeZone: "America/New_York"}});
            const nyTime = new Date(nyTimeString);
            
            const day = nyTime.getDay();
            const h = nyTime.getHours();
            const m = nyTime.getMinutes();
            const s = nyTime.getSeconds();

            const isWeekend = day === 0 || day === 6;
            const currentTimeStr = h * 3600 + m * 60 + s;
            const marketOpen = 9 * 3600 + 30 * 60; // 9:30 AM
            const marketClose = 16 * 3600; // 4:00 PM

            let status = "CLOSED";
            let color = "text-rose-400";
            let timeDiff = 0;

            if (!isWeekend && currentTimeStr >= marketOpen && currentTimeStr < marketClose) {{
                status = "OPEN";
                color = "text-emerald-400";
                timeDiff = marketClose - currentTimeStr;
            }} else {{
                status = "CLOSED";
                color = "text-rose-400";
                if (isWeekend) {{
                    let daysToAdd = day === 6 ? 2 : 1;
                    timeDiff = (24 * 3600 - currentTimeStr) + marketOpen + ((daysToAdd - 1) * 24 * 3600);
                }} else {{
                    if (currentTimeStr < marketOpen) {{
                        timeDiff = marketOpen - currentTimeStr;
                    }} else {{
                        let daysToAdd = day === 5 ? 3 : 1;
                        timeDiff = (24 * 3600 - currentTimeStr) + marketOpen + ((daysToAdd - 1) * 24 * 3600);
                    }}
                }}
            }}

            const hLeft = Math.floor(timeDiff / 3600);
            const mLeft = Math.floor((timeDiff % 3600) / 60);
            const sLeft = timeDiff % 60;
            const timerStr = (status === "OPEN" ? "Closes in " : "Opens in ") + 
                             (hLeft > 24 ? Math.floor(hLeft/24) + "d " + (hLeft%24) + "h " : (hLeft > 0 ? hLeft + "h " : "")) + 
                             mLeft + "m " + sLeft + "s";

            const statusEl = document.getElementById("marketStatus");
            const timerEl = document.getElementById("marketTimer");
            if (statusEl && timerEl) {{
                statusEl.textContent = status;
                statusEl.className = "text-xs font-bold " + color;
                timerEl.textContent = timerStr;
            }}
        }}
        setInterval(updateMarketClock, 1000);
        updateMarketClock();
    </script>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Interactive Control Room successfully generated at {html_path}")

if __name__ == "__main__":
    generate_dashboard()

