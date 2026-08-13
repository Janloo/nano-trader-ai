const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
    page.on('pageerror', err => console.log('BROWSER ERROR:', err.message));
    
    // Auto-accept the dialog
    page.on('dialog', async dialog => {
        console.log('DIALOG APPEARED:', dialog.message());
        await dialog.dismiss();
    });

    await page.goto('http://127.0.0.1:8080/');
    await page.waitForTimeout(1000);
    console.log('Clicking SOFT STOP...');
    await page.evaluate(() => {
        const btn = document.querySelector('button[onclick*="soft_stop"]');
        if (btn) {
            btn.click();
        } else {
            console.log('Button not found');
        }
    });
    await page.waitForTimeout(2000);
    await browser.close();
})();
