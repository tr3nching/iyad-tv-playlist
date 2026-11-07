import { createDecipheriv, createHash } from 'node:crypto';
import { mkdir, readFile, writeFile, rename } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const API = 'https://auth.iyad.click';
const EPG_URL = 'https://tr3nching.github.io/ph-tv-playlist/epg.xml.gz';
const BACKUP_SOURCE = 'https://3rstvportal.blogspot.com/';
const channelGroups = JSON.parse(await readFile(new URL('../channel-groups.json', import.meta.url), 'utf8'));
const sourceOverrides = JSON.parse(await readFile(new URL('../source-channel-overrides.json', import.meta.url), 'utf8'));
const primaryOverrides = JSON.parse(await readFile(new URL('../primary-source-overrides.json', import.meta.url), 'utf8'));
const primaryAliases = new Map(Object.entries(JSON.parse(await readFile(new URL('../primary-source-category-aliases.json', import.meta.url), 'utf8')).aliases).map(([name, group]) => [name.toLowerCase().replace(/[^a-z0-9]/g, ''), group]));
const primarySourceGroups = new Map();
const primarySourceParents = new Map();
const normalizedGroups = new Map(Object.entries(channelGroups).map(([name, group]) => [name.toLowerCase().replace(/[^a-z0-9]/g, ''), group]));
const headers = {
  Origin: 'https://iyad.click',
  Referer: 'https://iyad.click/',
  'User-Agent': 'Mozilla/5.0',
};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export function primarySourceJobs(catalog) {
  const jobs = [];
  const norm = value => clean(value).toLowerCase().replace(/[^a-z0-9]/g, '');
  for (const channel of catalog) {
    if (channel.enabled === false || typeof channel.name !== 'string') continue;
    for (let index = 0; index <= 20; index++) {
      const suffix = index === 1 ? '' : String(index);
      const label = index === 0 ? channel.name : channel[`alt_name${suffix}`];
      if (typeof label !== 'string' || !clean(label) || (index > 0 && channel[`alt_enabled${suffix}`] === false)) continue;
      const override = primaryOverrides[channel.name]?.[index] || {};
      const generic = /^Stream \d+$/.test(clean(label));
      const name = override.name || (generic ? `${channel.name} ${clean(label)}` : clean(label));
      const explicit = primaryAliases.get(norm(name)) || normalizedGroups.get(norm(name));
      const family = /^(?:VEVO|XITE|Kpop)\b/i.test(name) ? 'Music' : /^(?:BeIn Sports|Pilipinas Live|TNT Sports|TSN)\b/i.test(name) || /^\d{1,2}:\d{2}[ap]m .+ vs .+/i.test(name) ? 'Sports' : null;
      const category = override.category || explicit || family || (index === 0 || generic ? channelCategory(channel.name) : 'General');
      const epgId = index === 0 ? override.epgId || name : `primary-source:${norm(channel.name)}:${index}`;
      const categoryBasis = override.category ? 'source-specific override' : explicit ? 'configured broad channel type; see category review' : family ? 'broad branded channel family' : generic ? 'parent broad type for generic source label; not schedule identity' : index === 0 ? 'existing primary category' : 'unresolved named source';
      const job = { id: epgId, epgId, parentName: channel.name, serverIndex: index, name, logo: override.logo || (index > 0 ? channel[`alt_logo${suffix}`] : channel.logo) || channel.logo || '', category, group: category, categoryBasis, regionalEvidence: override.regionalEvidence, enabled: true };
      if (index > 0) { primarySourceGroups.set(epgId, category); primarySourceParents.set(epgId, { parentId: primaryOverrides[channel.name]?.[0]?.epgId || channel.name, index }); }
      jobs.push(job);
    }
  }
  if (new Set(jobs.map(job => job.id)).size !== jobs.length) throw new Error('Duplicate primary source identities');
  return jobs;
}

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
  if (name.startsWith('category:') && categoryOrder.includes(name.slice(9))) return name.slice(9);
  if (primarySourceGroups.has(name)) return primarySourceGroups.get(name);
  const additionalKey = clean(name).match(/^additional:([^:]+)(?::.*)?$/)?.[1];
  if (additionalKey && sourceOverrides[additionalKey]?.category) return sourceOverrides[additionalKey].category;
  const key = clean(name).replace(/^additional:([^:]+)(?::.*)?$/, '$1').replace(/\s*\[(?:Backup|Alternate|Additional)\]$/, '').toLowerCase().replace(/[^a-z0-9]/g, '');
  return normalizedGroups.get(key) || 'General';
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
    const encoded = block.match(/\btvg-id="([^"]*)"/)?.[1] || '';
    const id = encoded.replace(/&(amp|quot|lt|gt);/g, (_, key) => ({ amp: '&', quot: '"', lt: '<', gt: '>' }[key]));
    const url = block.split(/\r?\n/).find(line => /^https?:\/\//.test(line));
    return { id, url, block };
  });
}

