import sys

path = r'c:\sources\nano-trader-ai\backtesting\engine.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

mock_class = """
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return self.current_time
                
        with patch('realtime_executor.datetime', MockDateTime):
            # Optimize loop using itertuples instead of iterrows for massive speedup
            for row in flat_bars.itertuples():
"""

content = content.replace("# Optimize loop using itertuples instead of iterrows for massive speedup\n        for row in flat_bars.itertuples():\n", mock_class)
content = content.replace("            sym = row.symbol\n", "                sym = row.symbol\n")
content = content.replace("            bar_dict = {\n", "                bar_dict = {\n")
content = content.replace("                't': row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else str(row.timestamp),\n", "                    't': row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else str(row.timestamp),\n")
content = content.replace("                'o': row.open,\n", "                    'o': row.open,\n")
content = content.replace("                'h': row.high,\n", "                    'h': row.high,\n")
content = content.replace("                'l': row.low,\n", "                    'l': row.low,\n")
content = content.replace("                'c': row.close,\n", "                    'c': row.close,\n")
content = content.replace("                'v': row.volume,\n", "                    'v': row.volume,\n")
content = content.replace("                'vw': getattr(row, 'vwap', row.close),\n", "                    'vw': getattr(row, 'vwap', row.close),\n")
content = content.replace("                'n': getattr(row, 'trade_count', 0)\n", "                    'n': getattr(row, 'trade_count', 0)\n")
content = content.replace("            }\n", "                }\n")
content = content.replace("            close = float(row.close)\n", "                close = float(row.close)\n")
content = content.replace("            ts = row.timestamp\n", "                ts = row.timestamp\n")
content = content.replace("            \n            self.current_time = ts\n", "                \n                self.current_time = ts\n")
content = content.replace("            sym_clean = sym.replace(\"/\", \"\")\n", "                sym_clean = sym.replace(\"/\", \"\")\n")
content = content.replace("            self.broker.set_simulated_time(\n", "                self.broker.set_simulated_time(\n")
content = content.replace("                ts, \n", "                    ts, \n")
content = content.replace("                price_dict={sym_clean: close},\n", "                    price_dict={sym_clean: close},\n")
content = content.replace("                high_dict={sym_clean: row.high},\n", "                    high_dict={sym_clean: row.high},\n")
content = content.replace("                low_dict={sym_clean: row.low}\n", "                    low_dict={sym_clean: row.low}\n")
content = content.replace("            )\n", "                )\n")
content = content.replace("            \n            bar = MockBar(sym, close, ts, row.high, row.low, row.volume)\n", "                \n                bar = MockBar(sym, close, ts, row.high, row.low, row.volume)\n")
content = content.replace("            # Feed bar to executor\n", "                # Feed bar to executor\n")
content = content.replace("            try:\n", "                try:\n")
content = content.replace("                executor.on_bar(bar)\n", "                    executor.on_bar(bar)\n")
content = content.replace("            except Exception as e:\n", "                except Exception as e:\n")
content = content.replace("                logger.error(f\"Error processing HFT bar: {e}\")\n", "                    logger.error(f\"Error processing HFT bar: {e}\")\n")
content = content.replace("            \n            # Record equity at the end of each day\n", "                \n                # Record equity at the end of each day\n")
content = content.replace("            if ts.hour == 23 and ts.minute == 59:\n", "                if ts.hour == 23 and ts.minute == 59:\n")
content = content.replace("                account = self.broker.get_account_info()\n", "                    account = self.broker.get_account_info()\n")
content = content.replace("                self.equity_curve.append({\n", "                    self.equity_curve.append({\n")
content = content.replace("                    'date': ts.strftime(\"%Y-%m-%d\"),\n", "                        'date': ts.strftime(\"%Y-%m-%d\"),\n")
content = content.replace("                    'equity': float(account.equity),\n", "                        'equity': float(account.equity),\n")
content = content.replace("                    'cash': float(account.cash)\n", "                        'cash': float(account.cash)\n")
content = content.replace("                })\n", "                    })\n")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
