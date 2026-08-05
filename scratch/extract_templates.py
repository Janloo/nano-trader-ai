import os
import re

files = ["dashboard.html", "analytics.html", "advanced_chart.html", "hft_chart.html"]

# Base template structure
base_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}NanoTrader AI{% endblock %}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="/static/styles.css">
    {% block extra_head %}{% endblock %}
</head>
<body>

    <nav>
        <div class="brand-container">
            <div class="brand-logo">N</div>
            <div class="brand-text">NanoTrader AI</div>
            <div class="nav-links">
                <a href="/" class="nav-link {% if active_page == 'dashboard' %}active{% endif %}">Dashboard</a>
                <a href="/analytics" class="nav-link {% if active_page == 'analytics' %}active{% endif %}">Analytics</a>
                <a href="/advanced-chart" class="nav-link {% if active_page == 'advanced_chart' %}active{% endif %}">Advanced Chart</a>
                <a href="/hft-chart" class="nav-link {% if active_page == 'hft_chart' %}active{% endif %}">HFT Chart</a>
            </div>
        </div>
        <div class="nav-controls">
            <button onclick="openSettings()" style="background: none; border: 1px solid var(--panel-border); color: var(--text-muted); padding: 6px 12px; border-radius: 6px; cursor: pointer;">&#9881; Settings</button>
            <div class="status-badge">
                <div class="pulse-dot"></div>
                Live Engine Active
            </div>
        </div>
    </nav>

    {% block content %}{% endblock %}

    <!-- Settings Modal -->
    <div id="settingsModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title">Live Engine Settings</div>
                <button class="close-btn" onclick="closeSettings()">&times;</button>
            </div>
            <div class="setting-group">
                <label><input type="checkbox" id="set_vwap"> Enable VWAP Strategy</label>
            </div>
            <div class="setting-group">
                <label>Bollinger Squeeze Threshold (%)</label>
                <input type="number" id="set_squeeze" step="0.001" value="0.005">
            </div>
            <div class="setting-group">
                <label>HFT Budget (%)</label>
                <input type="number" id="set_hft_budget" step="0.01" value="0.4">
            </div>
            <div class="setting-group">
                <label>ATR Stop Loss Multiplier</label>
                <input type="number" id="set_sl_mult" step="0.1" value="2.0">
            </div>
            <div class="setting-group">
                <label>Max Capital Per Trade (%)</label>
                <input type="number" id="set_max_cap" step="0.01" value="0.05">
            </div>
            <button class="save-btn" onclick="saveSettings()">Apply Settings</button>
        </div>
    </div>
    
    <script>
        function openSettings() {
            document.getElementById('settingsModal').classList.add('active');
        }
        function closeSettings() {
            document.getElementById('settingsModal').classList.remove('active');
        }
        function saveSettings() {
            // Simulated save function for the frontend
            alert('Settings applied successfully!');
            closeSettings();
        }
    </script>

    {% block extra_scripts %}{% endblock %}
</body>
</html>
"""

os.makedirs("templates", exist_ok=True)

with open("templates/base.html", "w", encoding="utf-8") as f:
    f.write(base_html)

for file in files:
    if not os.path.exists(file):
        print(f"File {file} not found, skipping...")
        continue
        
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract title
    title_match = re.search(r'<title>(.*?)</title>', content)
    title = title_match.group(1) if title_match else "NanoTrader AI"

    # Extract content between </nav> and the first <script> that is not chart.js
    # We can split the body
    body_match = re.search(r'</nav>(.*?)<script', content, re.DOTALL)
    if body_match:
        page_content = body_match.group(1).strip()
    else:
        # Fallback if no script or no nav
        if '</nav>' in content:
            page_content = content.split('</nav>')[1].split('</body>')[0].strip()
        else:
            page_content = ""

    # Remove settings modal from page_content if it exists
    page_content = re.sub(r'<div id="settingsModal".*?</div>\s*</div>\s*</div>', '', page_content, flags=re.DOTALL)

    # Extract scripts
    # Find all <script>...</script> blocks
    scripts = ""
    for script_match in re.finditer(r'<script>(.*?)</script>', content, re.DOTALL):
        script_code = script_match.group(1)
        if 'openSettings' in script_code and 'closeSettings' in script_code and 'saveSettings' in script_code:
            # Skip the settings script
            continue
        scripts += f"\n<script>{script_code}</script>"

    # active_page logic
    if file == "dashboard.html":
        active_page = "dashboard"
    elif file == "analytics.html":
        active_page = "analytics"
    elif file == "advanced_chart.html":
        active_page = "advanced_chart"
    elif file == "hft_chart.html":
        active_page = "hft_chart"
        
    new_template = f"{{% extends 'base.html' %}}\n\n"
    new_template += f"{{% set active_page = '{active_page}' %}}\n\n"
    new_template += f"{{% block title %}}{title}{{% endblock %}}\n\n"
    new_template += f"{{% block content %}}\n{page_content}\n{{% endblock %}}\n\n"
    new_template += f"{{% block extra_scripts %}}{scripts}\n{{% endblock %}}\n"

    with open(os.path.join("templates", file), "w", encoding="utf-8") as f:
        f.write(new_template)
    print(f"Created templates/{file}")

