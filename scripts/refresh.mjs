import { createDecipheriv } from 'node:crypto';
import { mkdir, readFile, writeFile, rename } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const API = 'https://auth.iyad.click';
const EPG_URL = 'https://tr3nching.github.io/ph-tv-playlist/epg.xml.gz';
const BACKUP_SOURCE = 'https://3rstvportal.blogspot.com/';
const channelGroups = JSON.parse(await readFile(new URL('../channel-groups.json', import.meta.url), 'utf8'));
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
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const response = await fetch(`${API}${path}${path === '/data' ? `?refresh=${Date.now()}` : ''}`, {
        headers: { ...headers, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        method: body ? 'POST' : 'GET',
        ...(body ? { body: JSON.stringify(body) } : {}),
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) {
        let detail = '';
        try {
          const failure = await response.json();
          if (typeof failure.error === 'string') detail = ` (${clean(failure.error).slice(0, 160)})`;
        } catch {}
        throw new Error(`${path}: HTTP ${response.status}${detail}`);
      }
      return await response.json();
    } catch (error) {
      if (attempt === 4) throw error;
      await sleep(2000 * (2 ** attempt));
    }
  }
}

function clean(value) {
  return String(value ?? '').replace(/[\r\n\u0000-\u001f]/g, ' ').trim();
}

function attribute(value) {
  return clean(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

export function channelCategory(name) {
  return channelGroups[clean(name).replace(/\s*\[Backup\]$/, '')] || 'General';
}

export function categorizePlaylist(text) {
  return text.replace(/^#EXTINF:[^\r\n]*/gm, line => {
    const encoded = line.match(/\btvg-id="([^"]*)"/)?.[1] || '';
    const id = encoded.replace(/&(amp|quot|lt|gt);/g, (_, key) => ({ amp: '&', quot: '"', lt: '<', gt: '>' }[key]));
    const group = attribute(channelCategory(id));
    return line.replace(/\s+group-title="[^"]*"/g, '').replace(/^#EXTINF:[^ ,]+/, prefix => `${prefix} group-title="${group}"`);
  });
}

function playlistEntries(text) {
  return text.split(/(?=^#EXTINF:)/m).slice(1).map(block => {
    const id = block.match(/\btvg-id="([^"]*)"/)?.[1] || '';
    const url = block.split(/\r?\n/).find(line => /^https?:\/\//.test(line));
    return { id, url, block };
  });
}

function stableEndpoint(value) {
  const url = new URL(value);
  for (const key of [...url.searchParams.keys()]) {
    if (/^(token|auth|expires?|expiry|exp|signature|sig|sign|hdnea|hdnts|policy|key-pair-id|x-amz-.*)$/i.test(key)) url.searchParams.delete(key);
  }
  url.searchParams.sort();
  return { host: url.host, path: url.pathname, query: url.searchParams.toString() };
}

export function deduplicateBackups(primary, backup) {
  const regular = playlistEntries(primary);
  const kept = []; const excluded = [];
  for (const entry of playlistEntries(backup)) {
    const duplicate = regular.some(original => {
      if (original.id !== entry.id || !original.url || !entry.url) return false;
      const a = stableEndpoint(original.url), b = stableEndpoint(entry.url);
      if (a.host !== b.host || a.query !== b.query) return false;
      if (a.path === b.path) return true;
      const folder = path => path.slice(0, path.lastIndexOf('/') + 1);
      const hlsVariant = path => /\/(?:playlist|chunks|master|index|mono(?:\.ts)?)\.m3u8$/i.test(path);
      return folder(a.path) !== '/' && folder(a.path) === folder(b.path) && hlsVariant(a.path) && hlsVariant(b.path);
    });
    if (duplicate) excluded.push(entry.id); else kept.push(entry);
  }
  return { text: backup ? `#EXTM3U x-tvg-url="${EPG_URL}"\n` + kept.map(entry => entry.block.trimEnd() + '\n').join('') : '', excluded, entries: kept };
}

export function streamUrl(value) {
  const url = new URL(value);
  if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Unsupported stream URL');
  return url.href;
}

