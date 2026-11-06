import { mkdir, readFile, writeFile, copyFile, access } from 'node:fs/promises';
const site = new URL('../site/', import.meta.url);
const bootstrap = new URL('../bootstrap/', import.meta.url);
const base = 'https://tr3nching.github.io/ph-tv-playlist/';
const streamFiles = ['playlist.m3u', 'playlist-drm.m3u', 'playlist-drm.otc.json', 'status.json'];
const guideFiles = ['epg.xml', 'epg.xml.gz', 'epg-status.json', 'mapping.json', 'mapping.csv', 'verification.json', 'report.txt'];
const backupFiles = ['playlist-backup.m3u', 'backup-status.json', 'backup-checks.json'];
const optionalFiles = ['playlist-combined.m3u', 'playlist-status.json'];
await mkdir(site, { recursive: true });
for (const file of [...streamFiles, ...guideFiles, ...backupFiles, ...optionalFiles]) {
  try { await access(new URL(file, bootstrap)); await copyFile(new URL(file, bootstrap), new URL(file, site)); } catch {}
}
async function restoreNewer(files, statusFile, timestampField) {
  try {
    const statusResponse = await fetch(base + statusFile, { signal: AbortSignal.timeout(15000), cache: 'no-store' });
    if (!statusResponse.ok) return;
    const status = await statusResponse.json();
    let local = {};
    try { local = JSON.parse(await readFile(new URL(statusFile, site), 'utf8')); } catch {}
    if (!(Date.parse(status[timestampField]) >= Date.parse(local[timestampField] || '1970-01-01'))) return;
    const staged = [];
    for (const file of files.filter(f => f !== statusFile)) {
      const response = await fetch(base + file, { signal: AbortSignal.timeout(15000), cache: 'no-store' });
      if (!response.ok) throw new Error('Previous deployment incomplete');
      const bytes = Buffer.from(await response.arrayBuffer());
      if (bytes.length > 12000000) throw new Error('Previous asset too large');
      staged.push([file, bytes]);
    }
    staged.push([statusFile, JSON.stringify(status, null, 2)]);
    for (const [file, bytes] of staged) await writeFile(new URL(file, site), bytes);
    console.log(`Restored current ${statusFile}`);
  } catch { console.warn(`Could not restore ${statusFile}; using checked-in snapshot`); }
}
if (process.env.PUBLISH_SNAPSHOT !== 'true') {
  await restoreNewer(streamFiles, 'status.json', 'updatedAt');
  await restoreNewer(guideFiles, 'epg-status.json', 'generated_utc');
  await restoreNewer(backupFiles, 'backup-status.json', 'updatedAt');
}
console.log('Prepared playlist and guide fallback files');