const categoryOrder = ['Entertainment', 'Movies', 'Sports', 'News', 'Kids', 'Anime', 'Documentaries', 'Music', 'Lifestyle', 'Faith', 'Education', 'General'];

export function orderPlaylist(text) {
  const header = text.split(/(?=^#EXTINF:)/m)[0];
  // Stable category ordering keeps each complete entry and its playback settings together.
  const entries = playlistEntries(text).sort((a, b) => {
    const group = entry => entry.block.split('\n')[0].match(/\bgroup-title="([^"]*)"/)?.[1] || 'General';
    const rank = entry => { const index = categoryOrder.indexOf(group(entry)); return index < 0 ? categoryOrder.length : index; };
    return rank(a) - rank(b);
  });
  return header + entries.map(entry => entry.block.trimEnd() + '\n').join('');
}

export const categoryNumbers = Object.freeze({ Entertainment: 100, Movies: 200, Sports: 300, News: 400, Kids: 500, Anime: 600, Documentaries: 700, Music: 800, Lifestyle: 900, Faith: 1000, Education: 1100, General: 1200 });

function entryName(entry) {
  const line = entry.block.split('\n')[0];
  const encoded = line.match(/\btvg-name="([^"]*)"/)?.[1];
  return encoded === undefined ? line.slice(line.indexOf(',') + 1).trim() : encoded.replace(/&(amp|quot|lt|gt);/g, (_, key) => ({ amp: '&', quot: '"', lt: '<', gt: '>' }[key]));
}

const sourceName = name => name.replace(/\s*(?:\[(?:Backup|Alternate|Additional)\]|\*)$/, '').trim();
const nameKey = name => sourceName(name).toLowerCase().replace(/[^a-z0-9]/g, '');
const compareNames = (a, b) => Number(b.id.startsWith('category:')) - Number(a.id.startsWith('category:')) || sourceName(entryName(a)).localeCompare(sourceName(entryName(b)), 'en', { sensitivity: 'base', numeric: true }) || entryName(a).localeCompare(entryName(b), 'en') || a.id.localeCompare(b.id, 'en');

