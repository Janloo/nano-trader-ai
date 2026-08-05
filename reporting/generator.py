import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_dashboard_data():
    """Returns a dictionary of all dynamic data fragments for the AJAX dashboard."""
    html_path = "dashboard.html"

    from data.db import get_trades, get_portfolio_history, get_ai_analytics
    
    history = get_portfolio_history(limit=500)
    trades = get_trades(limit=100)
    ai_logs = get_ai_analytics(limit=100)

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
        for t in trades:
            # Match feedback loop metrics for display
            feedback_str = "<span class='text-slate-500 font-semibold'>No Trade</span>"
            for log in ai_logs:
                log_time = log.get("timestamp", "")
                trade_time = t.get("timestamp", "")
                if log.get("asset") == t["symbol"] and log_time and trade_time:
                    try:
                        t_diff = abs((datetime.fromisoformat(log_time.replace("Z", "+00:00")) - datetime.fromisoformat(trade_time.replace("Z", "+00:00"))).total_seconds())
                        if t_diff < 120:  # matches within 2 minutes
                            ret_1h = log.get("return_1h")
                            ret_4h = log.get("return_4h")
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
        for log in ai_logs:
            action = log.get("action", "HOLD").upper()
            confidence = log.get("confidence", 0)
            score = log.get("sentiment_score", 0.0)
            
            ret_1h = log.get("return_1h")
            ret_4h = log.get("return_4h")
            parts = []
            if ret_1h is not None:
                parts.append(f"+1h: <span class='{'text-emerald-400' if ret_1h >= 0 else 'text-rose-400'} font-bold'>{ret_1h:+.2f}%</span>")
            if ret_4h is not None:
                parts.append(f"+4h: <span class='{'text-emerald-400' if ret_4h >= 0 else 'text-rose-400'} font-bold'>{ret_4h:+.2f}%</span>")
            feedback_loop_str = " / ".join(parts) if parts else "Awaiting (+1h)"
            
            # Use reasoning as title
            titles_str = log.get("reasoning", "N/A")
            
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
            
            # Show latest 50 logs first
            for log in reversed(logbook_entries[-50:]):
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
                
                import html as _html
                safe_log = _html.escape(log)
                logbook_rows.append(f"""
                <div class="py-3 flex items-start gap-3 border-b border-slate-800/40 last:border-b-0">
                    <div class="flex-shrink-0 mt-0.5">{badge}</div>
                    <div class="{text_class} text-sm font-medium">{safe_log}</div>
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


    # Fetch Alpaca Open Positions
    open_positions_rows = []
    total_invested = 0.0
    try:
        from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL
        if APCA_API_KEY_ID and APCA_API_SECRET_KEY and "your_api" not in APCA_API_KEY_ID.lower():
            from alpaca.trading.client import TradingClient
            tc = TradingClient(APCA_API_KEY_ID, APCA_API_SECRET_KEY, paper="paper" in APCA_API_BASE_URL.lower(), url_override=APCA_API_BASE_URL)
            positions = tc.get_all_positions()
            for p in positions:
                notional = float(p.market_value)
                total_invested += notional
                pnl_color = "text-emerald-400" if float(p.unrealized_pl) >= 0 else "text-rose-400"
                open_positions_rows.append(f'''
                <tr class="hover:bg-slate-900/20 transition-colors border-b border-slate-800/40 last:border-b-0">
                    <td class="py-3"><span class="font-bold text-white">{p.symbol}</span></td>
                    <td class="py-3 text-right font-mono text-slate-300">{p.qty}</td>
                    <td class="py-3 text-right font-mono text-slate-300">${float(p.avg_entry_price):,.2f}</td>
                    <td class="py-3 text-right font-mono text-slate-300">${float(p.current_price):,.2f}</td>
                    <td class="py-3 text-right font-mono text-indigo-300 font-bold">${notional:,.2f}</td>
                    <td class="py-3 text-right font-mono {pnl_color}">${float(p.unrealized_pl):,.2f}</td>
                    <td class="py-3 text-right pl-4">
                        <button onclick="closePosition('{p.symbol}')" class="px-3 py-1 bg-rose-600/80 hover:bg-rose-500 text-white rounded text-xs font-bold transition">Close</button>
                    </td>
                </tr>
                ''')
    except Exception as e:
        open_positions_rows.append(f'<tr><td colspan="7" class="py-6 text-center text-rose-500 text-sm">Failed to load open positions: {e}</td></tr>')
        
    if not open_positions_rows:
        open_positions_rows.append('<tr><td colspan="7" class="py-6 text-center text-slate-500 text-sm">No open positions found.</td></tr>')

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

    return {
        'current_equity': current_equity,
        'current_buying_power': current_buying_power,
        'cumulative_pnl': cumulative_pnl,
        'pnl_pct': pnl_pct,
        'current_unrealized_pnl': current_unrealized_pnl,
        'total_trades': len(trades),
        'trades_rows': ''.join(trades_rows),
        'ai_rows': ''.join(ai_rows),
        'logbook_rows': ''.join(logbook_rows),
        'das_cards_html': das_cards_html,
        'news_feed_html': news_feed_html,
        'das_ts_str': das_ts_str,
        'das_articles_count': das_articles_count,
        'das_health_badge': das_health_badge,
        'ws_rows': ''.join(ws_rows),
        'open_positions_rows': ''.join(open_positions_rows),
        'total_invested': total_invested,
        'alpaca_orders_rows': ''.join(alpaca_orders_rows),
        'starting_equity': starting_equity,
        'history_raw': history,
        'trades_raw': trades,
        'price_history_raw': price_history,
        'ws_triggers_raw': ws_triggers
    }


def get_trades_rows_html(offset=0, limit=20):
    from data.db import get_db, get_ai_analytics
    from datetime import datetime
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset))
        trades = [dict(row) for row in cursor.fetchall()]
        
    ai_logs = get_ai_analytics(limit=100) # Fetch recent for feedback mapping
    
    trades_rows = []
    for t in trades:
        feedback_str = "<span style='color: var(--text-muted); font-weight: 600;'>No Trade</span>"
        for log in ai_logs:
            log_time = log.get("timestamp", "")
            trade_time = t.get("timestamp", "")
            if log.get("asset") == t["symbol"] and log_time and trade_time:
                try:
                    t_diff = abs((datetime.fromisoformat(log_time.replace("Z", "+00:00")) - datetime.fromisoformat(trade_time.replace("Z", "+00:00"))).total_seconds())
                    if t_diff < 120:
                        ret_1h = log.get("return_1h")
                        ret_4h = log.get("return_4h")
                        parts = []
                        if ret_1h is not None:
                            color = "var(--success-color)" if ret_1h >= 0 else "var(--danger-color)"
                            parts.append(f"+1h: <span style='color: {color}; font-family: monospace; font-weight: bold;'>{ret_1h:+.2f}%</span>")
                        if ret_4h is not None:
                            color = "var(--success-color)" if ret_4h >= 0 else "var(--danger-color)"
                            parts.append(f"+4h: <span style='color: {color}; font-family: monospace; font-weight: bold;'>{ret_4h:+.2f}%</span>")
                        if parts:
                            feedback_str = " / ".join(parts)
                        else:
                            feedback_str = "<span style='color: #f59e0b; font-weight: 600;'>Awaiting (+1h)</span>"
                        break
                except Exception:
                    pass

        exec_type = t.get("execution_type", "cron_macro")
        if exec_type == "hybrid_websocket_trigger":
            type_badge = "<span style='margin-left: 8px; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2);'>⚡ WS Trigger</span>"
        else:
            type_badge = "<span style='margin-left: 8px; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2);'>Cron Macro</span>"

        trades_rows.append(f'''
        <tr style="transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='rgba(255,255,255,0.05)'" onmouseout="this.style.backgroundColor='transparent'">
            <td style="padding: 12px; color: var(--text-muted); font-family: monospace; font-size: 12px;">{t["timestamp"]}</td>
            <td style="padding: 12px; font-weight: bold; color: var(--text-main);">{t["symbol"]}</td>
            <td style="padding: 12px;">
                <span style="padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; background: rgba(16, 185, 129, 0.1); color: var(--success-color); border: 1px solid rgba(16, 185, 129, 0.2);">BUY</span>
                {type_badge}
            </td>
            <td style="padding: 12px; color: var(--text-secondary); font-family: monospace;">${t["price"]:.2f}</td>
            <td style="padding: 12px; font-family: monospace; color: var(--text-muted);">{(t.get("notional") or 0.0):.2f}</td>
            <td style="padding: 12px; color: var(--text-muted); max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 12px;" title="{t['reasoning']}">{t['reasoning'][:100]}...</td>
            <td style="padding: 12px; text-align: right;">{feedback_str}</td>
        </tr>
        ''')
    return "\n".join(trades_rows)

def get_ai_rows_html(offset=0, limit=20):
    from data.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_analytics WHERE action NOT LIKE 'SHADOW_%' ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset))
        ai_logs = [dict(row) for row in cursor.fetchall()]
        
    ai_rows = []
    for log in ai_logs:
        ret_1h = log.get('return_1h')
        ret_4h = log.get('return_4h')
        pnl_text = ""
        if ret_1h is not None:
            color = "var(--success-color)" if ret_1h > 0 else "var(--danger-color)"
            pnl_text += f"<span style='color: {color}; margin-right: 8px;'>1h: {ret_1h:.2f}%</span>"
        if ret_4h is not None:
            color = "var(--success-color)" if ret_4h > 0 else "var(--danger-color)"
            pnl_text += f"<span style='color: {color};'>4h: {ret_4h:.2f}%</span>"
        if not pnl_text:
            pnl_text = "<span style='color: var(--text-muted);'>Waiting...</span>"
            
        action = log['action']
        if action == "BUY":
            action_style = "background: rgba(16, 185, 129, 0.1); color: var(--success-color); border: 1px solid rgba(16, 185, 129, 0.2);"
        else:
            action_style = "background: rgba(100, 116, 139, 0.1); color: var(--text-muted); border: 1px solid rgba(100, 116, 139, 0.2);"
        
        ai_rows.append(f'''
        <tr style="transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='rgba(255,255,255,0.05)'" onmouseout="this.style.backgroundColor='transparent'">
            <td style="padding: 16px 24px; color: var(--text-secondary);">{log['timestamp']}</td>
            <td style="padding: 16px 24px; font-weight: bold; color: var(--text-main);">{log['asset']}</td>
            <td style="padding: 16px 24px;">
                <span style="padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; {action_style}">{action}</span>
            </td>
            <td style="padding: 16px 24px; color: var(--text-secondary); font-family: monospace;">${log['price']:.2f}</td>
            <td style="padding: 16px 24px; text-align: right; font-family: monospace; font-size: 14px;">{pnl_text}</td>
        </tr>
        ''')
    return "\n".join(ai_rows)

def get_shadow_rows_html(offset=0, limit=20):
    from data.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_analytics WHERE action LIKE 'SHADOW_%' ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset))
        shadow_logs = [dict(row) for row in cursor.fetchall()]
        
    shadow_rows = []
    for log in shadow_logs:
        ret_1h = log.get('return_1h')
        ret_4h = log.get('return_4h')
        pnl_text = ""
        if ret_1h is not None:
            color = "var(--success-color)" if ret_1h > 0 else "var(--danger-color)"
            pnl_text += f"<span style='color: {color}; margin-right: 8px;'>1h: {ret_1h:.2f}%</span>"
        if ret_4h is not None:
            color = "var(--success-color)" if ret_4h > 0 else "var(--danger-color)"
            pnl_text += f"<span style='color: {color};'>4h: {ret_4h:.2f}%</span>"
        if not pnl_text:
            pnl_text = "<span style='color: var(--text-muted);'>Waiting...</span>"
            
        action = log['action'].replace("SHADOW_", "")
        action_style = "background: rgba(139, 92, 246, 0.1); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.2);"
        
        shadow_rows.append(f'''
        <tr style="transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='rgba(255,255,255,0.05)'" onmouseout="this.style.backgroundColor='transparent'">
            <td style="padding: 16px 24px; color: var(--text-secondary);">{log['timestamp']}</td>
            <td style="padding: 16px 24px; font-weight: bold; color: var(--text-main);">{log['asset']}</td>
            <td style="padding: 16px 24px;">
                <span style="padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; {action_style}">{action} (Shadow)</span>
            </td>
            <td style="padding: 16px 24px; color: var(--text-secondary); font-family: monospace;">${log['price']:.2f}</td>
            <td style="padding: 16px 24px; text-align: right; font-family: monospace; font-size: 14px;">{pnl_text}</td>
        </tr>
        ''')
    return "\n".join(shadow_rows)
