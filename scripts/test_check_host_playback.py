import json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import check_host_playback as health

class HostHealthTests(unittest.TestCase):
 def row(self):return {'id':'safe','channel':'Example','kind':'primary','url':'https://example.com/a/master.m3u8','headers':{'User-Agent':'browser','Accept':'*/*'}}
 def test_first_variant_and_first_segment_are_checked(self):
  calls=[]
  def fetch(url,headers,stage,limit):
   calls.append((url,stage,headers))
   if stage=='manifest':return b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nsub/first.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=2\nsecond.m3u8\n',url,200
   if stage=='variant':return b'#EXTM3U\n#EXTINF:5,\n../first.ts\n#EXTINF:5,\nsecond.ts\n',url,200
   return b'video',url,200
  process=subprocess.CompletedProcess([],0,json.dumps({'streams':[{'codec_type':'video'}]}).encode(),b'')
  with patch.object(health,'fetch',side_effect=fetch),patch.object(health.subprocess,'run',return_value=process):result=health.check(self.row(),'ffprobe')
  self.assertEqual(result['status'],'PLAYABLE');self.assertEqual([x[0] for x in calls],['https://example.com/a/master.m3u8','https://example.com/a/sub/first.m3u8','https://example.com/a/first.ts']);self.assertTrue(all(x[2]==self.row()['headers'] for x in calls))
 def test_segment_http_error_reports_exact_stage(self):
  with patch.object(health,'fetch',side_effect=[(b'#EXTM3U\n#EXTINF:4,\nx.ts\n','https://example.com/m.m3u8',200),health.CheckError('segment','HTTP error',403)]):result=health.check(self.row(),'ffprobe')
  self.assertEqual((result['status'],result['stage'],result['httpStatus']),('FAIL','segment',403))
 def test_ffprobe_failure_is_not_playable(self):
  process=subprocess.CompletedProcess([],1,b'',b'Server returned 403 Forbidden')
  with patch.object(health,'fetch',side_effect=[(b'#EXTM3U\n#EXTINF:4,\nx.ts\n','https://example.com/m.m3u8',200),(b'abc','https://example.com/x.ts',200)]),patch.object(health.subprocess,'run',return_value=process):result=health.check(self.row(),'ffprobe')
  self.assertEqual((result['status'],result['stage'],result['httpStatus']),('FAIL','ffprobe',403))
 def test_parse_skips_title_channels_and_keeps_distinct_ids(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'list';p.write_text('#EXTM3U\n#EXTINF:-1 tvg-id="category:Movies",Title\nhttps://example.com/t.m3u8\n#EXTINF:-1 tvg-id="GMA",GMA\nhttps://example.com/g.m3u8\n',encoding='utf8');rows=health.playlist_rows(p);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['channel'],'GMA')
if __name__=='__main__':unittest.main()
