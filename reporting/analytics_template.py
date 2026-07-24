import os
import json

def generate_analytics_page():
    html_path = 'analytics.html'
    
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
                        <span class="ml-1.5 text-xs font-semibold px-2 py-0.5 bg-purple-500/10 text-purple-400 rounded-full border border-purple-500/20">Analytics</span>
                    </div>
                    
                    <!-- Tab Links -->
                    <div class="hidden md:flex items-center gap-2 ml-10">
                        <a href="/" class="text-sm font-bold text-slate-400 hover:text-white px-4 py-1.5 transition-colors rounded-lg hover:bg-slate-800/50">Dashboard</a>
                        <a href="/analytics" class="text-sm font-bold text-white px-4 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700 shadow-sm">Analytics</a>
                    </div>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
        <div class="mx-auto max-w-7xl">
            <!-- Shadow vs Real Performance Section -->
            <div class="mb-8">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-xl font-bold text-white"><span class="text-amber-500 mr-2">📈</span> Shadow vs Real Performance</h2>
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
                            <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Real Strategy</h3>
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
                            <h3 class="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">Shadow Strategy</h3>
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
                                    <th class="p-4 font-semibold text-emerald-400">Real PnL</th>
                                    <th class="p-4 font-semibold text-purple-400">Shadow PnL</th>
                                    <th class="p-4 font-semibold">Real Win Rate</th>
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
                                label: 'Real PnL (%)',
                                data: realData,
                                borderColor: '#10b981',
                                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.4
                            },
                            {
                                label: 'Shadow PnL (%)',
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

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(template)
