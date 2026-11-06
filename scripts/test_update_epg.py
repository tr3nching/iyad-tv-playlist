import datetime as dt,json,tempfile,unittest,xml.etree.ElementTree as E
from pathlib import Path
from unittest.mock import patch
import update_epg as epg

class GuideTests(unittest.TestCase):
 def run_build(self,feeds,mapping=None,strict=None):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory);names=list(mapping or {'News':{},'Sports':{}})
   cfg={'sources':[{'name':label,'url':'https://example.com/'+label} for label in feeds],'activeSources':list(feeds),'channelMap':mapping or {},'strictChannels':strict or [],'minChannels':1}
   (out/'config.json').write_text(json.dumps(cfg));(out/'catalog.json').write_text(json.dumps([{'name':n,'enabled':True} for n in names]))
   metadata={label:{'programme_entries':sum(len(v) for v in f['programmes'].values())} for label,f in feeds.items()}
   with patch.object(epg,'load_sources',return_value=(feeds,metadata)):r=epg.build(out/'catalog.json',out,config_path=out/'config.json')
   self.assertEqual(len(E.parse(out/'epg.xml').getroot().findall('channel')),r['mapped_channels'])
   return r
 def feed(self,name='News',sid='news',offset=0,stale=False,overlap=False):
  now=dt.datetime.now(epg.UTC).replace(microsecond=0)+dt.timedelta(days=-4 if stale else 0)
  ps=[]
  for n in range(4):
   a=now+dt.timedelta(hours=n);b=a+dt.timedelta(minutes=90 if overlap else 30)
   zone=dt.timezone(dt.timedelta(hours=offset))
   p=E.Element('programme',{'channel':sid,'start':a.astimezone(zone).strftime('%Y%m%d%H%M%S %z'),'stop':b.astimezone(zone).strftime('%Y%m%d%H%M%S %z')});E.SubElement(p,'title').text=f'Episode {n}';ps.append(p)
  return {'names':{sid:[name]},'programmes':{sid:ps}}
 def test_explicit_offsets_preserve_absolute_instant(self):
  self.assertEqual(epg.parse_time('20261106110000 +0800'),epg.parse_time('20261106030000 +0000'))
  with self.assertRaises(ValueError):epg.parse_time('20261106110000')
 def test_stale_first_source_recovers_from_later_feed(self):
  r=self.run_build({'first':self.feed(stale=True),'next':self.feed(offset=8)},{'News':{}})
  self.assertEqual(r['channels'][0]['source'],'next');self.assertEqual(r['total_overlaps'],0)
 def test_overlapping_first_feed_does_not_block_recovery(self):
  r=self.run_build({'first':self.feed(overlap=True),'next':self.feed()},{'News':{}})
  self.assertEqual(r['channels'][0]['source'],'next')
 def test_strict_identity_prevents_philippines_nba_matching_us(self):
  a=self.feed('NBA TV Philippines','ph');b=self.feed('NBA TV','us')
  r=self.run_build({'first':a,'next':b},{'NBA TV':{'next':['us']}},['NBA TV'])
  self.assertEqual(r['channels'][0]['source_id'],'us')
 def test_region_words_are_not_removed_and_ambiguous_names_rejected(self):
  f=self.feed('GMA Pinoy TV','pinoy')
  self.assertEqual(epg.candidate_ids('GMA',f,'x',{}),[])
  f['names']['other']=['GMA Pinoy TV']
  f.pop('_name_index',None)
  self.assertEqual(epg.candidate_ids('GMA Pinoy TV',f,'x',{}),[])
 def test_invalid_and_placeholder_only_schedules_are_rejected(self):
  f=self.feed();p=f['programmes']['news'][0];p.set('stop',p.get('start'))
  for q in f['programmes']['news'][1:]:q.find('title').text='No data'
  ps,invalid,placeholders=epg.prepare_channel('News','news',f,dt.datetime.now(epg.UTC))
  self.assertEqual((len(ps),invalid,placeholders),(0,1,3))

if __name__=='__main__':unittest.main()
