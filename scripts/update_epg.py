"""Single XMLTV builder for the PH TV playlist. Python 3.10+, standard library."""
from __future__ import annotations
import argparse,collections,concurrent.futures,copy,csv,datetime as dt,gzip,hashlib,html,io,json,re,unicodedata,urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE=Path(__file__).resolve().parent
UTC=dt.timezone.utc
MAX_BYTES=32_000_000
MAX_XML_BYTES=180_000_000
PLACEHOLDERS={'no data','no epg','no information','programming unavailable','to be announced','tba'}
CHANNEL_GROUPS=json.loads((BASE.parent/'channel-groups.json').read_text(encoding='utf-8'))
# Android TV accepts a fixed set of program genres. Some channel types use a
# broader equivalent; General has no useful genre to infer.
FALLBACK_GENRES={'Sports':'SPORTS','Movies':'MOVIES','News':'NEWS','Kids':'FAMILY_KIDS',
 'Anime':'ENTERTAINMENT','Documentaries':'EDUCATION','Music':'MUSIC',
 'Lifestyle':'LIFE_STYLE','Faith':'LIFE_STYLE','Education':'EDUCATION',
 'Entertainment':'ENTERTAINMENT'}

def apply_genre_fallback(programme,channel,group=None):
 """Supply a channel-based genre only when all supplied categories are empty."""
 categories=programme.findall('category')
 if any((category.text or '').strip() for category in categories):return False
 category=group or CHANNEL_GROUPS.get(channel.strip()) or next((value for key,value in CHANNEL_GROUPS.items() if norm(key)==norm(channel)),None)
 genre=FALLBACK_GENRES.get(category)
 if not genre:return False
 for category in categories:programme.remove(category)
 category=ET.Element('category',{'lang':'en'});category.text=genre
 preceding={'title','sub-title','desc','credits','date'}
 position=next((i for i,child in enumerate(programme) if child.tag not in preceding),len(programme))
 programme.insert(position,category)
 return True

def norm(value):return ''.join(c for c in unicodedata.normalize('NFKC',value or '').casefold() if c.isalnum())
def parse_time(value):
 if not re.fullmatch(r'\d{14} [+-]\d{4}',value or ''):raise ValueError('Missing explicit XMLTV UTC offset')
 return dt.datetime.strptime(value,'%Y%m%d%H%M%S %z').astimezone(UTC)
def stamp(value):return value.astimezone(UTC).strftime('%Y%m%d%H%M%S +0000')
def decode(data):
 if data[:2]==b'\x1f\x8b':
  with gzip.GzipFile(fileobj=io.BytesIO(data)) as archive:data=archive.read(MAX_XML_BYTES+1)
 if len(data)>MAX_XML_BYTES:raise ValueError('Source expands past limit')
 if b'<!ENTITY' in data:raise ValueError('XML entities prohibited')
 return ET.fromstring(data)
def fetch(url,cache,offline=False):
 path=BASE/'cache'/cache;path.parent.mkdir(exist_ok=True)
 if offline:data=path.read_bytes();meta={'url':url,'cached':True}
 else:
  req=urllib.request.Request(url,headers={'User-Agent':'ph-tv-epg/1.0','Accept-Encoding':'identity'})
  with urllib.request.urlopen(req,timeout=25) as response:
   data=response.read(MAX_BYTES+1)
   if len(data)>MAX_BYTES:raise ValueError('Source exceeds download limit')
   meta={'url':url,'cached':False,'retrieved_utc':dt.datetime.now(UTC).isoformat()}
  path.write_bytes(data)
 meta['sha256']=hashlib.sha256(data).hexdigest()
 return data,meta

def candidate_ids(name,feed,label,config):
 additional=config.get('_additionalMappings',{}).get(name) or config.get('_primarySourceMappings',{}).get(name)
 if additional:
  if label not in additional.get('allowedSources',[]):return []
  explicit=additional.get('sourceMap',{}).get(label,[])
  explicit=[explicit] if isinstance(explicit,str) else list(explicit)
  canonical=additional.get('canonical')
  inherited=candidate_ids(canonical,feed,label,config) if canonical else []
  return list(dict.fromkeys(explicit+inherited))
 if name.startswith(('additional:','primary-source:')):return []
 explicit=config.get('channelMap',{}).get(name,{}).get(label,[])
 explicit=[explicit] if isinstance(explicit,str) else explicit
 if name in config.get('strictChannels',[]) or label in config.get('explicitOnlySources',[]):return explicit
 # Preserve all region words and station suffixes: no fuzzy or substring matching.
 if '_name_index' not in feed:
  index=collections.defaultdict(set)
  for sid,names in feed['names'].items():
   names=[names] if isinstance(names,str) else names
   for key in {norm(sid),*(norm(n) for n in names)}:index[key].add(sid)
  feed['_name_index']=index
 matches=sorted(feed['_name_index'].get(norm(name),[]))
 return list(dict.fromkeys(explicit+(matches if len(matches)==1 else [])))

