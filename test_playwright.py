import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        page.on('console', lambda msg: print(f'BROWSER CONSOLE: {msg.text}'))
        page.on('pageerror', lambda exc: print(f'BROWSER ERROR: {exc}'))

        await page.goto('http://127.0.0.1:8080/')
        await page.wait_for_timeout(1000)

        print('Clicking SOFT STOP...')
        
        async def handle_dialog(dialog):
            print(f'DIALOG: {dialog.message}')
            await dialog.accept()
            
        page.on('dialog', handle_dialog)

        await page.evaluate('''() => {
            const btn = document.querySelector('button[onclick*="soft_stop"]');
            if (btn) {
                console.log("Button found, clicking");
                btn.click();
            } else {
                console.log("Button not found");
            }
        }''')
        
        await page.wait_for_timeout(2000)
        
        ui_state = await page.evaluate('''() => {
            return document.getElementById('botStatusText').innerText;
        }''')
        print(f'Final UI State: {ui_state}')
        
        await browser.close()

asyncio.run(main())
