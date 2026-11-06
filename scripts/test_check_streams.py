import json,tempfile,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
import check_streams as check

class StreamChecks(unittest.TestCase):
 def row(self,url='https://example.com/master.m3u8'):
  return {'id':'hash','channel':'Test','kind':'primary','url':url,'headers':{}}
 def test_hls_checks_media_and_keeps_primary_on_inconclusive_forbidden_fragment(self):
  calls=[]
  def sample(url,headers,deadline,media=False):
   calls.append(url)
   if url.endswith('master.m3u8'):return b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nvideo.m3u8\n',url
   if url.endswith('video.m3u8'):return b'#EXTM3U\n#EXTINF:6,\nsegment.ts\n',url
   raise urllib.error.HTTPError(url,403,'Forbidden',{},None)
  with patch.object(check,'sample',side_effect=sample):r=check.probe(self.row())
  self.assertFalse(r['reachable']);self.assertEqual(r['error'],'HTTP 403');self.assertEqual(len(calls),3)
  self.assertTrue(r['publish']);self.assertEqual(r['status'],'inconclusive')
 def test_failed_checks_do_not_hide_primary_or_additional_channels(self):
  for code,kind,expected in [(404,'primary',True),(502,'additional',True),(403,'additional',True),(403,'primary',True)]:
   row=self.row();row['kind']=kind
   with patch.object(check,'sample',side_effect=urllib.error.HTTPError(row['url'],code,'Failure',{},None)):r=check.probe(row)
   self.assertEqual(r['publish'],expected)
 def test_hls_reachable_media_and_empty_playlist(self):
  with patch.object(check,'sample',side_effect=[(b'#EXTM3U\n#EXTINF:6,\na.ts\n','https://example.com/a.m3u8'),(b'video','https://example.com/a.ts')]):
   r=check.probe(self.row());self.assertTrue(r['reachable']);self.assertEqual(r['stage'],'media')
  with patch.object(check,'sample',return_value=(b'#EXTM3U\n','https://example.com/a.m3u8')):self.assertFalse(check.probe(self.row())['reachable'])
 def test_dash_timeline_expands_representation_and_number(self):
  xml=b'<MPD><Period><AdaptationSet contentType="video"><SegmentTemplate startNumber="9" media="$RepresentationID$/$Number%04d$-$Time$.m4s"><SegmentTimeline><S t="100" d="5" r="3"/></SegmentTimeline></SegmentTemplate><Representation id="v1"/></AdaptationSet></Period></MPD>'
  self.assertEqual(check.dash_media(xml,'https://example.com/path/manifest.mpd'),'https://example.com/path/v1/0011-110.m4s')
 def test_unsupported_dash_keeps_manifest_only_classification(self):
  xml=b'<MPD><Period><AdaptationSet><SegmentTemplate media="$Time$.m4s"><SegmentTimeline><S t="1" d="5" r="-1"/></SegmentTimeline></SegmentTemplate><Representation id="v"/></AdaptationSet></Period></MPD>'
  with patch.object(check,'sample',return_value=(xml,'https://example.com/a.mpd')):r=check.probe(self.row('https://example.com/a.mpd'))
  self.assertTrue(r['reachable']);self.assertEqual(r['stage'],'manifest_only')
  multiple=b'<MPD><Period id="expired"/><Period id="current"/></MPD>'
  self.assertIsNone(check.dash_media(multiple,'https://example.com/a.mpd'))
 def test_candidates_remain_and_report_never_exposes_urls_or_headers(self):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory);text='#EXTM3U\n#EXTINF:-1 tvg-id="Test",Test\n#KODIPROP:inputstream.adaptive.manifest_headers=Origin=https%3A%2F%2Fexample.com\nhttps://example.com/a.m3u8?token=private\n'
   (out/'playlist-drm.m3u').write_text(text)
   def outcome(row):return {k:row[k] for k in ['id','channel','kind']}|{'reachable':True,'stage':'media'}
   with patch.object(check,'probe',side_effect=outcome):r=check.check(out)
   self.assertEqual((out/'playlist-drm.m3u').read_text(),text)
   report=(out/'stream-health.json').read_text();self.assertNotIn('private',report);self.assertNotIn('https://',report)
   self.assertEqual(r['reachableCount'],1)
   def failed(row):return {k:row[k] for k in ['id','channel','kind']}|{'reachable':False,'publish':True,'status':'unreachable','error':'HTTP 502'}
   with patch.object(check,'probe',side_effect=failed):r=check.check(out)
   self.assertEqual(r['reachableCount'],0);self.assertEqual(r['hiddenCount'],0)

if __name__=='__main__':unittest.main()