def ctc_programmes(payload,station,now):
 """Dated PH listings; infer stops only from the next published slot, never pad."""
 details=payload.get('data',{}).get('details',{})
 if str(details.get('network_id'))!=str(station['providerId']):raise ValueError('Station identifier mismatch')
 zone=dt.timezone(dt.timedelta(hours=8));today=now.astimezone(zone).date();slots={};ambiguous=set()
 for day in payload.get('data',{}).get('sched',[]):
  dates=[]
  for year in [today.year-1,today.year,today.year+1]:
   try:
    date=dt.datetime.strptime(day['date']+', '+str(year),'%A, %B %d, %Y').date()
    if date.strftime('%A').lower()!=day['date'].split(',')[0].lower():continue
    if -8<=(date-today).days<=8:dates.append(date)
   except (KeyError,ValueError):continue
  if len(dates)!=1:continue
  for row in day.get('sched',[]):
   try:
    clock=dt.datetime.strptime(row['time'].strip(),'%I:%M %p').time()
    start=dt.datetime.combine(dates[0],clock,zone).astimezone(UTC)
    title=html.unescape(row['title']).strip()
    if not title:continue
    if start in slots and slots[start]!=title:ambiguous.add(start)
    slots[start]=title
   except (KeyError,ValueError,TypeError):continue
 result=[];ordered=sorted(slots)
 for start,stop in zip(ordered,ordered[1:]):
  if start in ambiguous or not dt.timedelta(0)<stop-start<=dt.timedelta(hours=4):continue
  p=ET.Element('programme',{'channel':station['id'],'start':stamp(start),'stop':stamp(stop)})
  ET.SubElement(p,'title',{'lang':'en'}).text=slots[start]
  result.append(p)
 return result

def load_ctc(source,offline=False):
 root=ET.Element('tv');details=[];now=dt.datetime.now(UTC)
 def one(station):
  url=source['url'].replace('{id}',station['id'])
  try:
   data,meta=fetch(url,'ctc-'+station['id']+'.json',offline)
   programmes=ctc_programmes(json.loads(data),station,now)
   return station,programmes,{**meta,'station':station['id'],'programmes':len(programmes)}
  except Exception as error:return station,[],{'station':station['id'],'url':url,'error':type(error).__name__}
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for station,programmes,meta in pool.map(one,source['stations']):
   channel=ET.SubElement(root,'channel',{'id':station['id']})
   ET.SubElement(channel,'display-name').text=station['name']
   root.extend(programmes);details.append(meta)
 return root,{'url':source['url'],'cached':offline,'station_sources':details,
              'schedule_policy':'Dated Philippine listings, UTC+08:00; stops from next published slot up to four hours; unknown final stop omitted.'}

def load_sources(config,channels,offline=False):
 feeds={};metadata={}
 sources=[s for s in config['sources'] if s['name'] in config['activeSources']]
 def one(source):
  label=source['name']
  try:
   if source.get('format')=='clickthecity':root,meta=load_ctc(source,offline)
   else:data,meta=fetch(source['url'],label.lower()+'.xml.gz',offline);root=decode(data)
   names={c.get('id'):[n.text or '' for n in c.findall('display-name')] for c in root.findall('channel')}
   feed={'names':names,'programmes':collections.defaultdict(list)}
   wanted={sid for name in channels for sid in candidate_ids(name,feed,label,config)}
   programme_count=0
   for p in root.findall('programme'):
    programme_count+=1
    if p.get('channel') in wanted:feed['programmes'][p.get('channel')].append(p)
   meta.update(channel_definitions=len(names),programme_entries=programme_count)
   print(f"Loaded {label}: {len(names)} definitions, {programme_count} listings",flush=True)
   return label,feed,meta
  except Exception as error:
   print(f'Skipped {label}: {type(error).__name__}',flush=True)
   return label,{'names':{},'programmes':{}},{'url':source['url'],'error':type(error).__name__+': '+str(error),'channel_definitions':0,'programme_entries':0}
 # Parse at most two large source files at once, discard unrelated programmes immediately.
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for label,feed,meta in pool.map(one,sources):feeds[label]=feed;metadata[label]=meta
 return feeds,metadata

