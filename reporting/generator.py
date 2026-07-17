import json
import os
from datetime import datetime

def generate_dashboard():
    """Reads trades.json and ai_analytics_logs.json to auto-generate an interactive Control Room HTML dashboard."""
    json_path = os.path.join("data", "trades.json")
    analytics_path = os.path.join("data", "ai_analytics_logs.json")
    html_path = "dashboard.html"

    # Default structures
    data = {"portfolio_history": [], "trades": []}
    ai_logs = []

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
        except Exception as e:
            print(f"Error loading trades.json for reporting: {e}")

    if os.path.exists(analytics_path):
        try:
            with open(analytics_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    ai_logs = json.loads(content)
        except Exception as e:
            print(f"Error loading ai_analytics_logs.json for reporting: {e}")

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

            trades_rows.append(f"""
            <tr class="hover:bg-slate-900/20 transition-colors">
                <td class="py-3.5 text-slate-400 font-mono text-xs">{datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")}</td>
                <td class="py-3.5"><span class="font-bold text-white">{t["symbol"]}</span></td>
                <td class="py-3.5">
                    <span class="inline-flex items-center rounded-md px-2 py-1 text-xs font-semibold border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                        BUY
                    </span>
                </td>
                <td class="py-3.5 text-right font-mono">{t["qty"]:.6f}</td>
                <td class="py-3.5 text-right font-mono">${t["price"]:.2f}</td>
                <td class="py-3.5 text-right font-mono">${t["notional"]:.2f}</td>
                <td class="py-3.5 text-center font-mono">
                    <span class="px-2 py-0.5 rounded text-xs font-bold {
                        'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' if t.get('sentiment_score', 0) > 0
                        else 'bg-rose-500/10 text-rose-400 border border-rose-500/20' if t.get('sentiment_score', 0) < 0
                        else 'bg-slate-500/10 text-slate-400 border border-slate-500/20'
                    }">
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
                        <!-- Environment selector -->
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Env:</span>
                            <select id="envSelect" onchange="changeEnvironment()" class="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-xs font-bold text-white focus:outline-none focus:border-blue-500 cursor-pointer">
                                <option value="sandbox">Sandbox (Paper)</option>
                                <option value="production">Production (Live)</option>
                            </select>
                        </div>
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
        </main>
        <!-- Toast Notification Container -->
        <div id="toastContainer" class="fixed bottom-5 right-5 z-50 flex flex-col gap-3"></div>
    </div>

    <!-- Data Injection & Chart Script -->
    <script>
        const portfolioData = {json.dumps(history)};
        const tradesData = {json.dumps(trades)};

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

            fetch("http://127.0.0.1:8000/api/config", {{
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

            fetch(`http://127.0.0.1:8000/api/status?${{queryParams.toString()}}`)
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
                    
                    alert("Connection Verification Failure:\\n\\nCould not establish connection to the local Python server (http://127.0.0.1:8000).\\n\\nPlease ensure that the bot server is currently running on your system.");
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
            const error = service === 'alpaca' ? window.alpacaError : window.geminiError;
            if (error && error.trim() !== "") {{
                alert(`${{service.toUpperCase()}} Connection Failure Details:\\n\\n${{error}}`);
            }} else if (error === "") {{
                alert(`${{service.toUpperCase()}} Connection Status:\\n\\nVerification check completed successfully! API keys are active and functional.`);
            }} else {{
                alert(`${{service.toUpperCase()}} Status:\\n\\nVerification check pending... Please save configurations first.`);
            }}
        }}
        window.addEventListener("DOMContentLoaded", loadSavedCredentials);
    </script>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Interactive Control Room successfully generated at {html_path}")
