import test from 'node:test';
import assert from 'node:assert/strict';
import { createCipheriv, randomBytes } from 'node:crypto';
import { decrypt, playlist, streamUrl } from '../scripts/refresh.mjs';

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