def prepare_channel(name,sid,feed,now,genre_channel=None,genre_group=None,station_name=None):
 programmes=[];seen=set();invalid=0;placeholders=0
 raw=feed['programmes'].get(sid,[])
 names=feed['names'].get(sid,[]);names=[names] if isinstance(names,str) else names
 titles={norm(p.findtext('title','')) for p in raw}
 only_station=bool(titles) and (any(titles=={norm(n)} for n in names) or
                              ((genre_channel or name)=='IBC13' and titles=={'ibctv13'}))
 aliases=[station_name] if isinstance(station_name,str) else (station_name or [])
 if titles:only_station=only_station or any(titles=={norm(n)} for n in [genre_channel,*aliases] if n)
 for p in raw:
  title=p.findtext('title','').strip()
  if name=='Arirang':title=title.removesuffix('"n":"').strip()
  subtitle=p.findtext('sub-title','').strip();description=p.findtext('desc','').strip()
  series=p.findtext('series-id','').strip()
  categories={norm(c.text or '') for c in p.findall('category')}
  episode_detail=(bool(subtitle) and norm(subtitle)!=norm(title) and len(description)>=15) or (bool(series) and bool(categories&{'series','movie','movies','film'}) and len(description)>=40)
  if not title or title.lower() in PLACEHOLDERS or (only_station and not episode_detail):placeholders+=1;continue
  try:a=parse_time(p.get('start'));b=parse_time(p.get('stop'))
  except ValueError:invalid+=1;continue
  if b<=a:invalid+=1;continue
  if b<now-dt.timedelta(hours=24) or a>now+dt.timedelta(days=8):continue
  # Repeated identical broadcast slots from aggregate feeds are a single programme.
  key=(a,b,title)
  if key in seen:continue
  seen.add(key);q=copy.deepcopy(p);q.set('channel',name);q.set('start',stamp(a));q.set('stop',stamp(b));q.find('title').text=title
  apply_genre_fallback(q,genre_channel or name,genre_group)
  programmes.append((a,b,q))
 programmes.sort(key=lambda x:(x[0],x[1]))
 return programmes,invalid,placeholders

def read_playlist(path):
 """Read identities and transient exact stream URLs; URLs never enter guide audits."""
 if not path.exists():return []
 result=[];entry=None
 for line in path.read_text(encoding='utf-8-sig').splitlines():
  line=line.strip()
  if line.startswith('#EXTINF:'):
   attrs=dict(re.findall(r'([\w-]+)="([^"]*)"',line))
   entry={'id':attrs.get('tvg-id',''),'display':attrs.get('tvg-name',line.split(',',1)[-1])}
  elif entry and line and not line.startswith('#'):
   entry['url']=line;result.append(entry);entry=None
 return result

def additional_entries(out,config):
 path=out/'playlist-backup.m3u'
 if not path.exists():path=out/'backup-candidates.m3u'
 if not path.exists():return []
 mapping_path=BASE.parent/'3rs-epg-mappings.json'
 mappings=json.loads(mapping_path.read_text(encoding='utf-8')).get('entries',{}) if mapping_path.exists() else {}
 override_path=BASE.parent/'source-channel-overrides.json'
 overrides=json.loads(override_path.read_text(encoding='utf-8')) if override_path.exists() else {}
 overrides=overrides.get('entries',overrides)
 primaries={};published_display={entry['id']:entry['display'] for entry in read_playlist(out/'playlist.m3u')}
 for file in ['playlist-drm.m3u','playlist.m3u']:
  for entry in read_playlist(out/file):
   if entry['id'] and not entry['id'].startswith(('additional:','primary-source:')):primaries.setdefault(entry['url'],set()).add(entry['id'])
 entries=[];seen=set()
 for entry in read_playlist(path):
  identity=entry['id']
  if not identity or identity in seen:raise ValueError('Additional playlist has missing or duplicate tvg-id')
  seen.add(identity)
  if not identity.startswith('additional:'):raise ValueError('Additional playlist entry lacks independent ID')
  entry['display']=published_display.get(identity,entry['display'])
  source_name=re.sub(r'\s*(?:\[Additional\]|\*)\s*$','',entry['display']).strip()
  override=overrides.get(identity.split(':')[1],{})
  if override.get('name'):source_name=override['name'];entry['display']=source_name
  reviewed=mappings.get(identity,{})
  duplicates=sorted(primaries.get(entry['url'],[]))
  # Ambiguous primary IDs sharing a URL do not establish a unique schedule identity.
  entries.append({'id':identity,'display':entry['display'],'sourceName':source_name if override else reviewed.get('sourceName',source_name),
    'genreGroup':override.get('category'),
    'duplicatePrimary':duplicates[0] if len(duplicates)==1 else None,'reviewed':reviewed})
 config['_additionalMappings']={e['id']:e['reviewed'] for e in entries if e['reviewed']}
 config['_unboundAdditionalMappings']=sorted(set(mappings)-seen)
 return entries