export function playlist(rows, { includeDrm = false, epgUrl = EPG_URL } = {}) {
  return `#EXTM3U x-tvg-url="${attribute(streamUrl(epgUrl))}"\n` + rows.map(row => {
    const lines = [`#EXTINF:-1 tvg-id="${attribute(row.epgId || row.name)}" tvg-name="${attribute(row.name)}" tvg-logo="${attribute(row.logo)}" group-title="${attribute(row.group || channelCategory(row.epgId || row.name))}",${clean(row.name)}`];
    if (includeDrm && row.clearKey) {
      if (![row.clearKey.id, row.clearKey.value].every(v => typeof v === 'string' && /^[a-fA-F0-9]{32}$/.test(v))) throw new Error('Invalid source ClearKey configuration');
      const origin = encodeURIComponent(row.origin || headers.Origin);
      lines.push('#KODIPROP:inputstream=inputstream.adaptive', '#KODIPROP:inputstream.adaptive.manifest_type=mpd', '#KODIPROP:inputstream.adaptive.license_type=org.w3.clearkey', `#KODIPROP:inputstream.adaptive.license_key=${row.clearKey.id}:${row.clearKey.value}`, `#KODIPROP:inputstream.adaptive.manifest_headers=Origin=${origin}`, `#KODIPROP:inputstream.adaptive.stream_headers=Origin=${origin}`);
    }
    lines.push(streamUrl(row.url));
    return lines.join('\n') + '\n';
  }).join('');
}

