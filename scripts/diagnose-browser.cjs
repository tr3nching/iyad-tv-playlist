const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const results = [];
    page.on('response', async response => {
      const url = new URL(response.url());
      if (url.hostname !== 'auth.iyad.click' || !['/key', '/data', '/play'].includes(url.pathname)) return;
      let payload = {}; try { payload = await response.json(); } catch {}
      results.push({ endpoint: url.pathname, status: response.status(), successShape: response.ok() && typeof payload[url.pathname === '/key' ? 'key' : 'data'] === 'string',
        error: typeof payload.error === 'string' ? payload.error.replace(/https?:\/\/\S+/g, '[URL omitted]').slice(0, 180) : undefined });
    });
    await page.goto('https://iyad.click/', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(10000);
    await page.evaluate(async () => {
      await fetch('https://auth.iyad.click/play', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channelName: 'SYFY', serverIndex: 1 }) });
    });
    await page.waitForTimeout(1000);
    console.log(JSON.stringify({ client: 'actual Chromium website session', results }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error.name); process.exitCode = 1; });