export function addCategoryHeaders(text) {
  const entries = playlistEntries(text).filter(entry => !entry.id.startsWith('category:'));
  const groups = new Set(entries.map(entry => channelCategory(entry.id)));
  const rows = categoryOrder.filter(group => groups.has(group)).map(group => ({ name: `━━ ${group.toUpperCase()} ━━`, epgId: `category:${group}`, group,
    url: `https://tr3nching.github.io/ph-tv-playlist/categories/${group.toLowerCase()}.m3u8` }));
  return text.split(/(?=^#EXTINF:)/m)[0] + entries.map(entry => entry.block.trimEnd() + '\n').join('') + playlist(rows).split('\n').slice(1).join('\n');
}

export function numberPlaylist(text) {
  const assignments = Object.create(null);
  const entries = playlistEntries(text).sort((a, b) => categoryNumbers[channelCategory(a.id)] - categoryNumbers[channelCategory(b.id)] || compareNames(a, b));
  const present = new Set(entries.map(entry => entry.id));
  const parents = new Map();
  for (const entry of entries) {
    const source = primarySourceParents.get(entry.id);
    if (source && present.has(source.parentId)) parents.set(entry.id, source);
  }
  // A verified additional duplicate shares its matching source family's major number.
  const primary = entries.filter(entry => !entry.id.startsWith('additional:'));
  for (const entry of entries.filter(entry => entry.id.startsWith('additional:'))) {
    const matches = primary.filter(other => other.url === entry.url);
    const names = primary.filter(other => nameKey(entryName(other)) === nameKey(entryName(entry)));
    const match = (matches.length ? matches : names).sort((a,b) => Number(parents.has(a.id))-Number(parents.has(b.id)) || a.id.localeCompare(b.id))[0];
    if (match) parents.set(entry.id, { parentId: parents.get(match.id)?.parentId || match.id });
  }
  let lastMajor = 0;
  for (const entry of entries.filter(entry => !parents.has(entry.id))) {
    if (Object.hasOwn(assignments,entry.id)) continue;
    const major = Math.max(categoryNumbers[channelCategory(entry.id)], lastMajor + 1);
    assignments[entry.id] = major; lastMajor = major;
  }
  const used = new Map();
  for (const [id, source] of parents) {
    if (!source.index) continue;
    if (!used.has(source.parentId)) used.set(source.parentId, new Set());
    used.get(source.parentId).add(source.index);
    assignments[id] = `${assignments[source.parentId]}.${String(source.index).padStart(3,'0')}`;
  }
  for (const [id, source] of parents) {
    if (source.index) continue;
    if (!used.has(source.parentId)) used.set(source.parentId, new Set());
    const slots=used.get(source.parentId);let index=Math.max(0,...slots)+1;slots.add(index);
    assignments[id] = `${assignments[source.parentId]}.${String(index).padStart(3,'0')}`;
  }
  const header = text.split(/(?=^#EXTINF:)/m)[0];
  const numbered = entries.map(entry => entry.block.replace(/^#EXTINF:[^\r\n]*/, line => line.replace(/\s+tvg-chno="[^"]*"/g, '').replace(/^#EXTINF:[^ ,]+/, prefix => `${prefix} tvg-chno="${assignments[entry.id]}"`)).trimEnd() + '\n').join('');
  return { text: header + numbered, assignments };
}

export function markAdditionalChannels(primary, backup) {
  const regular = playlistEntries(primary);
  const entries = playlistEntries(backup).map(entry => {
    const sourceKey = entry.id.match(/^additional:([^:]+)(?::.*)?$/)?.[1];
    const name = sourceOverrides[sourceKey]?.name || sourceName(entryName(entry));
    const duplicate = regular.some(original => nameKey(entryName(original)) === nameKey(name) || (original.url && original.url === entry.url));
    const displayName = name + (duplicate ? ' *' : '');
    const block = entry.block.replace(/^#EXTINF:[^\r\n]*/, line => {
      const metadata = line.match(/^(#EXTINF:(?:[^,"\r\n]|"[^"]*")*),/)?.[1];
      if (!metadata) throw new Error('Invalid channel metadata');
      return metadata.replace(/\s+tvg-name="[^"]*"/g, '') + ` tvg-name="${attribute(displayName)}",${clean(displayName)}`;
    });
    return { ...entry, block };
  });
  return { text: backup ? `#EXTM3U x-tvg-url="${EPG_URL}"\n` + entries.map(entry => entry.block.trimEnd() + '\n').join('') : '', excluded: [], entries };
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
  return rows.filter((row, index) => rows.findIndex(other => other.url === row.url) === index);
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
  const catalog = JSON.parse(await readFile(new URL('../catalog.json', import.meta.url), 'utf8'));
  const norm = name => name.toLowerCase().replace(/[^a-z0-9]/g, '');
  const additionalChannels = [];
  for (const row of candidates) {
    const originalName = row.name;
    row.epgId = additionalChannelId(row);
    const override = sourceOverrides[norm(originalName)];
    row.name = override?.name || originalName;
    row.group = override?.category || channelCategory(originalName);
    if (catalog.some(channel => norm(channel.name) === norm(row.name))) row.name += ' *';
    additionalChannels.push(row.name);
  }
  const checks = savedChecks || await checkBackupManifests(candidates);
  const readable = new Set(checks.filter(c => c.manifest_readable).map(c => c.channel));
  const rows = candidates.filter(r => readable.has(r.name) || readable.has(sourceName(r.name)));
  const output = new URL('../site/', import.meta.url);
  await mkdir(output, { recursive: true });
  await writeFile(new URL('backup-candidates.m3u', output), playlist(candidates, { includeDrm: true }));
  await writeFile(new URL('backup-checks.json', output), JSON.stringify({ checkedAt: new Date().toISOString(), candidates: candidates.length, readableManifests: rows.length, scope: 'Manifest requests only; not video decoding or TV playback. Network-specific results.', channels: checks }, null, 2));
  await writeFile(new URL('playlist-backup.m3u', output), playlist(rows, { includeDrm: true }));
  await writeFile(new URL('backup-status.json', output), JSON.stringify({ updatedAt: new Date().toISOString(), candidateCount: candidates.length, channelCount: rows.length, additionalChannels: rows.map(row => row.name), candidateAdditionalChannels: additionalChannels, verifiedAdditionalChannels: [], existingChannelBackups: 0, clearKeyChannelCount: rows.filter(r => r.clearKey).length,
    note: 'All saved candidates remain listed. An asterisk marks additional entries sharing an original name or stream URL. Reachability checks are informational; playback is not guaranteed.' }, null, 2));
  console.log(`Backup playlist extracted: ${rows.length} channels`);
}

export function additionalChannelId(row) {
  const name = row.name.toLowerCase().replace(/[^a-z0-9]/g, '');
  return 'additional:' + name + ':' + createHash('sha256').update(row.url).digest('hex').slice(0, 12);
}

export function streamCheckId(kind, entry) {
  return createHash('sha256').update(`${kind}\0${entry.id}\0${entry.url}`).digest('hex');
}

export function validatedAdditional(text, report, now = Date.now()) {
  const checked = Date.parse(report?.checkedAt);
  const current = Number.isFinite(checked) && checked <= now + 60000 && now - checked <= 24 * 60 * 60 * 1000;
  const approved = new Set(current ? (report.channels || []).filter(row => row.validated === true && row.decodedFrames >= 25).map(row => row.id) : []);
  const selected = playlistEntries(text).filter(entry => approved.has(streamCheckId('additional', entry)));
  return `#EXTM3U x-tvg-url="${EPG_URL}"\n` + selected.map(entry => entry.block.trimEnd() + '\n').join('');
}

export async function combinePlaylists(output = new URL('../site/', import.meta.url)) {
  let primary = await readFile(new URL('playlist-drm.m3u', output), 'utf8');
  let backup = '';
  try { backup = await readFile(new URL('backup-candidates.m3u', output), 'utf8'); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    try { backup = await readFile(new URL('playlist-backup.m3u', output), 'utf8'); }
    catch (fallbackError) { if (fallbackError.code !== 'ENOENT') throw fallbackError; }
  }
  try {
    const inventory = JSON.parse(await readFile(new URL('primary-source-catalog.json', output), 'utf8'));
    for (const entry of inventory.entries || []) if (entry.id?.startsWith('primary-source:')) { primarySourceGroups.set(entry.id, entry.category || 'General'); primarySourceParents.set(entry.id, { parentId: primaryOverrides[entry.parentName]?.[0]?.epgId || entry.parentName, index: entry.serverIndex }); }
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  let validation = {};
  try { validation = JSON.parse(await readFile(new URL('backup-validation.json', output), 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const distinct = markAdditionalChannels(primary, validatedAdditional(backup, validation));
  backup = categorizePlaylist(distinct.text);
  if (backup) await writeFile(new URL('playlist-backup.m3u', output), backup);
  try {
    const statusUrl = new URL('backup-status.json', output);
    const status = JSON.parse(await readFile(statusUrl, 'utf8'));
    const ids = new Set(distinct.entries.map(entry => entry.id));
    status.additionalChannels = distinct.entries.map(entry => entry.block.split('\n')[0].split(',').pop());
    status.channelCount = distinct.entries.length;
    status.existingChannelBackups = 0;
    status.note = 'Only additional streams with at least 25 decoded video frames for the exact stream identity within 24 hours are listed. Candidates are retained separately for retry. An asterisk marks an original name or stream URL duplicate.';
    status.clearKeyChannelCount = (backup.match(/^#KODIPROP:inputstream\.adaptive\.license_key=/gm) || []).length;
    status.excludedDuplicates = [...new Set([...(status.excludedDuplicates || []), ...distinct.excluded])].filter(id => !ids.has(id));
    delete status.source;
    await writeFile(statusUrl, JSON.stringify(status, null, 2));
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const base = primary.replace(/^#EXTM3U[^\n]*/, `#EXTM3U x-tvg-url="${EPG_URL}"`);
  const numbered = numberPlaylist(categorizePlaylist(addCategoryHeaders(base.trimEnd() + '\n' + backup.split('\n').slice(1).join('\n'))));
  const combined = numbered.text;
  await writeFile(new URL('channel-numbers.json', output), JSON.stringify(numbered.assignments, null, 2) + '\n');
  await writeFile(new URL('playlist.m3u.tmp', output), combined);
  await rename(new URL('playlist.m3u.tmp', output), new URL('playlist.m3u', output));
  await writeFile(new URL('playlist-combined.m3u', output), combined);
  const count = text => (text.match(/^#EXTINF:/gm) || []).length;
  const categories = {};
  for (const match of combined.matchAll(/^#EXTINF:[^\n]*group-title="([^"]*)"/gm)) categories[match[1]] = (categories[match[1]] || 0) + 1;
  await writeFile(new URL('playlist-status.json', output), JSON.stringify({ assembledAt: new Date().toISOString(), entryCount: count(combined), categoryHeaderCount: (combined.match(/tvg-id="category:/g) || []).length, primaryEntryCount: count(primary), alternateEntryCount: count(backup), categories }, null, 2));
}

export async function resolveChannel(channel, key, transport = request) {
  const response = await transport('/play', { channelName: channel.parentName || channel.name, serverIndex: channel.serverIndex || 0 });
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
  return { ...channel, name: channel.name, logo: channel.logo || '', url, clearKey };
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
  const output = new URL('../site/', import.meta.url);
  await mkdir(output, { recursive: true });
  const jobs = primarySourceJobs(channels);
  let oldInventory = { entries: [] }; let oldPlaylist = '';
  try { oldInventory = JSON.parse(await readFile(new URL('primary-source-catalog.json', output), 'utf8')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  try { oldPlaylist = await readFile(new URL('playlist-drm.m3u', output), 'utf8'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const oldEntries = new Map(playlistEntries(oldPlaylist).map(entry => [entry.id, entry]));
  const oldNames = new Map((oldInventory.entries || []).map(entry => [entry.id, entry.name]));
  const inventory = { updatedAt: new Date().toISOString(), catalogSource, entries: jobs.filter(job => job.serverIndex > 0).map(({ id, parentName, serverIndex, name, category, categoryBasis, regionalEvidence, enabled }) => ({ id, parentName, serverIndex, name, category, categoryBasis, regionalEvidence, enabled })) };
  // Publish metadata only after accepting its matching playback cache.
  // Fail promptly if playback itself is down, preserving the last complete stream cache.
  const rows = [await resolveChannel(jobs[0], key)];
  const failed = []; let cursor = 1;
  await Promise.all(Array.from({ length: 4 }, async () => {
    while (cursor < jobs.length) {
      const job = jobs[cursor++];
      try { rows.push(await resolveChannel(job, key)); }
      catch (error) {
        failed.push({ id: job.id, name: job.name, parentName: job.parentName, serverIndex: job.serverIndex });
        console.warn(`Could not resolve ${clean(job.name)}: ${error.name}`);
        const prior = oldEntries.get(job.id) || (job.serverIndex === 0 ? oldEntries.get(job.parentName) : null);
        if (prior && (job.serverIndex === 0 || oldNames.get(job.id) === job.name)) {
          const license = prior.block.match(/license_key=([a-fA-F0-9]{32}):([a-fA-F0-9]{32})/);
          rows.push({ ...job, url: prior.url, retained: true, ...(license ? { clearKey: { id: license[1], value: license[2] } } : {}) });
        }
      }
    }
  }));
  const refreshedBases = rows.filter(row => row.serverIndex === 0 && !row.retained).length;
  if (refreshedBases / channels.length < 0.9) throw new Error(`Only ${refreshedBases}/${channels.length} primary channels refreshed; keeping previous deployment`);
  rows.sort((a, b) => a.name.localeCompare(b.name));
  const drmTemporary = new URL('playlist-drm.m3u.tmp', output);
  await writeFile(drmTemporary, playlist(rows, { includeDrm: true }), 'utf8');
  await rename(drmTemporary, new URL('playlist-drm.m3u', output));
  await writeFile(new URL('primary-source-catalog.json.tmp', output), JSON.stringify(inventory, null, 2) + '\n');
  await rename(new URL('primary-source-catalog.json.tmp', output), new URL('primary-source-catalog.json', output));
  const otcChannels = rows.map(row => ({ name: clean(row.name), epg_id: clean(row.epgId || row.name), icon: row.logo, url: row.url, ...(row.clearKey ? { source_format: 'dash', drm_type: 'clearkey', drm_key: `${row.clearKey.id}:${row.clearKey.value}`, headers: { Origin: 'https://iyad.click' } } : {}) }));
  await writeFile(new URL('playlist-drm.otc.json', output), JSON.stringify({ provider: { epg: EPG_URL }, channels: otcChannels }, null, 2));
  await writeFile(new URL('status.json', output), JSON.stringify({
    updatedAt: new Date().toISOString(),
    channelCount: rows.length,
    catalogCount: channels.length,
    catalogSource,
    primarySourceCount: jobs.length,
    alternateSourceCount: rows.filter(row => row.serverIndex > 0).length,
    retainedSourceCount: rows.filter(row => row.retained).length,
    clearKeyChannelCount: rows.filter(row => row.clearKey).length,
    failedChannels: failed,
    note: 'Stream URLs were resolved, not playback-tested. The separate DRM playlist preserves source-supplied ClearKey settings and requires a compatible player.',
  }, null, 2) + '\n');
  console.log(`Playlist refreshed: ${rows.length}/${jobs.length} sources across ${channels.length} channels`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  (async () => {
    if (process.argv.includes('--finalize')) {
      const output = new URL('../site/', import.meta.url);
      await combinePlaylists(output); return;
    }
    try { await refreshBackups(); } catch (error) { console.warn(`Backup refresh failed: ${error.message}`); }
    try { if (!process.argv.includes('--backup-only')) await main(); }
    finally { try { await combinePlaylists(); } catch { console.warn('Combined playlist unavailable; individual playlists retained'); } }
  })().catch(error => {
    console.error(`Refresh failed: ${error.message}`);
    process.exitCode = 1;
  });
}