export function parseBackupChannels(html) {
  const literal = html.match(/const\s+channels\s*=\s*\[([\s\S]*?)\];/)?.[1];
  if (!literal) throw new Error('Backup channel array missing');
  const rows = [];
  for (const object of literal.matchAll(/\{([^{}]*)\}/g)) {
    const fields = {};
    for (const pair of object[1].matchAll(/\b(name|url|type|logo|keyId|key)\s*:\s*(['"])((?:\\.|(?!\2)[^\\])*)\2/g)) {
      fields[pair[1]] = pair[3].replace(/\\(['"\\/])/g, '$1');
    }
    if (!fields.name || !['hls', 'mpd', 'dash'].includes(fields.type)) continue;
    let url;
    try { url = streamUrl(fields.url); } catch { continue; }
    const dash = ['mpd', 'dash'].includes(fields.type);
    const validKeys = [fields.keyId, fields.key].every(v => /^[a-fA-F0-9]{32}$/.test(v || ''));
    if (dash && (fields.keyId || fields.key) && !validKeys) continue;
    rows.push({ name: clean(fields.name), url, logo: fields.logo || '', origin: new URL(BACKUP_SOURCE).origin,
      ...(dash && validKeys ? { clearKey: { id: fields.keyId, value: fields.key } } : {}) });
  }
  return rows;
}

export async function checkBackupManifests(rows) {
  const checks = []; let cursor = 0;
  await Promise.all(Array.from({ length: 6 }, async () => {
    while (cursor < rows.length) {
      const row = rows[cursor++];
      try {
        const response = await fetch(row.url, { headers: { Origin: row.origin, 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(8000) });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const reader = response.body.getReader();
        let sample = ''; const decoder = new TextDecoder();
        try {
          while (sample.length < 65536) {
            const chunk = await reader.read(); if (chunk.done) break;
            sample += decoder.decode(chunk.value, { stream: true });
            if (/#EXTM3U|<MPD\b/.test(sample)) break;
          }
        } finally { await reader.cancel(); }
        checks.push({ channel: row.name, manifest_readable: /#EXTM3U|<MPD\b/.test(sample), http: response.status });
      } catch (error) { checks.push({ channel: row.name, manifest_readable: false, error: error.message.startsWith('HTTP ') ? error.message : error.name }); }
    }
  }));
  return checks;
}

export async function refreshBackups(savedHtml, savedChecks) {
  let html = savedHtml;
  if (html === undefined) {
    const response = await fetch(BACKUP_SOURCE, { signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error(`Backup source HTTP ${response.status}`);
    html = await response.text();
    if (html.length > 2000000) throw new Error('Backup page exceeds size limit');
  }
  const candidates = parseBackupChannels(html);
  if (candidates.length < 10) throw new Error('Backup catalog too small; keeping previous assets');
  const checks = savedChecks || await checkBackupManifests(candidates);
  const readable = new Set(checks.filter(c => c.manifest_readable).map(c => c.channel));
  const rows = candidates.filter(r => readable.has(r.name));
  const output = new URL('../site/', import.meta.url);
  await mkdir(output, { recursive: true });
  await writeFile(new URL('backup-checks.json', output), JSON.stringify({ checkedAt: new Date().toISOString(), candidates: candidates.length, readableManifests: rows.length, scope: 'Manifest requests only; not video decoding or TV playback. Network-specific results.', channels: checks }, null, 2));
  if (!rows.length) throw new Error('No readable backup manifests; keeping previous playlist');
  const catalog = JSON.parse(await readFile(new URL('../catalog.json', import.meta.url), 'utf8'));
  const norm = name => name.toLowerCase().replace(/[^a-z0-9]/g, '');
  const aliases = { '3rstv': '3RSTV', 'startvphilippines': 'Star TV Philippines', 'kapamilya': 'Kapamilya Channel', 'cinemaone': 'CinemaOne', 'teleradyo': 'DZMM Teleradyo', 'nbatvph': 'NBA TV Philippines', 'pbo': 'Pinoy Box Office', 'tmc': 'Tagalized Movie Channel', 'depedchannel': 'DepEd TV', 'axnchannel': 'AXN', 'hbohd': 'HBO', 'ptv4': 'Peoples Television' };
  const additionalChannels = [];
  for (const row of rows) {
    const hit = catalog.find(c => norm(c.name) === norm(row.name) || c.name === aliases[norm(row.name)]);
    row.epgId = hit?.name || row.name;
    if (hit) { row.name = hit.name + ' [Backup]'; }
    else { additionalChannels.push(row.name); }
    row.group = channelCategory(row.epgId);
  }
  await writeFile(new URL('playlist-backup.m3u', output), playlist(rows, { includeDrm: true }));
  await writeFile(new URL('backup-status.json', output), JSON.stringify({ updatedAt: new Date().toISOString(), candidateCount: candidates.length, channelCount: rows.length, additionalChannels, existingChannelBackups: rows.length-additionalChannels.length, clearKeyChannelCount: rows.filter(r => r.clearKey).length,
    note: 'Only entries with a readable manifest at refresh time are included. Video playback and source independence are not guaranteed. Failed entries are retried next refresh.' }, null, 2));
  console.log(`Backup playlist extracted: ${rows.length} channels`);
}

export async function combinePlaylists(output = new URL('../site/', import.meta.url)) {
  const primary = await readFile(new URL('playlist-drm.m3u', output), 'utf8');
  let backup = '';
  try { backup = await readFile(new URL('playlist-backup.m3u', output), 'utf8'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const distinct = deduplicateBackups(primary, backup);
  backup = categorizePlaylist(distinct.text);
  if (backup) await writeFile(new URL('playlist-backup.m3u', output), backup);
  try {
    const statusUrl = new URL('backup-status.json', output);
    const status = JSON.parse(await readFile(statusUrl, 'utf8'));
    const ids = new Set(distinct.entries.map(entry => entry.id));
    status.additionalChannels = (status.additionalChannels || []).filter(name => ids.has(name));
    status.channelCount = distinct.entries.length;
    status.existingChannelBackups = status.channelCount - status.additionalChannels.length;
    status.clearKeyChannelCount = (backup.match(/^#KODIPROP:inputstream\.adaptive\.license_key=/gm) || []).length;
    status.excludedDuplicates = [...new Set([...(status.excludedDuplicates || []), ...distinct.excluded])].filter(id => !ids.has(id));
    delete status.source;
    await writeFile(statusUrl, JSON.stringify(status, null, 2));
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const base = primary.replace(/^#EXTM3U[^\n]*/, `#EXTM3U x-tvg-url="${EPG_URL}"`);
  const combined = categorizePlaylist(base.trimEnd() + '\n' + backup.split('\n').slice(1).join('\n'));
  await writeFile(new URL('playlist.m3u.tmp', output), combined);
  await rename(new URL('playlist.m3u.tmp', output), new URL('playlist.m3u', output));
  await writeFile(new URL('playlist-combined.m3u', output), combined);
  const count = text => (text.match(/^#EXTINF:/gm) || []).length;
  const categories = {};
  for (const match of combined.matchAll(/^#EXTINF:[^\n]*group-title="([^"]*)"/gm)) categories[match[1]] = (categories[match[1]] || 0) + 1;
  await writeFile(new URL('playlist-status.json', output), JSON.stringify({ assembledAt: new Date().toISOString(), entryCount: count(combined), primaryEntryCount: count(primary), alternateEntryCount: count(backup), categories }, null, 2));
}

async function resolveChannel(channel, key) {
  const response = await request('/play', { channelName: channel.name, serverIndex: 0 });
  const data = decrypt(response.data, key);
  let url = streamUrl(data.url || data.embedUrl);
  // Match the site's normal short-lived token flow. The user approved a separate
  // public DRM playlist containing the settings supplied by the normal player.
  const parsed = new URL(url);
  if ((parsed.hostname === 'rise2the.top' || parsed.hostname.endsWith('.rise2the.top')) && !parsed.pathname.includes('/aldous/')) {
    const token = await request('/estes', { url, expiry: 3600 });
    if (!token.tokenizedUrl) throw new Error('Missing playback token');
    url = streamUrl(token.tokenizedUrl);
  }
  const mediaPath = new URL(url).pathname.toLowerCase();
  const isDash = !mediaPath.endsWith('.m3u8') && (mediaPath.endsWith('.mpd') || ['mpd', 'dash'].includes(String(data.type).toLowerCase()));
  const clearKey = isDash && [data.keyId, data.key].every(v => typeof v === 'string' && /^[a-fA-F0-9]{32}$/.test(v)) ? { id: data.keyId, value: data.key } : undefined;
  return { name: channel.name, logo: channel.logo || '', url, clearKey };
}

async function main() {
  const { key } = await request('/key');
  if (typeof key !== 'string' || !key.length) throw new Error('Missing catalog key');
  let catalog;
  let catalogSource = 'live';
  try {
    const encrypted = await request('/data');
    catalog = decrypt(encrypted.data, key);
  } catch (error) {
    console.warn(`Catalog unavailable (${error.message}); trying saved channel names with fresh playback requests`);
    catalog = JSON.parse(await readFile(new URL('../catalog.json', import.meta.url), 'utf8'));
    catalogSource = 'saved';
  }
  if (!Array.isArray(catalog)) throw new Error('Invalid catalog');
  const channels = catalog.filter(channel => channel.enabled !== false && typeof channel.name === 'string');
  if (channels.length < 10) throw new Error('Unexpectedly small catalog; keeping previous deployment');
  // Fail promptly if playback itself is down, rather than retrying the whole catalog.
  const rows = [await resolveChannel(channels[0], key)];
  const failed = [];
  let cursor = 1;
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
  const drmTemporary = new URL('playlist-drm.m3u.tmp', output);
  await writeFile(drmTemporary, playlist(rows, { includeDrm: true }), 'utf8');
  await rename(drmTemporary, new URL('playlist-drm.m3u', output));
  const otcChannels = rows.map(row => ({ name: clean(row.name), epg_id: clean(row.name), icon: row.logo, url: row.url, ...(row.clearKey ? { source_format: 'dash', drm_type: 'clearkey', drm_key: `${row.clearKey.id}:${row.clearKey.value}`, headers: { Origin: 'https://iyad.click' } } : {}) }));
  await writeFile(new URL('playlist-drm.otc.json', output), JSON.stringify({ provider: { epg: EPG_URL }, channels: otcChannels }, null, 2));
  await writeFile(new URL('status.json', output), JSON.stringify({
    updatedAt: new Date().toISOString(),
    channelCount: rows.length,
    catalogCount: channels.length,
    catalogSource,
    clearKeyChannelCount: rows.filter(row => row.clearKey).length,
    failedChannels: failed,
    note: 'Stream URLs were resolved, not playback-tested. The separate DRM playlist preserves source-supplied ClearKey settings and requires a compatible player.',
  }, null, 2) + '\n');
  console.log(`Playlist refreshed: ${rows.length}/${channels.length} channels`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  (async () => {
    try { await refreshBackups(); } catch (error) { console.warn(`Backup refresh failed: ${error.message}`); }
    try { if (!process.argv.includes('--backup-only')) await main(); }
    finally { try { await combinePlaylists(); } catch { console.warn('Combined playlist unavailable; individual playlists retained'); } }
  })().catch(error => {
    console.error(`Refresh failed: ${error.message}`);
    process.exitCode = 1;
  });
}
