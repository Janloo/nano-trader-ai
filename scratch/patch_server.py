import os
import re

with open("server.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add jinja2 imports at the top
if "from jinja2 import Environment" not in content:
    content = content.replace(
        "from http.server import BaseHTTPRequestHandler, HTTPServer",
        "from http.server import BaseHTTPRequestHandler, HTTPServer\nfrom jinja2 import Environment, FileSystemLoader"
    )

# Setup Jinja2 environment globally
jinja_setup = """
# Setup Jinja2 environment
templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(templates_dir))

def render_template(template_name, **context):
    template = jinja_env.get_template(template_name)
    return template.render(**context).encode('utf-8')
"""
if "jinja_env = Environment" not in content:
    content = content.replace("class DashboardHTTPHandler", jinja_setup + "\nclass DashboardHTTPHandler")

# Replace route serving
def replace_route(content, path, template_name):
    # Regex to find the if block for a specific path
    # Example: if clean_path == "/": ... (up to next if clean_path or end of method)
    pattern = re.compile(rf'if clean_path == "{path}":.*?return\n', re.DOTALL)
    
    new_code = f"""if clean_path == "{path}":
            try:
                rendered_html = render_template("{template_name}")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_cors_headers()
                self.end_headers()
                self._safe_write(rendered_html)
            except Exception as e:
                self.send_error(500, f"Server error: {{e}}")
            return\n"""
            
    return pattern.sub(new_code, content)

content = replace_route(content, "/", "dashboard.html")
content = replace_route(content, "/analytics", "analytics.html")
content = replace_route(content, "/advanced-chart", "advanced_chart.html")
content = replace_route(content, "/hft-chart", "hft_chart.html")

with open("server.py", "w", encoding="utf-8") as f:
    f.write(content)

print("server.py patched successfully.")
