import os
import json

def generate_analytics_page():
    html_path = 'analytics.html'
    
    # Calculate Scorecard Metrics from DB
    win_rate = 0.0
    rr_ratio = 0.0
    ev_per_trade = 0.0
    profit_factor = 0.0
    total_trades = 0
    
    db_path = os.path.join("data", "trading_bot.db")
    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Count real trades for the validation counter
            cursor.execute("SELECT count(*) FROM trades")
            row = cursor.fetchone()
            if row:
                total_trades = row[0]
            
            # Calculate real metrics using ai_analytics (where we have exact return_1h)
            cursor.execute("SELECT return_1h FROM ai_analytics WHERE action NOT LIKE 'SHADOW_%' AND return_1h IS NOT NULL")
            logs = cursor.fetchall()
            
            wins = []
            losses = []
            for log in logs:
                ret = log['return_1h']
                if ret > 0:
                    wins.append(ret)
                elif ret < 0:
                    losses.append(abs(ret))
                    
            executed = len(wins) + len(losses)
            if executed > 0:
                win_rate = (len(wins) / executed) * 100
                loss_rate = (len(losses) / executed)
                win_rate_decimal = len(wins) / executed
                
                avg_win = sum(wins) / len(wins) if wins else 0
                avg_loss = sum(losses) / len(losses) if losses else 0
                
                if avg_loss > 0:
                    rr_ratio = avg_win / avg_loss
                    ev_per_trade = (win_rate_decimal * rr_ratio) - (loss_rate * 1)
                    profit_factor = sum(wins) / sum(losses)
                else:
                    rr_ratio = avg_win
                    ev_per_trade = win_rate_decimal * rr_ratio
                    profit_factor = 99.9  # arbitrarily high
                    
            conn.close()
        except Exception as e:
            print(f"Scorecard calculation error: {e}")

    # Load System Errors for UI Alert Banner
    system_errors_html = ""
    error_file_path = os.path.join("data", "state", "system_errors.json")
    if os.path.exists(error_file_path):
        try:
            with open(error_file_path, "r", encoding="utf-8") as f:
                errors = json.load(f)
                if errors:
                    latest = errors[-1]
                    system_errors_html = f'''
                    <div class="mb-6 bg-rose-900/40 border border-rose-500/50 rounded-xl p-4 flex items-start gap-4 shadow-lg shadow-rose-900/20">
                        <div class="bg-rose-500/20 p-2 rounded-lg text-rose-400">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                        </div>
                        <div>
                            <h3 class="text-rose-400 font-bold text-lg">⚠️ FAIL-SAFE TRIGGERED: {latest.get("module", "System")}</h3>
                            <p class="text-sm text-rose-200 mt-1">Context: {latest.get("context", "")}</p>
                            <p class="text-sm text-white font-mono mt-2 bg-black/40 p-2 rounded">{latest.get("error", "")}</p>
                            <p class="text-xs text-rose-500/80 mt-2">Logged at: {latest.get("timestamp", "")}</p>
                        </div>
                    </div>
                    '''
        except Exception:
            pass
            
    pf_color = "text-emerald-400" if profit_factor > 1.2 else "text-rose-400"
    pf_badge = "🟢 Eccellente" if profit_factor >= 1.5 else "🟡 Buono" if profit_factor >= 1.0 else "🔴 Rischio"
    ev_color = "text-emerald-400" if ev_per_trade > 0 else "text-rose-400"
    wr_color = "text-emerald-400" if win_rate > 50 else "text-amber-400"
    
    template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NanoTrader AI - Analytics</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-black text-white flex flex-col">
    <!-- Navigation -->
    <nav class="border-b border-slate-800/80 bg-slate-950/60 backdrop-blur-md sticky top-0 z-40">
        <div class="w-full px-4 sm:px-6 lg:px-8">
            <div class="flex h-16 items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="h-9 w-9 rounded-xl bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                        <svg class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                        </svg>
                    </div>
                    <div>
                        <span class="text-lg font-bold bg-gradient-to-r from-blue-400 to-indigo-200 bg-clip-text text-transparent">Nano-Trader-AI</span>
                        <span class="ml-1.5 text-xs font-semibold px-2 py-0.5 bg-purple-500/10 text-purple-400 rounded-full border border-purple-500/20">Analytics</span>
                    </div>
                    
                    <!-- Premium Tab Links -->
                    <div class="hidden md:flex items-center p-1 bg-slate-900/80 border border-slate-700/50 rounded-2xl shadow-inner ml-8">
                        <a href="/" class="flex items-center gap-2 text-sm font-bold px-4 py-2 transition-all rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
                            Dashboard
                        </a>
                        <a href="/advanced-chart" class="flex items-center gap-2 text-sm font-bold px-4 py-2 transition-all rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"></path></svg>
                            Adv. Chart
                        </a>
                        <a href="/analytics" class="flex items-center gap-2 text-sm font-bold px-4 py-2 transition-all rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-500/20">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
                            Analytics
                        </a>
                        <a href="/hft-chart" class="flex items-center gap-2 text-sm font-bold px-4 py-2 transition-all rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/60">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                            HFT Mechanisms
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
        <div class="w-full">
            __SYSTEM_ERRORS_HTML__
            <!-- Shadow vs Real Performance Section -->
            <div class="mb-8">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-xl font-bold text-white"><span class="text-amber-500 mr-2">📈</span> Alpha vs Basic Method Performance</h2>
                    <select id="assetSelect" class="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-300 focus:outline-none focus:border-amber-500" onchange="loadPerformanceChart(this.value)">
                        <option value="ALL">All Assets</option>
                        <option value="BTCUSD">BTC/USD</option>
                        <option value="ETHUSD">ETH/USD</option>
                        <option value="SOLUSD">SOL/USD</option>
                    </select>
                </div>
                
                <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
                    <div class="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg h-[500px]">
                        <canvas id="performanceChart"></canvas>
                    </div>
                    
                    <div class="space-y-4">
                        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg">
                            <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Basic Method</h3>
                            <div class="flex justify-between items-end mb-2">
                                <span class="text-sm text-slate-500">Cumulative PnL</span>
                                <span id="realPnl" class="text-xl font-bold font-mono text-white">0.00%</span>
                            </div>
                            <div class="flex justify-between items-end">
                                <span class="text-sm text-slate-500">Win Rate</span>
                                <span id="realWinRate" class="text-emerald-400 font-bold font-mono">0%</span>
                            </div>
                        </div>
                        
                        <div class="bg-slate-900 border border-purple-900/30 rounded-xl p-4 shadow-lg relative overflow-hidden">
                            <div class="absolute -right-4 -top-4 w-16 h-16 bg-purple-500/10 rounded-full blur-xl"></div>
                            <h3 class="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">Alpha Strategy</h3>
                            <div class="flex justify-between items-end mb-2">
                                <span class="text-sm text-slate-500">Cumulative PnL</span>
                                <span id="shadowPnl" class="text-xl font-bold font-mono text-white">0.00%</span>
                            </div>
                            <div class="flex justify-between items-end">
                                <span class="text-sm text-slate-500">Win Rate</span>
                                <span id="shadowWinRate" class="text-purple-400 font-bold font-mono">0%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- System Health Scorecard Section -->
            <div class="mb-8">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-xl font-bold text-white"><span class="text-emerald-400 mr-2">🎯</span> System Health Scorecard</h2>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-5 gap-4">
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg text-center relative overflow-hidden group">
                        <div class="absolute inset-0 bg-gradient-to-t from-blue-900/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Total Trades</h3>
                        <p class="text-2xl font-bold font-mono text-white">__TOTAL_TRADES__</p>
                        <p class="text-xs text-slate-500 mt-1">Need 100 for validation</p>
                    </div>
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg text-center relative overflow-hidden group">
                        <div class="absolute inset-0 bg-gradient-to-t from-emerald-900/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Win Rate</h3>
                        <p class="text-2xl font-bold font-mono __WR_COLOR__">__WIN_RATE__%</p>
                    </div>
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg text-center relative overflow-hidden group">
                        <div class="absolute inset-0 bg-gradient-to-t from-amber-900/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Reward/Risk</h3>
                        <p class="text-2xl font-bold font-mono text-amber-400">__RR_RATIO__</p>
                    </div>
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg text-center relative overflow-hidden group">
                        <div class="absolute inset-0 bg-gradient-to-t from-emerald-900/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Expected Value</h3>
                        <p class="text-2xl font-bold font-mono __EV_COLOR__">__EV_PER_TRADE__ R</p>
                    </div>
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg text-center relative overflow-hidden group">
                        <div class="absolute inset-0 bg-gradient-to-t from-blue-900/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Profit Factor</h3>
                        <p class="text-2xl font-bold font-mono __PF_COLOR__">__PROFIT_FACTOR__</p>
                        <p class="text-xs mt-1 font-semibold text-slate-300">__PF_BADGE__</p>
                    </div>
                </div>
            </div>
            
            <!-- Daily Checkpoints Section -->
            <div class="mb-8">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-xl font-bold text-white"><span class="text-blue-400 mr-2">📌</span> Daily Checkpoints</h2>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl shadow-lg overflow-hidden">
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="bg-slate-800/50 border-b border-slate-700/50 text-slate-400 text-xs uppercase tracking-wider">
                                    <th class="p-4 font-semibold">Date</th>
                                    <th class="p-4 font-semibold">Total Equity</th>
                                    <th class="p-4 font-semibold">Available Cash</th>
                                    <th class="p-4 font-semibold text-emerald-400">Basic Method PnL</th>
                                    <th class="p-4 font-semibold text-purple-400">Alpha PnL</th>
                                    <th class="p-4 font-semibold">Basic Win Rate</th>
                                </tr>
                            </thead>
                            <tbody id="checkpointsBody" class="divide-y divide-slate-800/50 text-sm">
                                <tr>
                                    <td colspan="6" class="p-4 text-center text-slate-500">Loading checkpoints...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
        </div>
    </main>

    <script>
        let perfChart = null;

        async function loadPerformanceChart(asset) {
            try {
                const res = await fetch(`/api/performance_comparison?asset=${asset}`);
                const data = await res.json();
                
                document.getElementById('realPnl').innerText = data.real.final_pnl.toFixed(2) + '%';
                document.getElementById('realWinRate').innerText = data.real.win_rate.toFixed(1) + '%';
                
                document.getElementById('shadowPnl').innerText = data.shadow.final_pnl.toFixed(2) + '%';
                document.getElementById('shadowWinRate').innerText = data.shadow.win_rate.toFixed(1) + '%';
                
                // Collect all unique timestamps, sorted
                let timeMap = {};
                data.real.curve.forEach(p => timeMap[p.x] = {real: p.y});
                data.shadow.curve.forEach(p => {
                    if(!timeMap[p.x]) timeMap[p.x] = {};
                    timeMap[p.x].shadow = p.y;
                });
                
                let sortedTimes = Object.keys(timeMap).sort();
                
                let labels = [];
                let realData = [];
                let shadowData = [];
                
                let lastReal = 0;
                let lastShadow = 0;
                
                for(let t of sortedTimes) {
                    labels.push(t.substring(11, 16));
                    
                    if(timeMap[t].real !== undefined) lastReal = timeMap[t].real;
                    if(timeMap[t].shadow !== undefined) lastShadow = timeMap[t].shadow;
                    
                    realData.push(lastReal);
                    shadowData.push(lastShadow);
                }
                
                const ctx = document.getElementById('performanceChart').getContext('2d');
                
                if (perfChart) {
                    perfChart.destroy();
                }
                
                perfChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Basic Method PnL (%)',
                                data: realData,
                                borderColor: '#10b981',
                                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.4
                            },
                            {
                                label: 'Alpha PnL (%)',
                                data: shadowData,
                                borderColor: '#a855f7',
                                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.4
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            mode: 'index',
                            intersect: false,
                        },
                        scales: {
                            x: {
                                display: true,
                                grid: { color: 'rgba(255, 255, 255, 0.05)' }
                            },
                            y: {
                                display: true,
                                grid: { color: 'rgba(255, 255, 255, 0.05)' }
                            }
                        },
                        plugins: {
                            legend: {
                                labels: { color: '#94a3b8' }
                            }
                        }
                    }
                });
                
            } catch(e) {
                console.error("Error loading chart:", e);
            }
        }
        async function loadCheckpoints() {
            try {
                const response = await fetch('/data/checkpoints.json');
                const checkpoints = await response.json();
                
                const tbody = document.getElementById('checkpointsBody');
                tbody.innerHTML = '';
                
                if(!checkpoints || checkpoints.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="p-4 text-center text-slate-500">No checkpoints recorded yet.</td></tr>';
                    return;
                }
                
                // Sort descending by date
                checkpoints.sort((a, b) => new Date(b.date) - new Date(a.date));
                
                checkpoints.forEach(cp => {
                    const row = document.createElement('tr');
                    const realClass = cp.real_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400';
                    const shadowClass = cp.shadow_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400';
                    row.className = "hover:bg-slate-800/30 transition-colors";
                    row.innerHTML = `
                        <td class="p-4 font-mono text-slate-300">${cp.date}</td>
                        <td class="p-4 text-white font-semibold">$${cp.equity.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                        <td class="p-4 text-slate-300">$${cp.cash.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                        <td class="p-4 font-bold ${realClass}">${cp.real_pnl_pct > 0 ? '+' : ''}${cp.real_pnl_pct.toFixed(2)}%</td>
                        <td class="p-4 font-bold ${shadowClass}">${cp.shadow_pnl_pct > 0 ? '+' : ''}${cp.shadow_pnl_pct.toFixed(2)}%</td>
                        <td class="p-4 text-slate-300">${cp.real_winrate.toFixed(1)}%</td>
                    `;
                    tbody.appendChild(row);
                });
                
            } catch(e) {
                console.error("Error loading checkpoints:", e);
                document.getElementById('checkpointsBody').innerHTML = '<tr><td colspan="6" class="p-4 text-center text-rose-500">Error loading checkpoints</td></tr>';
            }
        }

        loadPerformanceChart('ALL');
        loadCheckpoints();
    </script>
</body>
</html>'''

    template = template.replace('__TOTAL_TRADES__', str(total_trades))
    template = template.replace('__TOTAL_TRADES__', str(total_trades))
    template = template.replace('__WIN_RATE__', f"{win_rate:.1f}")
    template = template.replace('__RR_RATIO__', f"{rr_ratio:.2f}")
    template = template.replace('__EV_PER_TRADE__', f"{ev_per_trade:+.3f}")
    template = template.replace('__PROFIT_FACTOR__', f"{profit_factor:.2f}")
    template = template.replace('__PF_BADGE__', str(pf_badge))
    template = template.replace('__WR_COLOR__', str(wr_color))
    template = template.replace('__EV_COLOR__', str(ev_color))
    template = template.replace('__PF_COLOR__', str(pf_color))
    template = template.replace('__SYSTEM_ERRORS_HTML__', system_errors_html)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(template)