def primary_source_entries(out,config):
 """Inventory every variant, but only actual published variant IDs may receive EPG."""
 path=out/'primary-source-catalog.json'
 if not path.exists():return []
 inventory=json.loads(path.read_text(encoding='utf-8'))
 if isinstance(inventory,dict):inventory=inventory.get('entries')
 if not isinstance(inventory,list):raise ValueError('Primary-source catalog must be an array')
 mapping_path=BASE.parent/'primary-source-epg-mappings.json'
 mappings=json.loads(mapping_path.read_text(encoding='utf-8')).get('entries',{}) if mapping_path.exists() else {}
 published={};primaries={}
 for entry in read_playlist(out/'playlist-drm.m3u'):
  if entry['id'].startswith('primary-source:'):published[entry['id']]=entry
  elif not entry['id'].startswith('additional:'):primaries.setdefault(entry['url'],set()).add(entry['id'])
 entries=[];seen=set()
 for metadata in inventory:
  if metadata.get('serverIndex')==0:continue
  identity=metadata.get('id','')
  if not identity.startswith('primary-source:') or identity in seen:raise ValueError('Missing/duplicate independent primary-source ID')
  seen.add(identity)
  actual=published.get(identity);display=metadata.get('name',identity)
  override=config.get('_primarySourceOverrides',{}).get(metadata.get('parentName'),{}).get(str(metadata.get('serverIndex')),{})
  display=override.get('name',display)
  reviewed=mappings.get(identity,{})
  # Unlike URL-hashed additional IDs, index IDs can be rebound to different labels.
  # A reviewed mapping must continue to identify exactly the reviewed station name.
  expected=reviewed.get('expectedNames') or ([reviewed['expectedName']] if reviewed.get('expectedName') else [])
  binding_valid=any(' '.join(display.split()).casefold()==' '.join(label.split()).casefold() for label in expected)
  required=reviewed.get('requiredUrlContains')
  if required:binding_valid=binding_valid and bool(actual and required.casefold() in actual['url'].casefold())
  duplicates=sorted(primaries.get(actual['url'],[])) if actual else []
  entries.append({'id':identity,'display':display if override else actual['display'] if actual else display,'sourceName':display,
   'genreGroup':override.get('category',metadata.get('category')),'parentName':metadata.get('parentName'),
   'serverIndex':metadata.get('serverIndex'),'enabled':metadata.get('enabled',True),
   'published':bool(actual),'duplicatePrimary':duplicates[0] if len(duplicates)==1 else None,
   'reviewed':reviewed if binding_valid else {},'reviewedBindingMismatch':bool(reviewed and not binding_valid)})
 config['_primarySourceMappings']={e['id']:e['reviewed'] for e in entries if e['reviewed']}
 return entries

