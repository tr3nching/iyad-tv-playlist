import test from 'node:test';
import assert from 'node:assert/strict';
import { createCipheriv, randomBytes } from 'node:crypto';
import { mkdtemp, readFile, writeFile, unlink, rmdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { numberPlaylist, orderPlaylist, channelCategory, decrypt, playlist, streamUrl, parseBackupChannels, checkBackupManifests, combinePlaylists, markAdditionalChannels, streamCheckId, additionalChannelId } from '../scripts/refresh.mjs';

test('decrypts the player response format without exposing key material', () => {
  const key = '0123456789abcdefextra';
  const iv = randomBytes(16);
  const cipher = createCipheriv('aes-128-cbc', Buffer.from(key.slice(0, 16)), iv);
  const payload = { url: 'https://example.com/live.m3u8' };
  const encoded = Buffer.concat([iv, cipher.update(JSON.stringify(payload)), cipher.final()]).toString('base64');
  assert.deepEqual(decrypt(encoded, key), payload);
  assert.throws(() => decrypt('bad', key));
});

test('untrusted channel names cannot insert playlist entries', () => {
  const output = playlist([{ name: 'News\n#EXTINF:-1,Injected', logo: 'https://example.com/a".png', url: 'https://example.com/live.m3u8?a=1&b=2' }]);
  assert.equal(output.split('\n').filter(line => line.startsWith('#EXTINF:')).length, 1);
  assert.ok(output.includes('&quot;'));
  assert.ok(output.endsWith('https://example.com/live.m3u8?a=1&b=2\n'));
});

test('rejects non-web playback URLs', () => {
  assert.throws(() => streamUrl('javascript:alert(1)'));
  assert.throws(() => streamUrl('file:///private'));
});

test('DRM metadata only appears in the explicitly requested format', () => {
  const clearKey = { id: '1'.repeat(32), value: '2'.repeat(32) };
  const rows = [{ name: 'Test', url: 'https://example.com/live.mpd', clearKey }];
  assert.ok(!playlist(rows).includes('license_key'));
  const result = playlist(rows, { includeDrm: true });
  assert.ok(result.includes('license_type=org.w3.clearkey'));
  assert.ok(result.includes(`license_key=${clearKey.id}:${clearKey.value}`));
  assert.throws(() => playlist([{ ...rows[0], clearKey: { id: 'bad\n#EXTINF:-1,Injected', value: clearKey.value } }], { includeDrm: true }));
});

test('backup extraction reads literal fields without executing page scripts', () => {
  const html = `<script>throw Error('must not execute'); const channels = [
    {name: 'News', url: 'https://example.com/a.m3u8', type: 'hls'},
    {name: 'Same URL under another name', url: 'https://example.com/a.m3u8', type: 'hls'},
    {name: 'Bad URL', url: 'javascript:alert(1)', type: 'hls'},
    {name: 'Bad DRM', url: 'https://example.com/a.mpd', type: 'mpd', keyId: 'bad', key: 'bad'},
    {name: 'Embed', url: 'https://example.com/embed', type: 'youtube'}
  ];</script>`;
  const rows = parseBackupChannels(html);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, 'News');
  assert.ok(playlist(rows).startsWith('#EXTM3U x-tvg-url="https://tr3nching.github.io/ph-tv-playlist/epg.xml.gz"'));
});

test('backup checks reject HTML and HTTP errors as stream manifests', async t => {
  t.mock.method(globalThis, 'fetch', async url => new Response(url.endsWith('good') ? '#EXTM3U\n#EXT-X-VERSION:3' : '<html>Unavailable</html>', { status: url.endsWith('denied') ? 403 : 200 }));
  const checks = await checkBackupManifests(['good', 'html', 'denied'].map(name => ({ name, url: `https://example.com/${name}`, origin: 'https://example.com' })));
  assert.deepEqual(checks.filter(c => c.manifest_readable).map(c => c.channel), ['good']);
});

