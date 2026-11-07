// Compare public request styles without logging encrypted payloads or playback settings.
const base = 'https://auth.iyad.click';
const origin = 'https://iyad.click';
const profiles = [
  { name: 'website-style', headers: { Origin: origin, Referer: `${origin}/` } },
  { name: 'updater-style', headers: { Origin: origin, Referer: `${origin}/`, 'User-Agent': 'Mozilla/5.0' }, fresh: true },
  { name: 'browser-headers', headers: { Origin: origin, Referer: `${origin}/`, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', Accept: '*/*', 'Accept-Language': 'en-US,en;q=0.9', 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-site' } },
];
const results = [];
for (const profile of profiles) {
  for (const endpoint of ['key', 'data', 'play']) {
    const started = Date.now();
    try {
      const response = await fetch(`${base}/${endpoint}${endpoint === 'data' && profile.fresh ? `?refresh=${Date.now()}` : ''}`, {
        method: endpoint === 'play' ? 'POST' : 'GET',
        headers: { ...profile.headers, ...(endpoint === 'play' ? { 'Content-Type': 'application/json' } : {}) },
        ...(endpoint === 'play' ? { body: JSON.stringify({ channelName: 'SYFY', serverIndex: 1 }) } : {}),
        signal: AbortSignal.timeout(15000),
      });
      let payload = {}; try { payload = await response.json(); } catch {}
      const error = typeof payload.error === 'string' ? payload.error.replace(/https?:\/\/\S+/g, '[URL omitted]').replace(/[\r\n]/g, ' ').slice(0, 180) : undefined;
      results.push({ profile: profile.name, endpoint, status: response.status, successShape: response.ok && typeof payload[endpoint === 'key' ? 'key' : 'data'] === 'string', error,
        cacheStatus: response.headers.get('cf-cache-status'), age: response.headers.get('age'),
        edge: response.headers.get('cf-ray')?.split('-').pop(), elapsedMs: Date.now() - started });
    } catch (error) {
      results.push({ profile: profile.name, endpoint, errorType: error.name, elapsedMs: Date.now() - started });
    }
  }
}
console.log(JSON.stringify({ checkedAt: new Date().toISOString(), environment: process.env.GITHUB_ACTIONS === 'true' ? 'GitHub' : 'local', results }, null, 2));
