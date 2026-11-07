import test from 'node:test';
import assert from 'node:assert/strict';
import { createCipheriv, randomBytes } from 'node:crypto';
import { mkdtemp, readFile, writeFile, unlink, rmdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { labelNbaEvents, configuredSourceCategory, addCategoryHeaders, validatedAdditional, primarySourceJobs, resolveChannel, numberPlaylist, orderPlaylist, channelCategory, decrypt, playlist, streamUrl, parseBackupChannels, checkBackupManifests, combinePlaylists, markAdditionalChannels, streamCheckId, additionalChannelId } from '../scripts/refresh.mjs';

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
  const files = ['backup-validation.json', 'playlist-drm.m3u', 'playlist-backup.m3u', 'playlist.m3u', 'playlist-combined.m3u', 'playlist-status.json', 'channel-numbers.json'];
  try {
    const primary = playlist([{ name: 'NBA TV', url: 'https://example.com/news.mpd', clearKey: { id: '1'.repeat(32), value: '2'.repeat(32) } }], { includeDrm: true });
    const backup = playlist([{ name: 'NBA TV [Backup]', epgId: 'NBA TV', group: 'Backup', url: 'https://example.com/backup.m3u8' }]);
    await writeFile(new URL('playlist-drm.m3u', output), primary);
    await writeFile(new URL('playlist-backup.m3u', output), backup);
    await writeFile(new URL('backup-validation.json',output),JSON.stringify({checkedAt:new Date().toISOString(),channels:[{id:streamCheckId('additional',{id:'NBA TV',url:'https://example.com/backup.m3u8'}),validated:true,decodedFrames:25}]}));
    await combinePlaylists(output);
    const canonical = await readFile(new URL('playlist.m3u', output), 'utf8');
    assert.equal((canonical.match(/^#EXTM3U/gm) || []).length, 1);
    assert.equal((canonical.match(/^#EXTINF:/gm) || []).length, 3);
    assert.ok(canonical.includes('license_type=org.w3.clearkey'));
    assert.equal((canonical.match(/group-title="Sports"/g) || []).length, 3);
    assert.ok(canonical.includes('NBA TV *'));
    assert.equal(canonical, await readFile(new URL('playlist-combined.m3u', output), 'utf8'));
    assert.equal(JSON.parse(await readFile(new URL('playlist-status.json', output))).entryCount, 3);
    await unlink(new URL('playlist-backup.m3u', output));
    await combinePlaylists(output);
    const fallback = await readFile(new URL('playlist.m3u', output), 'utf8');
    assert.ok(fallback.includes('license_type=org.w3.clearkey'));
    assert.equal((fallback.match(/^#EXTINF:/gm) || []).length, 2);
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

test('additional sources require recent decoding proof bound to the exact URL', () => {
  const row={name:'GMA',epgId:'additional:gma:test',url:'https://example.com/first.m3u8'};
  const text=playlist([row]);const now=Date.now();
  const report={checkedAt:new Date(now).toISOString(),channels:[{id:streamCheckId('additional',{id:row.epgId,url:row.url}),validated:true,decodedFrames:25}]};
  assert.ok(validatedAdditional(text,report,now).includes(row.url));
  assert.ok(!validatedAdditional(text,{},now).includes(row.url));
  assert.ok(!validatedAdditional(text,{...report,checkedAt:new Date(now-25*3600000).toISOString()},now).includes(row.url));
  assert.ok(!validatedAdditional(text,{...report,channels:[{...report.channels[0],decodedFrames:0}]},now).includes(row.url));
  assert.ok(!validatedAdditional(playlist([{...row,url:'https://example.com/replacement.m3u8'}]),report,now).includes('#EXTINF:'));
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
  assert.equal(channelCategory('3RSTV'),'Movies');
  assert.equal(channelCategory(id),'Movies');
});

test('all enabled source slots keep their playback indexes and distinct identities', () => {
  const channels=[{name:'Fixture Parent',enabled:true,alt_name:'Stream 2',alt_enabled:false,alt_name2:'Different Channel',alt_name20:'Last Channel'}, {name:'Disabled Parent',enabled:false,alt_name:'Hidden'}];
  const jobs=primarySourceJobs(channels);
  assert.deepEqual(jobs.map(job=>job.serverIndex),[0,2,20]);
  assert.equal(jobs[1].name,'Different Channel');
  assert.equal(jobs[1].parentName,'Fixture Parent');
  assert.equal(jobs[1].id,'primary-source:fixtureparent:2');
  assert.notEqual(jobs[1].id,jobs[2].id);
  const syfy=primarySourceJobs([{name:'SYFY',alt_name:'Stream 2'}]);
  assert.deepEqual(syfy.map(job=>job.name),['Sci Fi','SyFy 2']);
  assert.deepEqual(syfy.map(job=>job.id),['Sci Fi','primary-source:syfy:1']);
  assert.ok(syfy.every(job=>job.category==='Entertainment'));
});

test('alternate playback requests use the original container name and actual source index', async () => {
  const key='0123456789abcdef';const iv=Buffer.alloc(16);const cipher=createCipheriv('aes-128-cbc',Buffer.from(key),iv);
  const data=Buffer.concat([iv,cipher.update(JSON.stringify({url:'https://example.com/alternate.m3u8',type:'hls'})),cipher.final()]).toString('base64');
  const job={name:'Different Channel',parentName:'Fixture Parent',serverIndex:3,epgId:'primary-source:fixtureparent:3'};
  const row=await resolveChannel(job,key,async(path,body)=>{assert.equal(path,'/play');assert.deepEqual(body,{channelName:'Fixture Parent',serverIndex:3});return{data};});
  assert.equal(row.epgId,job.epgId);assert.equal(row.name,'Different Channel');
});

test('large categories retain unique whole numbers and alphabetical order', () => {
  const rows=Array.from({length:105},(_,i)=>({name:`NBA TV ${104-i}`,epgId:`additional:nbatv:${104-i}`,url:`https://example.com/${i}.m3u8`}));
  const output=numberPlaylist(playlist(rows)).text;
  const numbers=[...output.matchAll(/tvg-chno="([^"]*)"/g)].map(match=>Number(match[1]));
  assert.equal(new Set(numbers).size,105);
  assert.ok(numbers.every(Number.isInteger));
  assert.deepEqual(numbers,[...numbers].sort((a,b)=>a-b));
  assert.ok(output.indexOf('tvg-name="NBA TV 2"')<output.indexOf('tvg-name="NBA TV 10"'));
});


test('source alternates use their base major number and padded actual source index', () => {
  const jobs=primarySourceJobs([{name:'SYFY',alt_name:'Stream 2',alt_name2:'Stream 3'}]);
  const rows=jobs.map((job,index)=>({...job,url:`https://example.com/${index}.m3u8`}));
  rows.push({name:'Sci Fi *',epgId:'additional:scifi:fixture',url:rows[0].url});
  const {assignments}=numberPlaylist(playlist(rows));
  const major=assignments['Sci Fi'];
  assert.equal(assignments['primary-source:syfy:1'],`${major}.001`);
  assert.equal(assignments['primary-source:syfy:2'],`${major}.002`);
  assert.equal(assignments['additional:scifi:fixture'],`${major}.003`);
  assert.equal(new Set(Object.values(assignments)).size,4);
});


test('source numbering handles escaped base channel identities', () => {
  const jobs=primarySourceJobs([{name:'R&B Test',alt_name:'Stream 2'}]);
  const rows=jobs.map((job,index)=>({...job,url:`https://example.com/escaped-${index}.m3u8`}));
  const {assignments}=numberPlaylist(playlist(rows));
  assert.equal(assignments['primary-source:rbtest:1'],`${assignments['R&B Test']}.001`);
});


test('category title channels lead their block and reserve its starting whole number', () => {
 const input=playlist([{name:'A2Z',url:'https://example.com/a.m3u8'},{name:'NBA TV',url:'https://example.com/b.m3u8'}]);
 const first=numberPlaylist(addCategoryHeaders(input));
 assert.equal(first.assignments['category:Entertainment'],100);
 assert.equal(first.assignments.A2Z,101);
 assert.equal(first.assignments['category:Sports'],300);
 assert.equal(first.assignments['NBA TV'],301);
 assert.equal((first.text.match(/tvg-id="category:/g)||[]).length,2);
 assert.equal(numberPlaylist(addCategoryHeaders(first.text)).text,first.text);
});


test('a named source of a different channel type keeps its own category number', () => {
 const jobs=primarySourceJobs([{name:'Fixture Parent',alt_name:'ABC Kids'}]);
 const rows=jobs.map((job,index)=>({...job,url:`https://example.com/different-type-${index}.m3u8`}));
 const {assignments}=numberPlaylist(playlist(rows));
 assert.ok(Number.isInteger(assignments['primary-source:fixtureparent:1']));
 assert.ok(assignments['primary-source:fixtureparent:1']>=800&&assignments['primary-source:fixtureparent:1']<900);
});


test('cached generic sources inherit corrected broad categories without relabeling named sources', () => {
 assert.equal(configuredSourceCategory({name:'NBA TV Stream 2',parentName:'NBA TV',category:'General'}),'Sports');
 assert.equal(configuredSourceCategory({name:'Unknown Station',parentName:'NBA TV',category:'General'}),'General');
 assert.equal(configuredSourceCategory({name:'ABC Kids',parentName:'NBA TV',category:'General'}),'Kids');
});


test('requested categories persist for named and generic alternate streams', () => {
  const jobs=primarySourceJobs([{name:'MUX DOS',alt_name:'MUX WORLD',alt_name2:'Stream 3'}, {name:'Sony Channel',alt_name:'Sony Movies Stream 2'}, {name:'BS10 + more Converge Channels',alt_name:'Phoenix Television'}]);
  assert.deepEqual(jobs.map(j=>j.category),['Lifestyle','Entertainment','Lifestyle','Movies','Movies','Entertainment','Documentaries']);
  for (const job of jobs.filter(j=>j.serverIndex)) assert.equal(configuredSourceCategory({...job,category:'General'}),job.category);
  for (const name of ['3RSTV','Star TV Philippines','STBS Global','HypeTV','Sony One Action Hits']) assert.equal(channelCategory(name),'Movies');
  assert.equal(channelCategory('Dream TV PH'),'Entertainment');
  assert.equal(channelCategory('Media Pilipinas TV'),'Entertainment');
  assert.equal(channelCategory('RJ Digitv'),'Music');
});

test('category headers use requested channel numbers and order', () => {
  const names=['Entertainment','Movies','Sports','Lifestyle','Documentaries','Education','News','Kids','Anime','Faith','Music','General'];
  const rows=names.map(name=>({name,epgId:`category:${name}`,url:'https://example.com/title.m3u8'})).reverse();
  const result=numberPlaylist(playlist(rows));
  assert.deepEqual(names.map(name=>result.assignments[`category:${name}`]),names.map((_,i)=>(i+1)*100));
  assert.deepEqual([...result.text.matchAll(/tvg-id="category:([^"]+)"/g)].map(m=>m[1]),names);
});


test('NBA event streams get an NBA prefix without changing their identity or other channels', () => {
 const rows=[{name:'8:00am Celtics vs Hornets',epgId:'primary-source:nbatv:2',url:'https://example.com/event'}, {name:'NBA TV',url:'https://example.com/nba'}, {name:'8:00am Other vs Game',epgId:'primary-source:other:1',url:'https://example.com/other'}];
 const text=labelNbaEvents(playlist(rows));
 assert.ok(text.includes('tvg-name="NBA TV - 8:00am Celtics vs Hornets"'));
 assert.ok(text.includes('tvg-id="primary-source:nbatv:2"'));
 assert.ok(text.includes('tvg-name="8:00am Other vs Game"'));
 assert.equal(labelNbaEvents(text),text);
});