test('one canonical playlist retains DRM, backups and guide, including without backups', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'ph-tv-playlist-'));
  const output = pathToFileURL(directory + '/');
  const files = ['playlist-drm.m3u', 'playlist-backup.m3u', 'playlist.m3u', 'playlist-combined.m3u', 'playlist-status.json', 'channel-numbers.json'];
  try {
    const primary = playlist([{ name: 'NBA TV', url: 'https://example.com/news.mpd', clearKey: { id: '1'.repeat(32), value: '2'.repeat(32) } }], { includeDrm: true });
    const backup = playlist([{ name: 'NBA TV [Backup]', epgId: 'NBA TV', group: 'Backup', url: 'https://example.com/backup.m3u8' }]);
    await writeFile(new URL('playlist-drm.m3u', output), primary);
    await writeFile(new URL('playlist-backup.m3u', output), backup);
    await combinePlaylists(output);
    const canonical = await readFile(new URL('playlist.m3u', output), 'utf8');
    assert.equal((canonical.match(/^#EXTM3U/gm) || []).length, 1);
    assert.equal((canonical.match(/^#EXTINF:/gm) || []).length, 2);
    assert.ok(canonical.includes('license_type=org.w3.clearkey'));
    assert.equal((canonical.match(/group-title="Sports"/g) || []).length, 2);
    assert.ok(canonical.includes('NBA TV *'));
    assert.equal(canonical, await readFile(new URL('playlist-combined.m3u', output), 'utf8'));
    assert.equal(JSON.parse(await readFile(new URL('playlist-status.json', output))).entryCount, 2);
    await unlink(new URL('playlist-backup.m3u', output));
    await combinePlaylists(output);
    const fallback = await readFile(new URL('playlist.m3u', output), 'utf8');
    assert.ok(fallback.includes('license_type=org.w3.clearkey'));
    assert.equal((fallback.match(/^#EXTINF:/gm) || []).length, 1);
  } finally {
    for (const file of files) { try { await unlink(new URL(file, output)); } catch {} }
    await rmdir(directory);
  }
});

test('additional entries stay separate and duplicates receive an asterisk', () => {
  const primary = playlist([
    { name: 'News', url: 'https://example.com/news/master.m3u8?token=old' },
    { name: 'Sports', url: 'https://example.com/sports/playlist.m3u8' },
    { name: 'Movies', url: 'https://example.com/play?server=1' },
  ]);
  const backups = playlist([
    { name: 'News [Backup]', epgId: 'News', url: 'https://example.com/news/master.m3u8?token=new' },
    { name: 'Sports [Backup]', epgId: 'Sports', url: 'https://example.com/sports/chunks.m3u8' },
    { name: 'Movies [Backup]', epgId: 'Movies', url: 'https://example.com/play?server=2' },
    { name: 'News [Backup]', epgId: 'News', url: 'https://other.example.com/news/master.m3u8' },
    { name: 'Another name', epgId: 'additional:another', url: 'https://example.com/news/master.m3u8?token=old' },
  ]);
  const distinct = markAdditionalChannels(primary, backups);
  assert.deepEqual(distinct.excluded, []);
  assert.equal(distinct.entries.length, 5);
  assert.ok(distinct.text.includes('Another name *'));
  assert.ok(distinct.text.includes('News *'));
  assert.ok(distinct.text.includes('server=2'));
  assert.ok(distinct.text.includes('other.example.com'));
});

test('all saved candidates remain listed regardless of failed checks, with custom numbers', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'ph-tv-playlist-')); const output = pathToFileURL(directory + '/');
  const primary = { name: 'NBA TV', url: 'https://example.com/main.m3u8' };
  const extra = { name: 'Different channel', epgId: 'additional:differentchannel', url: 'https://example.com/other.m3u8' };
  const files = ['playlist-drm.m3u','backup-candidates.m3u','playlist-backup.m3u','playlist.m3u','playlist-combined.m3u','playlist-status.json', 'channel-numbers.json'];
  try {
    const original = playlist([primary]);
    await writeFile(new URL('playlist-drm.m3u',output),original);
    await writeFile(new URL('backup-candidates.m3u',output),playlist([extra]));
    const checks = [{id:streamCheckId('primary',{id:primary.name,url:primary.url}),reachable:false},{id:streamCheckId('additional',{id:extra.epgId,url:extra.url}),reachable:true}];
    await combinePlaylists(output,{health:{channels:checks}});
    let result = await readFile(new URL('playlist.m3u',output),'utf8');
    assert.ok(result.includes(primary.url));assert.ok(result.includes(extra.url));
    assert.ok(result.includes('tvg-chno='));
    assert.equal(await readFile(new URL('playlist-drm.m3u',output),'utf8'),original);
    checks[0].reachable=false;checks[1].reachable=false;
    await combinePlaylists(output,{health:{channels:checks}});
    result=await readFile(new URL('playlist.m3u',output),'utf8');assert.ok(result.includes(primary.url));assert.ok(result.includes(extra.url));
    checks[0].reachable=false;checks[0].publish=true;checks[0].status='inconclusive';
    await combinePlaylists(output,{health:{channels:checks}});
    assert.ok((await readFile(new URL('playlist.m3u',output),'utf8')).includes(primary.url));
  } finally { for(const file of files){try{await unlink(new URL(file,output));}catch{}} await rmdir(directory); }
});

test('additional streams with the same name retain separate identities and no original EPG ID', () => {
  const first=additionalChannelId({name:'One PH',url:'https://example.com/first.m3u8'});
  const second=additionalChannelId({name:'One PH',url:'https://example.com/second.m3u8'});
  assert.notEqual(first,second);assert.ok(first.startsWith('additional:oneph:'));
  assert.notEqual(first,'One PH');
});

test('Syfy and Sci Fi keep separate names and guide identities', () => {
  const output=playlist([{name:'SYFY',url:'https://example.com/syfy.m3u8'},{name:'Sci Fi',url:'https://example.com/scifi.m3u8'}]);
  assert.ok(output.includes('tvg-id="SYFY"'));
  assert.ok(output.includes('tvg-id="Sci Fi"'));
  assert.equal(channelCategory('SYFY'),'Entertainment');
  assert.equal(channelCategory('Sci Fi'),'Entertainment');
});

test('actual playlist entries follow category order and keep playback blocks intact', () => {
  const rows=[
    {name:'NBA TV',url:'https://example.com/nba.mpd',clearKey:{id:'1'.repeat(32),value:'2'.repeat(32)}},
    {name:'GMA',url:'https://example.com/gma.m3u8'},
    {name:'CNN HD',url:'https://example.com/news.m3u8'},
    {name:'A2Z',url:'https://example.com/a2z.m3u8'},
  ];
  const input=playlist(rows,{includeDrm:true});const output=orderPlaylist(input);
  const ids=[...output.matchAll(/tvg-id="([^"]*)"/g)].map(match=>match[1]);
  assert.deepEqual(ids,['GMA','A2Z','NBA TV','CNN HD']);
  const before=input.split(/(?=^#EXTINF:)/m).slice(1).map(block=>block.trim()).sort();
  const after=output.split(/(?=^#EXTINF:)/m).slice(1).map(block=>block.trim()).sort();
  assert.deepEqual(after,before);
});

test('category numbers follow alphabetical display names and preserve playback identities', () => {
  const rows = [
    {name:'NBA TV',url:'https://example.com/sports.mpd',clearKey:{id:'1'.repeat(32),value:'2'.repeat(32)}},
    {name:'SYFY',url:'https://example.com/syfy.m3u8'},
    {name:'Sci Fi',url:'https://example.com/scifi.m3u8'},
    {name:'GMA',url:'https://example.com/gma.m3u8'},
  ];
  const original=playlist(rows,{includeDrm:true});
  const first=numberPlaylist(original);
  assert.equal(channelCategory('SYFY'),'Entertainment');
  assert.notEqual(first.assignments.SYFY,first.assignments['Sci Fi']);
  assert.ok(first.assignments['NBA TV']>=300 && first.assignments['NBA TV']<400);
  const without=numberPlaylist(playlist(rows.filter(row=>row.name!=='GMA')) ,first.assignments);
  assert.equal(without.assignments.SYFY,first.assignments.SYFY-1);
  assert.equal(without.assignments.GMA,undefined);
  const returned=numberPlaylist(original,without.assignments);
  assert.equal(returned.text,first.text);
  assert.deepEqual([...first.text.matchAll(/tvg-id="([^"]*)"/g)].map(match=>match[1]),['GMA','Sci Fi','SYFY','NBA TV']);
  assert.ok(returned.text.includes('license_key='+'1'.repeat(32)+':'+'2'.repeat(32)));
  for(const row of rows) assert.ok(returned.text.includes(row.url));
  assert.equal((returned.text.match(/tvg-chno=/g)||[]).length,rows.length);
  const numbers=[...returned.text.matchAll(/tvg-chno="(\d+)"/g)].map(match=>Number(match[1]));
  assert.deepEqual(numbers,[...numbers].sort((a,b)=>a-b));
});

test('source rename and movie category apply only to the additional 3RS identity', () => {
  const primary=playlist([{name:'3RSTV',url:'https://example.com/original.m3u8'}]);
  const id=additionalChannelId({name:'3RS TV',url:'https://example.com/additional.m3u8'});
  const additional=playlist([{name:'3RS TV *',epgId:id,url:'https://example.com/additional.m3u8'}]);
  const renamed=markAdditionalChannels(primary,additional).text;
  assert.ok(renamed.includes(',3RS SINEPINOY\n'));
  assert.ok(renamed.includes(`tvg-id="${id}"`));
  assert.ok(primary.includes(',3RSTV\n'));
  assert.equal(channelCategory('3RSTV'),'General');
  assert.equal(channelCategory(id),'Movies');
});
