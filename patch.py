import sys

with open('reporting/generator.py', 'r', encoding='utf-8') as f:
    content = f.read()

search_str = '''}, 5000);
                ping.classList.remove("hidden");
                dot.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
                btn.classList.remove("border-slate-800", "text-slate-400");
                btn.classList.add("border-emerald-500/50", "text-emerald-400");
            }
        });

        // Market Clock Logic
        function updateMarketClock() {
            const now = new Date();
            const nyTimeString = now.toLocaleString("en-US", {timeZone: "America/New_York"});
            const nyTime = new Date(nyTimeString);
            
            const day = nyTime.getDay();'''

replace_str = '''}}, 5000);
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
            
            const day = nyTime.getDay();'''

new_content = content.replace(search_str, replace_str)

end_search = '''        updateMarketClock();
    </script>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Interactive Control Room successfully generated at {html_path}")

if __name__ == "__main__":
    generate_dashboard()'''
end_replace = '''        updateMarketClock();
    </script>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Interactive Control Room successfully generated at {html_path}")

if __name__ == "__main__":
    generate_dashboard()'''

new_content = new_content.replace(
'''            if (!isWeekend && currentTimeStr >= marketOpen && currentTimeStr < marketClose) {''', 
'''            if (!isWeekend && currentTimeStr >= marketOpen && currentTimeStr < marketClose) {{'''
).replace(
'''                status = "OPEN";
                color = "text-emerald-400";
                timeDiff = marketClose - currentTimeStr;
            } else {''',
'''                status = "OPEN";
                color = "text-emerald-400";
                timeDiff = marketClose - currentTimeStr;
            }} else {{'''
).replace(
'''                status = "CLOSED";
                color = "text-rose-400";
                if (isWeekend) {''',
'''                status = "CLOSED";
                color = "text-rose-400";
                if (isWeekend) {{'''
).replace(
'''                    let daysToAdd = day === 6 ? 2 : 1;
                    timeDiff = (24 * 3600 - currentTimeStr) + marketOpen + ((daysToAdd - 1) * 24 * 3600);
                } else {''',
'''                    let daysToAdd = day === 6 ? 2 : 1;
                    timeDiff = (24 * 3600 - currentTimeStr) + marketOpen + ((daysToAdd - 1) * 24 * 3600);
                }} else {{'''
).replace(
'''                    if (currentTimeStr < marketOpen) {''',
'''                    if (currentTimeStr < marketOpen) {{'''
).replace(
'''                        timeDiff = marketOpen - currentTimeStr;
                    } else {''',
'''                        timeDiff = marketOpen - currentTimeStr;
                    }} else {{'''
).replace(
'''                        let daysToAdd = day === 5 ? 3 : 1;
                        timeDiff = (24 * 3600 - currentTimeStr) + marketOpen + ((daysToAdd - 1) * 24 * 3600);
                    }
                }
            }''',
'''                        let daysToAdd = day === 5 ? 3 : 1;
                        timeDiff = (24 * 3600 - currentTimeStr) + marketOpen + ((daysToAdd - 1) * 24 * 3600);
                    }}
                }}
            }}'''
).replace(
'''            if (statusEl && timerEl) {
                statusEl.textContent = status;
                statusEl.className = "text-xs font-bold " + color;
                timerEl.textContent = timerStr;
            }
        }''',
'''            if (statusEl && timerEl) {{
                statusEl.textContent = status;
                statusEl.className = "text-xs font-bold " + color;
                timerEl.textContent = timerStr;
            }}
        }}'''
)

with open('reporting/generator.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print('File patched!')
