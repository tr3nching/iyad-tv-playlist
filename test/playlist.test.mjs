import test from 'node:test';
import assert from 'node:assert/strict';
import { createCipheriv, randomBytes } from 'node:crypto';
import { decrypt, playlist, streamUrl, parseBackupChannels, checkBackupManifests } from '../scripts/refresh.mjs';

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