def build(catalog,out,offline=False,config_path=None):
 global CHANNEL_GROUPS
 CHANNEL_GROUPS=json.loads((BASE.parent/'channel-groups.json').read_text(encoding='utf-8'))
 now=dt.datetime.now(UTC);out.mkdir(parents=True,exist_ok=True)
 config=json.loads((config_path or BASE.parent/'epg-config.json').read_text(encoding='utf-8'))
 override_path=BASE.parent/'primary-source-overrides.json'
 config['_primarySourceOverrides']=json.loads(override_path.read_text(encoding='utf-8')) if override_path.exists() else {}
 channels=[];primary_groups={}
 for entry in json.loads(catalog.read_text(encoding='utf-8')):
  if not entry.get('enabled',True) or entry['name'] in config.get('exclude',[]):continue
  override=config['_primarySourceOverrides'].get(entry['name'],{}).get('0',{})
  identity=override.get('epgId',override.get('name',entry['name'])).strip()
  channels.append(identity)
  if override.get('category'):primary_groups[identity]=override['category']
 additional=additional_entries(out,config);additional_by_id={e['id']:e for e in additional}
 variants=primary_source_entries(out,config)
 eligible_variants={e['id']:e for e in variants if e['published'] and e['enabled']}
 channels=list(dict.fromkeys(channels+[e['id'] for e in additional]+list(eligible_variants)))
 feeds,source_meta=load_sources(config,channels,offline)
 root=ET.Element('tv',{'generator-info-name':'PH TV EPG builder'})
 stats=[];rows=[];skipped=collections.Counter();matched_any=0;selected_programmes={};additional_audit=[];variant_audit=[]
 for name in channels:
  chosen=None;attempts=[];has_any=False
  extra=additional_by_id.get(name) or eligible_variants.get(name);display=extra['display'] if extra else name
  genre_name=extra['sourceName'] if extra else name
  genre_group=extra.get('genreGroup') if extra else primary_groups.get(name)
  duplicate=extra.get('duplicatePrimary') if extra else None
  identity_reason='exact stream URL duplicate of primary' if duplicate else ('reviewed regional station alias' if extra and extra['reviewed'] else 'no reviewed station/regional identity')
  if duplicate and duplicate in selected_programmes:
   original=selected_programmes[duplicate];label,sid,ps,invalid,placeholders,upcoming=original
   programmes=[]
   for a,b,p in ps:
    q=copy.deepcopy(p);q.set('channel',name);apply_genre_fallback(q,genre_name,genre_group);programmes.append((a,b,q))
   chosen=(label,sid,programmes,invalid,placeholders,upcoming);has_any=True
  for source in ([] if chosen or duplicate else config['sources']):
   label=source['name']
   if label not in feeds:continue
   feed=feeds[label]
   for sid in candidate_ids(name,feed,label,config):
    raw=feed['programmes'].get(sid,[]);has_any=has_any or bool(raw)
    programmes,invalid,placeholders=prepare_channel(name,sid,feed,now,genre_name,genre_group,
      config.get('stationNameAliases',{}).get(name,extra['reviewed'].get('canonical') if extra else None))
    upcoming=sum(b>now for a,b,p in programmes)
    overlap=sum(b[0]<a[1] for a,b in zip(programmes,programmes[1:]))
    attempts.append({'source':label,'source_id':sid,'raw_entries':len(raw),'upcoming_programmes':upcoming,'overlaps':overlap,'invalid_rejected':invalid,'placeholder_rejected':placeholders})
    if upcoming and not overlap:
     chosen=(label,sid,programmes,invalid,placeholders,upcoming);break
   if chosen:break
  matched_any+=has_any
  if chosen:
   selected_programmes[name]=chosen
   label,sid,programmes,invalid,placeholders,upcoming=chosen
   channel=ET.SubElement(root,'channel',{'id':name});ET.SubElement(channel,'display-name').text=display
   for a,b,p in programmes:root.append(p)
   stats.append({'channel':name,'source':label,'source_id':sid,'programmes':len(programmes),'upcoming':upcoming,'first_utc':programmes[0][0].isoformat(),'last_utc':programmes[-1][1].isoformat(),'overlaps':0,'invalid_rejected':invalid,'placeholder_rejected':placeholders,'independent_broadcast_confirmation':False})
   reason='mapped'
  else:
   label=sid='';upcoming=0;reason='no usable current schedule' if has_any else 'no matching source listings';skipped[reason]+=1
   if extra:
    reason=('exact duplicate primary has no usable guide' if duplicate else
            'no reviewed station/regional identity' if not extra['reviewed'] else
            'reviewed identity has no usable current source listings')
  rows.append({'playlist_tvg_id':name,'source':label,'source_id':sid,'status':reason,'upcoming_programmes':upcoming,'attempts':attempts})
  if extra:
   audit={'playlist_tvg_id':name,'display_name':display,'source_name':genre_name,
    'status':reason,'identity_evidence':identity_reason,'duplicate_primary_id':duplicate,
    'canonical_station':extra['reviewed'].get('canonical'),'evidence':extra['reviewed'].get('evidence',''),
    'source':label,'source_id':sid,'upcoming_programmes':upcoming,'attempts':attempts}
   if name in eligible_variants:
    audit.update(parent_name=extra['parentName'],server_index=extra['serverIndex'],published=True,
                 reviewed_binding_mismatch=extra['reviewedBindingMismatch'])
    variant_audit.append(audit)
   else:additional_audit.append(audit)
 for entry in variants:
  if entry['id'] in eligible_variants:continue
  variant_audit.append({'playlist_tvg_id':entry['id'],'display_name':entry['display'],
   'source_name':entry['sourceName'],'parent_name':entry['parentName'],'server_index':entry['serverIndex'],
   'published':entry['published'],'status':'disabled variant' if not entry['enabled'] else 'not present in published DRM playlist',
   'source':'','source_id':'','upcoming_programmes':0,'attempts':[]})
 if len(stats)<config.get('minChannels',100):raise RuntimeError(f'Refusing inadequate guide: {len(stats)} current channels')
 ET.indent(root,space='  ');xml=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 total=sum(c['programmes'] for c in stats)
 for label,meta in source_meta.items():
  selected=[c for c in stats if c['source']==label]
  meta.update(selected_channels=len(selected),selected_programmes=sum(c['programmes'] for c in selected))
 report={'generated_utc':now.isoformat(),'enabled_channels':len(channels),'matched_channels_including_unusable':matched_any,'mapped_channels':len(stats),'unmapped_channels':len(channels)-len(stats),'programmes':total,'total_overlaps':0,'sources':source_meta,'source_counts':{label:{k:meta.get(k,0) for k in ['channel_definitions','programme_entries','selected_channels','selected_programmes']} for label,meta in source_meta.items()},'unmapped_reasons':dict(skipped),'channels':stats,'merge_policy':'Source priority with explicit identities or unique exact names. Try later feeds when earlier listings are stale, placeholders, invalid, or overlapping. One source per channel.','timezone_policy':'Parse explicit UTC offsets; preserve instants; player guide offset 0.','verification_scope':'Timestamp integrity and identity rules checked. Regional feeds and every broadcast are not independently confirmed. Total name matches and usable current schedules are separate counts.'}
 report['genre_policy']='Preserve non-empty programme categories. When missing, add the channel category mapped to an Android TV genre. General/unknown channels remain unclassified; never create programmes to supply a genre.'
 report['additional_entries']={'total':len(additional_audit),'mapped':sum(e['status']=='mapped' for e in additional_audit),
  'unmapped':sum(e['status']!='mapped' for e in additional_audit),'audit_file':'3rs-epg-audit.json','unbound_reviewed_mappings':config.get('_unboundAdditionalMappings',[]),
  'policy':'Use independent playlist IDs. Exact stream duplicates may reuse primary schedules; reviewed aliases use only their approved regional sources. Unidentified/custom stations receive no guessed guide.'}
 report['primary_source_entries']={'total':len(variant_audit),'published_eligible':len(eligible_variants),
  'mapped':sum(e['status']=='mapped' for e in variant_audit),'unmapped':sum(e['status']!='mapped' for e in variant_audit),
  'audit_file':'primary-source-epg-audit.json',
  'policy':'Require an enabled catalog ID actually present in the DRM playlist. No inheritance from parent name or stream index. Unique exact URL duplicates may reuse the matching primary guide; other station variants require reviewed ID/name-bound regional mappings.'}
 (out/'epg.xml.tmp').write_bytes(xml);(out/'epg.xml.tmp').replace(out/'epg.xml');(out/'epg.xml.gz').write_bytes(gzip.compress(xml,mtime=0))
 for file,value in [('epg-status.json',report),('verification.json',report),('mapping.json',rows)]:
  (out/file).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 (out/'3rs-epg-audit.json').write_text(json.dumps(additional_audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 (out/'primary-source-epg-audit.json').write_text(json.dumps(variant_audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 with (out/'mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=[k for k in rows[0] if k!='attempts'],extrasaction='ignore');writer.writeheader();writer.writerows(rows)
 (out/'report.txt').write_text(f"Generated {now.isoformat()}\nUsable current schedules {len(stats)}/{len(channels)}; matched including unusable {matched_any}; programmes {total}\n\n"+'\n'.join(f"{r['status']}  {r['playlist_tvg_id']} <- {r['source']}:{r['source_id']}" for r in rows)+'\n',encoding='utf-8')
 print(json.dumps({k:report[k] for k in ['mapped_channels','matched_channels_including_unusable','programmes','total_overlaps']},indent=2),flush=True)
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--catalog',type=Path,default=BASE.parent/'catalog.json');parser.add_argument('--out',type=Path,default=BASE.parent/'site');parser.add_argument('--config',type=Path,default=BASE.parent/'epg-config.json');parser.add_argument('--offline',action='store_true')
 args=parser.parse_args();build(args.catalog,args.out,args.offline,args.config)
