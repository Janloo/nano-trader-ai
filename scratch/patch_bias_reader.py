"""
Patch script: replace the inline BiasReader class in realtime_executor.py
with 'from data.bias_reader import BiasReader'.
Handles the UTF-8 box-drawing characters correctly.
"""
import re

path = "realtime_executor.py"

with open(path, "r", encoding="utf-8") as f:
    src = f.read()

# Find the BiasReader class block (from the separator comment to the end of get_bias_for_symbol)
pattern = re.compile(
    r'# [─\-]{10,}\n'           # separator line
    r'# BiasReader.*?\n'        # BiasReader heading
    r'# [─\-]{10,}\n'           # second separator
    r'class BiasReader:.*?'     # class body
    r'return \{[^\n]*not in current AI selection[^\n]*\}\n',  # last return
    re.DOTALL
)

replacement = "from data.bias_reader import BiasReader\n"

new_src, count = re.subn(pattern, replacement, src)
if count == 0:
    print("ERROR: Pattern not found. No changes made.")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)
    print(f"OK: Replaced {count} block(s).")
