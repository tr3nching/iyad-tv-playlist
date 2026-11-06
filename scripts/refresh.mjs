import { createDecipheriv } from 'node:crypto';
import { mkdir, writeFile, rename } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const API = 'https://auth.iyad.click';
const headers = {
  Origin: 'https://iyad.click',
  Referer: 'https://iyad.click/',
  'User-Agent': 'Mozilla/5.0',
};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export function decrypt(data, key) {
  const bytes = Buffer.from(data, 'base64');
  if (bytes.length < 32) throw new Error('Invalid encrypted response');
  const keyBytes = Buffer.alloc(16);
  Buffer.from(key, 'utf8').copy(keyBytes, 0, 0, 16);
  const cipher = createDecipheriv('aes-128-cbc', keyBytes, bytes.subarray(0, 16));
  return JSON.parse(Buffer.concat([cipher.update(bytes.subarray(16)), cipher.final()]).toString('utf8'));
}

async function request(path, body) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(`${API}${path}`, {
        headers: { ...headers, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        method: body ? 'POST' : 'GET',
        ...(body ? { body: JSON.stringify(body) } : {}),
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      if (attempt === 2) throw error;
      await sleep(1000 * (attempt + 1));
    }
  }
}

function clean(value) {
  return String(value ?? '').replace(/[\r\n\u0000-\u001f]/g, ' ').trim();
}

function attribute(value) {
  return clean(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

export function streamUrl(value) {
  const url = new URL(value);
  if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Unsupported stream URL');
  return url.href;
}

export function playlist(rows) {
  return '#EXTM3U\n' + rows.map(row =>
    `#EXTINF:-1 tvg-id="${attribute(row.name)}" tvg-name="${attribute(row.name)}" tvg-logo="${attribute(row.logo)}",${clean(row.name)}\n${streamUrl(row.url)}\n`
  ).join('');
}

async function resolveChannel(channel, key) {
  const response = await request('/play', { channelName: channel.name, serverIndex: 0 });
  const data = decrypt(response.data, key);
  let url = streamUrl(data.url || data.embedUrl);
  // Match the site's normal short-lived token flow; don't export DRM keys.
  const parsed = new URL(url);
  if ((parsed.hostname === 'rise2the.top' || parsed.hostname.endsWith('.rise2the.top')) && !parsed.pathname.includes('/aldous/')) {
    const token = await request('/estes', { url, expiry: 3600 });
    if (!token.tokenizedUrl) throw new Error('Missing playback token');
    url = streamUrl(token.tokenizedUrl);
  }
  return { name: channel.name, logo: channel.logo || '', url };
}

async function main() {
  const { key } = await request('/key');
  if (typeof key !== 'string' || !key.length) throw new Error('Missing catalog key');
  const encrypted = await request('/data');
  const catalog = decrypt(encrypted.data, key);
  if (!Array.isArray(catalog)) throw new Error('Invalid catalog');
  const channels = catalog.filter(channel => channel.enabled !== false && typeof channel.name === 'string');
  if (channels.length < 10) throw new Error('Unexpectedly small catalog; keeping previous deployment');
  const rows = [];
  const failed = [];
  let cursor = 0;
  await Promise.all(Array.from({ length: 4 }, async () => {
    while (cursor < channels.length) {
      const channel = channels[cursor++];
      try {
        rows.push(await resolveChannel(channel, key));
      } catch (error) {
        failed.push(channel.name);
        // Never log decrypted payloads, tokens, or stream query strings.
        console.warn(`Could not resolve ${clean(channel.name)}: ${error.name}`);
      }
    }
  }));
  if (rows.length / channels.length < 0.9) {
    throw new Error(`Only ${rows.length}/${channels.length} channels resolved; keeping previous deployment`);
  }
  rows.sort((a, b) => a.name.localeCompare(b.name));
  const output = new URL('../site/', import.meta.url);
  await mkdir(output, { recursive: true });
  const temporary = new URL('playlist.m3u.tmp', output);
  await writeFile(temporary, playlist(rows), 'utf8');
  await rename(temporary, new URL('playlist.m3u', output));
  await writeFile(new URL('status.json', output), JSON.stringify({
    updatedAt: new Date().toISOString(),
    channelCount: rows.length,
    catalogCount: channels.length,
    failedChannels: failed,
    note: 'Stream URLs were resolved, not playback-tested. Some channels require the original player or DRM.',
  }, null, 2) + '\n');
  console.log(`Playlist refreshed: ${rows.length}/${channels.length} channels`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch(error => {
    console.error(`Refresh failed: ${error.message}`);
    process.exitCode = 1;
  });
}
