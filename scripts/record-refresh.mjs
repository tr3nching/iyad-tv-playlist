import { readFile, writeFile, appendFile } from 'node:fs/promises';
const site = new URL('../site/', import.meta.url);
const streamOutcome = process.env.STREAM_OUTCOME || 'unknown';
const guideOutcome = process.env.GUIDE_OUTCOME || 'unknown';
const snapshot = process.env.PUBLISH_SNAPSHOT === 'true';
const report = {
  attemptedAt: new Date().toISOString(),
  streamRefresh: snapshot ? 'saved snapshot' : streamOutcome,
  guideRefresh: guideOutcome,
  note: 'A successful Pages deployment does not mean the stream source refreshed successfully. Check updatedAt in status.json and generated_utc in epg-status.json.',
};
const statusUrl = new URL('status.json', site);
const status = JSON.parse(await readFile(statusUrl, 'utf8'));
status.lastAutomaticAttemptAt = report.attemptedAt;
status.automaticRefreshStatus = snapshot ? 'Using freshly prepared snapshot; scheduled refreshes will attempt the source.' : streamOutcome === 'success' ? 'Source refreshed successfully' : 'Source refresh failed; previously saved stream links retained and may expire.';
await writeFile(statusUrl, JSON.stringify(status, null, 2));
await writeFile(new URL('refresh-status.json', site), JSON.stringify(report, null, 2));
const m3u = await readFile(new URL('playlist-drm.m3u', site), 'utf8');
if ((m3u.match(/^#EXTINF:/gm) || []).length < 10) throw new Error('No usable playlist to publish');
await readFile(new URL('epg.xml', site));
if (process.env.GITHUB_STEP_SUMMARY) await appendFile(process.env.GITHUB_STEP_SUMMARY, `Stream source refresh: **${report.streamRefresh}**\n\nGuide refresh: **${guideOutcome}**\n\n${report.note}\n`);
console.log(JSON.stringify(report));
