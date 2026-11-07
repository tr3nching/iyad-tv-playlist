import datetime as dt,json,tempfile,unittest,xml.etree.ElementTree as E
from pathlib import Path
from unittest.mock import patch
import update_epg as epg

class GuideTests(unittest.TestCase):
 def variant_build(self,variants,published,reviewed=None,overrides=None,catalog_names=None,strict=None):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory);(out/'scripts').mkdir()
   (out/'channel-groups.json').write_text('{}')
   (out/'primary-source-catalog.json').write_text(json.dumps(variants))
   (out/'primary-source-epg-mappings.json').write_text(json.dumps({'entries':reviewed or {}}))
   if overrides is not None:(out/'primary-source-overrides.json').write_text(json.dumps(overrides))
   playlist='#EXTM3U\n#EXTINF:-1 tvg-id="News",News\nhttps://example.com/primary\n'
   for identity,url in published.items():playlist+='#EXTINF:-1 tvg-id="'+identity+'" tvg-name="Variant",Variant\n'+url+'\n'
   (out/'playlist-drm.m3u').write_text(playlist)
   (out/'catalog.json').write_text(json.dumps([{'name':name} for name in catalog_names or ['News']]))
   (out/'config.json').write_text(json.dumps({'sources':[{'name':'one','url':'https://example.com/epg'}],'activeSources':['one'],'channelMap':{},'strictChannels':strict or [],'minChannels':1}))
   feed=self.feed();variant=self.feed('Different station','variant')
   feed['names'].update(variant['names']);feed['programmes'].update(variant['programmes'])
   with patch.object(epg,'BASE',out/'scripts'),patch.object(epg,'load_sources',return_value=({'one':feed},{'one':{'programme_entries':8}})):
    result=epg.build(out/'catalog.json',out,config_path=out/'config.json')
   audit=json.loads((out/'primary-source-epg-audit.json').read_text())
   self.assertNotIn('https://',json.dumps(audit))
   return result,audit,E.parse(out/'epg.xml').getroot()

 def test_primary_variant_does_not_inherit_parent_or_match_its_display_name(self):
  identity='primary-source:news:1'
  result,audit,xml=self.variant_build([{'id':identity,'parentName':'News','serverIndex':1,'name':'Different station','enabled':True}],{identity:'https://example.com/different'})
  self.assertEqual(result['primary_source_entries']['mapped'],0)
  self.assertEqual(audit[0]['status'],'no reviewed station/regional identity')
  self.assertFalse(any(p.get('channel')==identity for p in xml.findall('programme')))

 def test_primary_variant_requires_actual_publication_and_enabled_metadata(self):
  variants=[{'id':'primary-source:news:1','parentName':'News','serverIndex':1,'name':'Stream 2','enabled':True},
            {'id':'primary-source:news:2','parentName':'News','serverIndex':2,'name':'Disabled','enabled':False}]
  result,audit,_=self.variant_build(variants,{'primary-source:news:2':'https://example.com/primary'})
  self.assertEqual(result['enabled_channels'],1);self.assertEqual(result['primary_source_entries']['total'],2)
  self.assertEqual({a['status'] for a in audit},{'not present in published DRM playlist','disabled variant'})

 def test_primary_variant_exact_url_duplicate_has_independent_id_and_category(self):
  identity='primary-source:news:1'
  result,audit,xml=self.variant_build([{'id':identity,'parentName':'News','serverIndex':1,'name':'Stream 2','category':'Sports'}],{identity:'https://example.com/primary'})
  self.assertEqual(result['primary_source_entries']['mapped'],1)
  self.assertEqual(audit[0]['duplicate_primary_id'],'News')
  programmes=[p for p in xml.findall('programme') if p.get('channel')==identity]
  self.assertEqual(len(programmes),4);self.assertTrue(all(p.findtext('category')=='SPORTS' for p in programmes))

 def test_primary_variant_reviewed_mapping_is_name_bound_and_region_restricted(self):
  identity='primary-source:news:1'
  reviewed={identity:{'expectedName':'Different station','allowedSources':['one'],'sourceMap':{'one':['variant']}}}
  result,audit,_=self.variant_build([{'id':identity,'parentName':'News','serverIndex':1,'name':'Different station'}],{identity:'https://example.com/different'},reviewed)
  self.assertEqual(result['primary_source_entries']['mapped'],1);self.assertEqual(audit[0]['source_id'],'variant')
  result,audit,_=self.variant_build([{'id':identity,'parentName':'News','serverIndex':1,'name':'Renamed station'}],{identity:'https://example.com/different'},reviewed)
  self.assertEqual(result['primary_source_entries']['mapped'],0);self.assertTrue(audit[0]['reviewed_binding_mismatch'])
  self.assertEqual(epg.candidate_ids(identity,self.feed(),'wrong',{'_primarySourceMappings':reviewed}),[])

 def test_primary_inventory_wrapper_and_route_bound_mapping(self):
  identity='primary-source:news:1'
  inventory={'entries':[{'id':'News','serverIndex':0,'name':'News'},
              {'id':identity,'parentName':'News','serverIndex':1,'name':'Different station'}]}
  reviewed={identity:{'expectedName':'Different station','requiredUrlContains':'USA_STATION','allowedSources':['one'],'sourceMap':{'one':['variant']}}}
  result,audit,_=self.variant_build(inventory,{identity:'https://example.com/other-route'},reviewed)
  self.assertEqual(result['primary_source_entries']['total'],1);self.assertEqual(result['primary_source_entries']['mapped'],0)
  self.assertTrue(audit[0]['reviewed_binding_mismatch'])
  result,audit,_=self.variant_build(inventory,{identity:'https://example.com/USA_STATION/index.mpd'},reviewed)
  self.assertEqual(result['primary_source_entries']['mapped'],1)

 def test_syfy_base_and_variant_overrides_remain_independent(self):
  identity='primary-source:syfy:1'
  inventory={'entries':[{'id':identity,'parentName':'SYFY','serverIndex':1,'name':'SYFY Stream 2','category':'General'}]}
  overrides={'SYFY':{'0':{'name':'Sci Fi','epgId':'Sci Fi','category':'Entertainment'},'1':{'name':'SyFy 2','category':'Entertainment'}}}
  reviewed={identity:{'expectedNames':['SyFy 2'],'requiredUrlContains':'USA_SYFY','allowedSources':['one'],'sourceMap':{'one':['variant']}}}
  result,audit,xml=self.variant_build(inventory,{identity:'https://example.com/USA_SYFY/index.mpd'},reviewed,overrides,['News','SYFY'],['Sci Fi','SYFY'])
  self.assertEqual(result['primary_source_entries']['mapped'],1)
  self.assertEqual(audit[0]['source_name'],'SyFy 2');self.assertEqual(audit[0]['parent_name'],'SYFY')
  self.assertNotIn('SYFY',[c.get('id') for c in xml.findall('channel')])
  self.assertNotIn('Sci Fi',[c.get('id') for c in xml.findall('channel')])
  self.assertTrue(all(p.findtext('category')=='ENTERTAINMENT' for p in xml.findall('programme') if p.get('channel')==identity))

 def test_no_primary_variants_preserves_existing_333_identity_inventory(self):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)
   (out/'catalog.json').write_text(json.dumps([{'name':'News'}]+[{'name':f'Other {n}'} for n in range(245)]))
   (out/'config.json').write_text(json.dumps({'sources':[{'name':'one','url':'https://example.com'}],'activeSources':['one'],'minChannels':1}))
   (out/'backup-candidates.m3u').write_text('#EXTM3U\n'+''.join(f'#EXTINF:-1 tvg-id="additional:unreviewed{n}:hash" tvg-name="Unreviewed {n}",Unreviewed\nhttps://example.com/additional/{n}\n' for n in range(87)))
   with patch.object(epg,'load_sources',return_value=({'one':self.feed()},{'one':{'programme_entries':4}})):
    result=epg.build(out/'catalog.json',out,config_path=out/'config.json')
   self.assertEqual(result['enabled_channels'],333);self.assertEqual(result['additional_entries']['total'],87)
   self.assertEqual(result['primary_source_entries']['total'],0)

 def test_additional_alias_is_restricted_to_approved_region(self):
  identity='additional:sports:123'
  cfg={'_additionalMappings':{identity:{'canonical':'NBA TV Philippines','allowedSources':['PH2'],'sourceMap':{'PH2':['ph']}}}}
  self.assertEqual(epg.candidate_ids(identity,self.feed('NBA TV Philippines','ph'),'PH2',cfg),['ph'])
  self.assertEqual(epg.candidate_ids(identity,self.feed('NBA TV','us'),'US2',cfg),[])
  self.assertEqual(epg.candidate_ids('additional:unreviewed:456',self.feed('Unreviewed','other'),'PH2',cfg),[])

 def test_additional_metadata_includes_unavailable_entries_and_unique_ids(self):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)
   (out/'backup-candidates.m3u').write_text('#EXTM3U\n#EXTINF:-1 tvg-id="additional:one:111" tvg-name="Same [Additional]",Same\nhttps://example.com/one\n#EXTINF:-1 tvg-id="additional:two:222" tvg-name="Same [Additional]",Same\nhttps://example.com/two\n')
   (out/'playlist.m3u').write_text('#EXTM3U\n#EXTINF:-1 tvg-id="News",News\nhttps://example.com/one\n')
   entries=epg.additional_entries(out,{})
   self.assertEqual(len(entries),2);self.assertNotEqual(entries[0]['id'],entries[1]['id'])
   self.assertEqual(entries[0]['duplicatePrimary'],'News');self.assertIsNone(entries[1]['duplicatePrimary'])
   self.assertNotIn('https://',json.dumps(entries));self.assertNotIn('url',entries[0])

 def test_additional_genre_uses_source_name_not_opaque_id(self):
  identity='additional:nba:123'
  programmes,_,_=epg.prepare_channel(identity,'nba',self.feed('NBA TV','nba'),dt.datetime.now(epg.UTC),'NBA TV')
  self.assertTrue(all(p.get('channel')==identity and p.findtext('category')=='SPORTS' for a,b,p in programmes))

 def test_additional_station_placeholders_cannot_bypass_exclusion_using_namespace(self):
  for name,title in [('IBC13','IBC TV 13'),('A2Z','A2Z'),('PTV4','PTV 4')]:
   feed=self.feed('provider-code','opaque')
   for p in feed['programmes']['opaque']:p.find('title').text=title
   programmes,_,placeholders=epg.prepare_channel('additional:station:123','opaque',feed,dt.datetime.now(epg.UTC),name)
   self.assertEqual(programmes,[]);self.assertEqual(placeholders,4)

 def test_source_only_override_preserves_additional_id_and_category(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'scripts').mkdir()
   identity='additional:3rstv:123'
   (root/'source-channel-overrides.json').write_text(json.dumps({'3rstv':{'name':'3RS SINEPINOY','category':'Movies'}}))
   (root/'backup-candidates.m3u').write_text('#EXTM3U\n#EXTINF:-1 tvg-id="'+identity+'" tvg-name="3RS TV [Additional]",3RS TV\nhttps://example.com/3rs\n')
   with patch.object(epg,'BASE',root/'scripts'):entries=epg.additional_entries(root,{})
   self.assertEqual(entries[0]['id'],identity);self.assertEqual(entries[0]['sourceName'],'3RS SINEPINOY')
   self.assertEqual(entries[0]['display'],'3RS SINEPINOY');self.assertEqual(entries[0]['genreGroup'],'Movies')
   self.assertFalse(entries[0]['reviewed']);self.assertIsNone(entries[0]['duplicatePrimary'])

 def test_exact_duplicate_reuses_actual_primary_schedule_with_independent_id(self):
  identity='additional:news:111'
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)
   cfg={'sources':[{'name':'one','url':'https://example.com'}],'activeSources':['one'],'channelMap':{},'minChannels':1}
   (out/'config.json').write_text(json.dumps(cfg));(out/'catalog.json').write_text('[{"name":"News"}]')
   (out/'playlist.m3u').write_text('#EXTM3U\n#EXTINF:-1 tvg-id="News",News\nhttps://example.com/one\n')
   (out/'backup-candidates.m3u').write_text('#EXTM3U\n#EXTINF:-1 tvg-id="'+identity+'" tvg-name="News [Additional]",News\nhttps://example.com/one\n#EXTINF:-1 tvg-id="additional:custom:222" tvg-name="Custom",Custom\nhttps://example.com/unavailable\n')
   feed=self.feed();metadata={'one':{'programme_entries':4}}
   with patch.object(epg,'load_sources',return_value=({'one':feed},metadata)):
    result=epg.build(out/'catalog.json',out,config_path=out/'config.json')
   self.assertEqual(result['additional_entries']['total'],2);self.assertEqual(result['additional_entries']['mapped'],1)
   xml=E.parse(out/'epg.xml').getroot();p=[p for p in xml.findall('programme') if p.get('channel')==identity]
   self.assertEqual(len(p),4);self.assertEqual(p[0].get('start'),epg.stamp(epg.parse_time(feed['programmes']['news'][0].get('start'))))
   audit=json.loads((out/'3rs-epg-audit.json').read_text())
   self.assertEqual(len(audit),2);self.assertEqual(audit[0]['duplicate_primary_id'],'News')
   self.assertEqual(audit[1]['status'],'no reviewed station/regional identity')
   self.assertNotIn('https://',json.dumps(audit))

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

 def test_missing_genre_uses_channel_category_without_changing_schedule(self):
  feed=self.feed('NBA TV','nba')
  original=E.tostring(feed['programmes']['nba'][0])
  programmes,_,_=epg.prepare_channel('NBA TV','nba',feed,dt.datetime.now(epg.UTC))
  self.assertTrue(programmes)
  self.assertTrue(all(p.findtext('category')=='SPORTS' for a,b,p in programmes))
  self.assertEqual(E.tostring(feed['programmes']['nba'][0]),original)
  for a,b,p in programmes:
   self.assertEqual(epg.parse_time(p.get('start')),a)
   self.assertEqual(epg.parse_time(p.get('stop')),b)

 def test_supplied_genres_are_preserved_and_fallback_is_idempotent(self):
  p=E.Element('programme');E.SubElement(p,'category',{'lang':'fr'}).text='Actual programme genre'
  before=E.tostring(p)
  self.assertFalse(epg.apply_genre_fallback(p,'NBA TV'))
  self.assertEqual(E.tostring(p),before)
  blank=E.Element('programme');E.SubElement(blank,'title').text='A programme'
  E.SubElement(blank,'category').text='  ';E.SubElement(blank,'episode-num').text='1'
  self.assertTrue(epg.apply_genre_fallback(blank,'Cartoon Network'))
  self.assertFalse(epg.apply_genre_fallback(blank,'Cartoon Network'))
  self.assertEqual([c.text for c in blank.findall('category')],['FAMILY_KIDS'])
  self.assertEqual([child.tag for child in blank],['title','category','episode-num'])
  variant=E.Element('programme');E.SubElement(variant,'title').text='Music show'
  self.assertTrue(epg.apply_genre_fallback(variant,'HALLYPOP'))
  self.assertEqual(variant.findtext('category'),'MUSIC')
  unknown=E.Element('programme')
  self.assertFalse(epg.apply_genre_fallback(unknown,'Unlisted channel'))
  self.assertEqual(unknown.findall('category'),[])

if __name__=='__main__':unittest.main()
