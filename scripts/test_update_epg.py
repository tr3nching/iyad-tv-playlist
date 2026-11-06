import datetime as dt,json,tempfile,unittest,xml.etree.ElementTree as E
from pathlib import Path
from unittest.mock import patch
import update_epg as epg

class MergeTests(unittest.TestCase):
 def feeds(self, shift=0):
  now=dt.datetime.now(epg.UTC).replace(microsecond=0)
  result={s:{'names':{},'programmes':{}} for s in ['PH1','PH2']}
  for name in ['NHK World Japan','One Sports','Animal Planet']:
   for label,mapping in [('PH2',epg.MAPPING),('PH1',epg.PH1_MAPPING)]:
    if name not in mapping:continue
    cid=epg.ids(mapping,name)[0];result[label]['names'][cid]=name
    result[label]['programmes'][cid]=[]
    for n in range(40):
     start=now+dt.timedelta(hours=n+(shift if label=='PH1' else 0))
     p=E.Element('programme',{'channel':cid,'start':epg.stamp(start),'stop':epg.stamp(start+dt.timedelta(minutes=30))})
     E.SubElement(p,'title').text=f'{name} episode {n}'
     result[label]['programmes'][cid].append(p)
  return result

 def test_empty_ph1_cannot_claim_alignment(self):
  feeds=self.feeds();feeds['PH1']['programmes']={}
  r=epg.check_source_alignment(feeds)
  self.assertEqual(r['state'],'no_programmes');self.assertFalse(r['PH1_eligible'])

 def test_matching_absolute_instants_accept_ph1(self):
  r=epg.check_source_alignment(self.feeds())
  self.assertTrue(r['PH1_eligible']);self.assertEqual(r['delta_histogram_seconds'],{0:80})

 def test_eight_hour_shift_is_held_without_correction(self):
  r=epg.check_source_alignment(self.feeds(8))
  self.assertEqual(r['state'],'nonzero_shift_requires_review')
  self.assertFalse(r['PH1_eligible']);self.assertEqual(r['correction_applied_seconds'],0)

 def test_single_source_per_channel_and_new_ph1_fallback(self):
  feeds=self.feeds();metadata={s:{'programme_entries':sum(len(v) for v in feeds[s]['programmes'].values())} for s in feeds}
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory);catalog=out/'catalog.json'
   catalog.write_text(json.dumps([{'name':n,'enabled':True} for n in ['NHK World Japan','One Sports','Animal Planet']]))
   with patch.object(epg,'load_sources',return_value=(feeds,metadata)):
    r=epg.build(catalog,out)
   by_name={c['channel']:c for c in r['channels']}
   self.assertEqual(by_name['NHK World Japan']['source'],'PH2')
   self.assertEqual(by_name['One Sports']['source'],'PH2')
   self.assertEqual(by_name['Animal Planet']['source'],'PH1')
   self.assertEqual(r['programmes'],120);self.assertEqual(r['total_overlaps'],0)
   self.assertEqual(len(E.parse(out/'epg.xml').getroot().findall('programme')),120)

 def test_import_uses_exact_ids_preserves_ph2_and_holds_wrong_identities(self):
  feeds=self.feeds(); now=dt.datetime.now(epg.UTC).replace(microsecond=0)
  feeds['PH_EPG']={'names':{},'programmes':{}}
  for name in ['NHK World Japan','Crunchyroll','NBA TV','TV5','Broken Times','Stale Guide','Overlapping Guide']:
   feeds['PH_EPG']['names'][name]=name; entries=[]
   for n in range(70):
    start=now+dt.timedelta(hours=n if name!='Stale Guide' else n-72)
    stop=start+dt.timedelta(minutes=90 if name=='Overlapping Guide' else -1 if name=='Broken Times' else 30)
    p=E.Element('programme',{'channel':name,'start':epg.stamp(start),'stop':epg.stamp(stop)})
    E.SubElement(p,'title').text=f'Programme {n}';entries.append(p)
   feeds['PH_EPG']['programmes'][name]=entries
  names=['NHK World Japan','Crunchyroll','NBA TV','TV5','Broken Times','Stale Guide','Overlapping Guide','crunchyroll']
  metadata={s:{'programme_entries':sum(len(v) for v in f['programmes'].values())} for s,f in feeds.items()}
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory);catalog=out/'catalog.json';catalog.write_text(json.dumps([{'name':n,'enabled':True} for n in names]))
   with patch.object(epg,'load_sources',return_value=(feeds,metadata)):r=epg.build(catalog,out)
   chosen={c['channel']:c for c in r['channels']}
   self.assertEqual(set(chosen),{'NHK World Japan','Crunchyroll'})
   self.assertEqual(chosen['NHK World Japan']['source'],'PH2')
   self.assertEqual(chosen['Crunchyroll']['source'],'PH_EPG')
   self.assertEqual(r['total_overlaps'],0)

if __name__=='__main__':unittest.main()
