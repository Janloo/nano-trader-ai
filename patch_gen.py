# -*- coding: utf-8 -*-
import re

with open('reporting/generator.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Navbar link
old_nav = '''                        <div class="hidden md:flex items-center gap-2 ml-10">
                            <a href="/" class="text-sm font-bold text-white px-4 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700 shadow-sm">Dashboard</a>
                            <a href="/analytics" class="text-sm font-bold text-slate-400 hover:text-white px-4 py-1.5 transition-colors rounded-lg hover:bg-slate-800/50">Analytics</a>
                            <a href="/hft-chart" class="text-sm font-bold text-slate-400 hover:text-white px-4 py-1.5 transition-colors rounded-lg hover:bg-slate-800/50">HFT Mechanisms</a>
                        </div>'''
new_nav = '''                        <div class="hidden md:flex items-center gap-2 ml-10">
                            <a href="/" class="text-sm font-bold text-white px-4 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700 shadow-sm">Dashboard</a>
                            <a href="/advanced-chart" class="text-sm font-bold text-slate-400 hover:text-white px-4 py-1.5 transition-colors rounded-lg hover:bg-slate-800/50">Adv. Chart</a>
                            <a href="/analytics" class="text-sm font-bold text-slate-400 hover:text-white px-4 py-1.5 transition-colors rounded-lg hover:bg-slate-800/50">Analytics</a>
                            <a href="/hft-chart" class="text-sm font-bold text-slate-400 hover:text-white px-4 py-1.5 transition-colors rounded-lg hover:bg-slate-800/50">HFT Mechanisms</a>
                        </div>'''
code = code.replace(old_nav, new_nav)

# 2. HTML buttons
old_btns = '''                        <div class="flex gap-2 bg-slate-950 p-1 rounded-xl border border-slate-800/60">
                            <button id="wsTabBTC" onclick="switchWSSymbol('BTCUSD')" class="px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-600 text-white transition-all">BTCUSD</button>
                            <button id="wsTabETH" onclick="switchWSSymbol('ETHUSD')" class="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-white transition-all">ETHUSD</button>
                        </div>'''
new_btns = '''                        <div class="flex gap-2 bg-slate-950 p-1 rounded-xl border border-slate-800/60" id="wsSymbolTabs">
                            <!-- JS fills this -->
                        </div>'''
code = code.replace(old_btns, new_btns)

# 3. activeWSSymbol JS logic
old_js1 = '''        let wsChartInstance = null;
        let activeWSSymbol = 'BTCUSD';

        function renderWSRealtimeChart(symbol, isSilentUpdate = false) {{'''

new_js1 = '''        let wsChartInstance = null;
        let activeWSSymbol = null;

        function updateWSSymbolTabs() {{
            const tabsContainer = document.getElementById('wsSymbolTabs');
            if (!tabsContainer || !priceHistoryData) return;
            const symbols = Object.keys(priceHistoryData);
            if (symbols.length === 0) return;
            
            if (!activeWSSymbol || !symbols.includes(activeWSSymbol)) {{
                activeWSSymbol = symbols[0];
            }}
            
            tabsContainer.innerHTML = '';
            symbols.forEach(sym => {{
                const btn = document.createElement('button');
                btn.onclick = () => switchWSSymbol(sym);
                if (sym === activeWSSymbol) {{
                    btn.className = "px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-600 text-white transition-all";
                }} else {{
                    btn.className = "px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-white transition-all";
                }}
                btn.textContent = sym;
                tabsContainer.appendChild(btn);
            }});
        }}

        function renderWSRealtimeChart(symbol, isSilentUpdate = false) {{'''
code = code.replace(old_js1, new_js1)

# 4. switchWSSymbol logic
old_js2 = '''        function switchWSSymbol(symbol) {{
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
        }});'''

new_js2 = '''        function switchWSSymbol(symbol) {{
            activeWSSymbol = symbol;
            updateWSSymbolTabs();
            renderWSRealtimeChart(symbol);
        }}

        // Initialize WS chart
        window.addEventListener("DOMContentLoaded", () => {{
            updateWSSymbolTabs();
            if (activeWSSymbol) renderWSRealtimeChart(activeWSSymbol);
        }});'''
code = code.replace(old_js2, new_js2)

# 5. refreshDashboardData logic
old_js3 = '''                // WS Chart — update priceHistoryData and re-render
                if (data.price_history_raw) {{
                    priceHistoryData = data.price_history_raw;
                    const loader = document.getElementById('wsChartLoader');
                    const hasData = priceHistoryData[activeWSSymbol] && priceHistoryData[activeWSSymbol].length > 0;
                    if (loader) loader.style.display = hasData ? 'none' : 'flex';
                    if (typeof renderWSRealtimeChart === 'function') {{
                        renderWSRealtimeChart(activeWSSymbol, !!wsChartInstance);
                    }}
                }}'''

new_js3 = '''                // WS Chart — update priceHistoryData and re-render
                if (data.price_history_raw) {{
                    priceHistoryData = data.price_history_raw;
                    updateWSSymbolTabs();
                    const loader = document.getElementById('wsChartLoader');
                    const hasData = activeWSSymbol && priceHistoryData[activeWSSymbol] && priceHistoryData[activeWSSymbol].length > 0;
                    if (loader) loader.style.display = hasData ? 'none' : 'flex';
                    if (typeof renderWSRealtimeChart === 'function' && activeWSSymbol) {{
                        renderWSRealtimeChart(activeWSSymbol, !!wsChartInstance);
                    }}
                }}'''
code = code.replace(old_js3, new_js3)

with open('reporting/generator.py', 'w', encoding='utf-8') as f:
    f.write(code)

print('Success')
