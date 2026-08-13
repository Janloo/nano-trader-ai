
    // --- Chart Initialization ---
    const ctx = document.getElementById('equityChart').getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 350);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.5)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

    const equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Equity Curve',
                data: [],
                borderColor: '#3b82f6',
                backgroundColor: gradient,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 6,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false, color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b' } }
            },
            interaction: { intersect: false, mode: 'index' }
        }
    });

    // --- Mock Data Injection for Preview ---
    
    // Generate random volume bars
    const volContainer = document.getElementById('volumeBars');
    for(let i=0; i<30; i++) {
        const bar = document.createElement('div');
        bar.className = 'vol-bar';
        bar.style.height = `${Math.random() * 50 + 10}%`;
        volContainer.appendChild(bar);
    }

    // Simulate Live Updates
    setInterval(() => {
        // Update Volume
        const bars = document.getElementsByClassName('vol-bar');
        for(let i=0; i<bars.length-1; i++) {
            bars[i].style.height = bars[i+1].style.height;
            bars[i].className = bars[i+1].className;
        }
        const newHeight = Math.random() * 60 + 10;
        const isSpike = Math.random() > 0.9;
        bars[bars.length-1].style.height = `${newHeight}%`;
        bars[bars.length-1].className = isSpike ? 'vol-bar spike' : 'vol-bar';
        if (isSpike) {
            document.getElementById('volMultiplier').innerText = `${(Math.random() * 2 + 2).toFixed(1)}x`;
        } else {
            document.getElementById('volMultiplier').innerText = `1.${Math.floor(Math.random()*9)}x`;
        }

        // Update Squeeze Radar
        const bandwidth = 0.001 + Math.random() * 0.01;
        document.getElementById('bandwidthValue').innerText = bandwidth.toFixed(4);
        const radar = document.getElementById('bollingerBands');
        const status = document.getElementById('squeezeStatus');
        
        if(bandwidth < 0.002) {
            radar.style.borderColor = 'var(--danger-color)';
            radar.style.transform = 'scale(0.8)';
            status.innerText = "SQUEEZE DETECTED";
            status.style.color = 'var(--danger-color)';
        } else {
            radar.style.borderColor = 'rgba(255,255,255,0.1)';
            radar.style.transform = 'scale(1)';
            status.innerText = "NORMAL";
            status.style.color = 'var(--warn-color)';
        }
    }, 1000);

    // Fetch Live Data
    async function updateDashboard() {
        try {
            const response = await fetch('/api/dashboard_fragments');
            if (response.ok) {
                const data = await response.json();
                
                // Update Equity Chart
                if (data.history_raw && data.history_raw.length > 0) {
                    const sessionStartEquity = data.history_raw[0].equity || 0;
                    const hftBudgetPct  = data.hft_budget_pct || 0.4;        // from API (new field)
                    const budgetStart   = sessionStartEquity * hftBudgetPct; // session budget allocation

                    // Transform: budget_base + session_pnl
                    const chartData = data.history_raw.map(d => budgetStart + (d.equity - sessionStartEquity));

                    equityChart.data.labels = data.history_raw.map(d => {
                        const parts = d.timestamp.split('T');
                        return parts.length > 1 ? parts[1].substring(0, 8) : d.timestamp;
                    });
                    equityChart.data.datasets[0].data = chartData;
                    equityChart.update();

                    const currentEquity    = data.current_equity || 0;
                    const allocatedCapital = data.allocated_capital || (currentEquity * hftBudgetPct);
                    const pnlPct           = data.pnl_pct || 0;
                    const pnlAbs           = currentEquity - sessionStartEquity; // session $ pnl

                    // Feed equity into settings modal for live $ calculations
                    window._dashboardEquity = currentEquity;

                    // Conto Totale (secondary, top-right)
                    document.getElementById('totalEquityValue').innerText =
                        `$${currentEquity.toLocaleString('it-IT', {minimumFractionDigits:2, maximumFractionDigits:2})}`;

                    // Primary Breakdown
                    const budgetCurrent = budgetStart + pnlAbs;

                    document.getElementById('budgetCurrentValue').innerText =
                        `$${budgetCurrent.toLocaleString('it-IT', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
                        
                    document.getElementById('budgetStartValue').innerText =
                        `$${budgetStart.toLocaleString('it-IT', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
                    
                    const pnlAbsEl = document.getElementById('pnlAbsValue');
                    pnlAbsEl.innerText = `${pnlAbs >= 0 ? '+$' : '-$'}${Math.abs(pnlAbs).toLocaleString('it-IT', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
                    pnlAbsEl.style.color = pnlAbs >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
                    
                    const pnlEl = document.getElementById('pnlValue');
                    pnlEl.innerText  = `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`;
                    pnlEl.style.color = pnlPct >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
                }

                // Process incoming trades
                if (data.trades_raw && data.trades_raw.length > 0) {
                    const feed = document.getElementById('tradeFeed');
                    feed.innerHTML = ''; 
                    data.trades_raw.slice(0, 15).forEach(trade => {
                        const item = document.createElement('div');
                        item.className = 'log-item';
                        const action = trade.action ? trade.action.toLowerCase() : '';
                        if (action === 'buy') item.classList.add('buy');
                        else if (action === 'sell') item.classList.add('sell');
                        else if (action === 'profit') item.classList.add('tp');
                        
                        const timeParts = trade.timestamp.split('T');
                        const timeStr = timeParts.length > 1 ? timeParts[1].substring(0, 8) : trade.timestamp;
                        const price = trade.price ? trade.price.toFixed(4) : '0.0000';
                        const qty = trade.qty ? trade.qty.toFixed(4) : '0.0000';
                        
                        item.innerHTML = `
                            <span class="log-time">${timeStr}</span>
                            <span class="log-content">${trade.action} ${qty} ${trade.symbol} @ $${price}</span>
                        `;
                        feed.appendChild(item);
                    });
                }
            }
        } catch(e) {
            console.log("Waiting for API server...");
        }
    }
    
    async function updateEmergencyStatus() {
        try {
            const resp = await fetch('/api/emergency/status');
            const data = await resp.json();
            
            const panel = document.getElementById('killSwitchPanel');
            const indicator = document.getElementById('botStatusIndicator');
            const text = document.getElementById('botStatusText');
            const controls = document.getElementById('killSwitchControls');
            const resume = document.getElementById('resumeControls');
            const reasonDiv = document.getElementById('statusReason');
            const reasonText = document.getElementById('reasonText');

            if (data.locked) {
                indicator.style.backgroundColor = '#ef4444';
                indicator.style.boxShadow = '0 0 10px #ef4444';
                text.innerText = 'DISABLED';
                text.style.color = '#ef4444';
                
                controls.style.display = 'none';
                resume.style.display = 'flex';
                
                reasonText.innerText = data.status;
                reasonDiv.style.display = 'block';
                panel.style.border = '1px solid #ef4444';
            } else {
                indicator.style.backgroundColor = '#22c55e';
                indicator.style.boxShadow = '0 0 10px #22c55e';
                text.innerText = 'ACTIVE';
                text.style.color = 'white';
                
                controls.style.display = 'flex';
                resume.style.display = 'none';
                reasonDiv.style.display = 'none';
                panel.style.border = '1px solid rgba(255,255,255,0.1)';
            }
        } catch (e) {}
    }

    async function triggerEmergency(type) {
        let msg = type === 'hard_stop' 
            ? "⚠️ ATTENTION: HARD STOP will instantly liquidate all open positions at market price. This may cause slippage! Are you sure?"
            : "SOFT STOP will block new trades but let existing positions close normally (TP/SL). Proceed?";
        
        if (confirm(msg)) {
            await fetch('/api/emergency/' + type, { method: 'POST' });
            updateEmergencyStatus();
        }
    }

    async function resumeTrading() {
        if (confirm("Resume normal trading operations?")) {
            await fetch('/api/emergency/resume', { method: 'POST' });
            updateEmergencyStatus();
        }
    }

    setInterval(updateEmergencyStatus, 2000);
    updateEmergencyStatus();

    setInterval(updateDashboard, 5000);
    updateDashboard();

    function clearLogs() {
        document.getElementById('tradeFeed').innerHTML = '';
    }
