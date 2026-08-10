import asyncio
from alpaca.data.live.crypto import CryptoDataStream
from config.settings import APCA_API_KEY_ID, APCA_API_SECRET_KEY

async def main():
    stream = CryptoDataStream(APCA_API_KEY_ID, APCA_API_SECRET_KEY)
    
    async def bar_callback(bar):
        print(f"BAR: {bar}")
        
    async def quote_callback(quote):
        print(f"QUOTE: {quote}")
        
    async def trade_callback(trade):
        print(f"TRADE: {trade}")

    stream.subscribe_bars(bar_callback, "SOL/USD", "BTC/USD")
    stream.subscribe_quotes(quote_callback, "SOL/USD", "BTC/USD")
    stream.subscribe_trades(trade_callback, "SOL/USD", "BTC/USD")
    
    print("Starting stream...")
    await stream._run_forever()

if __name__ == "__main__":
    asyncio.run(main())
