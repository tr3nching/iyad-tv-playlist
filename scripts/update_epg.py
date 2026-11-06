"""Single XMLTV builder for the PH TV playlist. Python 3.10+, standard library."""
from __future__ import annotations
import argparse,collections,concurrent.futures,copy,csv,datetime as dt,gzip,hashlib,io,json,re,urllib.request
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

def apply_genre_fallback(programme,channel):
 """Supply a channel-based genre only when all supplied categories are empty."""
 categories=programme.findall('category')
 if any((category.text or '').strip() for category in categories):return False
 genre=FALLBACK_GENRES.get(CHANNEL_GROUPS.get(channel.strip()))
 if not genre:return False
 for category in categories:programme.remove(category)
 category=ET.Element('category',{'lang':'en'});category.text=genre
 preceding={'title','sub-title','desc','credits','date'}
 position=next((i for i,child in enumerate(programme) if child.tag not in preceding),len(programme))
 programme.insert(position,category)
 return True

def norm(value):return re.sub(r'[^a-z0-9]','',(value or '').lower())
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
 explicit=config.get('channelMap',{}).get(name,{}).get(label,[])
 explicit=[explicit] if isinstance(explicit,str) else explicit
 if name in config.get('strictChannels',[]):return explicit
 # Preserve all region words and station suffixes: no fuzzy or substring matching.
 if '_name_index' not in feed:
  index=collections.defaultdict(set)
  for sid,names in feed['names'].items():
   names=[names] if isinstance(names,str) else names
   for key in {norm(sid),*(norm(n) for n in names)}:index[key].add(sid)
  feed['_name_index']=index
 matches=sorted(feed['_name_index'].get(norm(name),[]))
 return list(dict.fromkeys(explicit+(matches if len(matches)==1 else [])))

def load_sources(config,channels,offline=False):
 feeds={};metadata={}
 sources=[s for s in config['sources'] if s['name'] in config['activeSources']]
 def one(source):
  label=source['name']
  try:
   data,meta=fetch(source['url'],label.lower()+'.xml.gz',offline);root=decode(data)
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

def prepare_channel(name,sid,feed,now):
 programmes=[];seen=set();invalid=0;placeholders=0
 raw=feed['programmes'].get(sid,[])
 names=feed['names'].get(sid,[]);names=[names] if isinstance(names,str) else names
 titles={norm(p.findtext('title','')) for p in raw}
 only_station=bool(titles) and (any(titles=={norm(n)} for n in names) or (name=='IBC13' and titles=={'ibctv13'}))
 for p in raw:
  title=p.findtext('title','').strip()
  if name=='Arirang':title=title.removesuffix('"n":"').strip()
  if not title or title.lower() in PLACEHOLDERS or only_station:placeholders+=1;continue
  try:a=parse_time(p.get('start'));b=parse_time(p.get('stop'))
  except ValueError:invalid+=1;continue
  if b<=a:invalid+=1;continue
  if b<now-dt.timedelta(hours=24) or a>now+dt.timedelta(days=8):continue
  # Repeated identical broadcast slots from aggregate feeds are a single programme.
  key=(a,b,title)
  if key in seen:continue
  seen.add(key);q=copy.deepcopy(p);q.set('channel',name);q.set('start',stamp(a));q.set('stop',stamp(b));q.find('title').text=title
  apply_genre_fallback(q,name)
  programmes.append((a,b,q))
 programmes.sort(key=lambda x:(x[0],x[1]))
 return programmes,invalid,placeholders

def build(catalog,out,offline=False,config_path=None):
 now=dt.datetime.now(UTC);out.mkdir(parents=True,exist_ok=True)
 config=json.loads((config_path or BASE.parent/'epg-config.json').read_text(encoding='utf-8'))
 channels=[c['name'].strip() for c in json.loads(catalog.read_text(encoding='utf-8')) if c.get('enabled',True) and c['name'] not in config.get('exclude',[])]
 try:
  additions=json.loads((out/'backup-status.json').read_text(encoding='utf-8')).get('additionalChannels',[])
  channels=list(dict.fromkeys(channels+additions))
 except (FileNotFoundError,ValueError):pass
 feeds,source_meta=load_sources(config,channels,offline)
 root=ET.Element('tv',{'generator-info-name':'PH TV EPG builder'})
 stats=[];rows=[];skipped=collections.Counter();matched_any=0
 for name in channels:
  chosen=None;attempts=[];has_any=False
  for source in config['sources']:
   label=source['name']
   if label not in feeds:continue
   feed=feeds[label]
   for sid in candidate_ids(name,feed,label,config):
    raw=feed['programmes'].get(sid,[]);has_any=has_any or bool(raw)
    programmes,invalid,placeholders=prepare_channel(name,sid,feed,now)
    upcoming=sum(b>now for a,b,p in programmes)
    overlap=sum(b[0]<a[1] for a,b in zip(programmes,programmes[1:]))
    attempts.append({'source':label,'source_id':sid,'raw_entries':len(raw),'upcoming_programmes':upcoming,'overlaps':overlap,'invalid_rejected':invalid,'placeholder_rejected':placeholders})
    if upcoming and not overlap:
     chosen=(label,sid,programmes,invalid,placeholders,upcoming);break
   if chosen:break
  matched_any+=has_any
  if chosen:
   label,sid,programmes,invalid,placeholders,upcoming=chosen
   channel=ET.SubElement(root,'channel',{'id':name});ET.SubElement(channel,'display-name').text=name
   for a,b,p in programmes:root.append(p)
   stats.append({'channel':name,'source':label,'source_id':sid,'programmes':len(programmes),'upcoming':upcoming,'first_utc':programmes[0][0].isoformat(),'last_utc':programmes[-1][1].isoformat(),'overlaps':0,'invalid_rejected':invalid,'placeholder_rejected':placeholders,'independent_broadcast_confirmation':False})
   reason='mapped'
  else:
   label=sid='';upcoming=0;reason='no usable current schedule' if has_any else 'no matching source listings';skipped[reason]+=1
  rows.append({'playlist_tvg_id':name,'source':label,'source_id':sid,'status':reason,'upcoming_programmes':upcoming,'attempts':attempts})
 if len(stats)<config.get('minChannels',100):raise RuntimeError(f'Refusing inadequate guide: {len(stats)} current channels')
 ET.indent(root,space='  ');xml=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 total=sum(c['programmes'] for c in stats)
 for label,meta in source_meta.items():
  selected=[c for c in stats if c['source']==label]
  meta.update(selected_channels=len(selected),selected_programmes=sum(c['programmes'] for c in selected))
 report={'generated_utc':now.isoformat(),'enabled_channels':len(channels),'matched_channels_including_unusable':matched_any,'mapped_channels':len(stats),'unmapped_channels':len(channels)-len(stats),'programmes':total,'total_overlaps':0,'sources':source_meta,'source_counts':{label:{k:meta.get(k,0) for k in ['channel_definitions','programme_entries','selected_channels','selected_programmes']} for label,meta in source_meta.items()},'unmapped_reasons':dict(skipped),'channels':stats,'merge_policy':'Source priority with explicit identities or unique exact names. Try later feeds when earlier listings are stale, placeholders, invalid, or overlapping. One source per channel.','timezone_policy':'Parse explicit UTC offsets; preserve instants; player guide offset 0.','verification_scope':'Timestamp integrity and identity rules checked. Regional feeds and every broadcast are not independently confirmed. Total name matches and usable current schedules are separate counts.'}
 report['genre_policy']='Preserve non-empty programme categories. When missing, add the channel category mapped to an Android TV genre. General/unknown channels remain unclassified; never create programmes to supply a genre.'
 (out/'epg.xml.tmp').write_bytes(xml);(out/'epg.xml.tmp').replace(out/'epg.xml');(out/'epg.xml.gz').write_bytes(gzip.compress(xml,mtime=0))
 for file,value in [('epg-status.json',report),('verification.json',report),('mapping.json',rows)]:
  (out/file).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 with (out/'mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=[k for k in rows[0] if k!='attempts'],extrasaction='ignore');writer.writeheader();writer.writerows(rows)
 (out/'report.txt').write_text(f"Generated {now.isoformat()}\nUsable current schedules {len(stats)}/{len(channels)}; matched including unusable {matched_any}; programmes {total}\n\n"+'\n'.join(f"{r['status']}  {r['playlist_tvg_id']} <- {r['source']}:{r['source_id']}" for r in rows)+'\n',encoding='utf-8')
 print(json.dumps({k:report[k] for k in ['mapped_channels','matched_channels_including_unusable','programmes','total_overlaps']},indent=2),flush=True)
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--catalog',type=Path,default=BASE.parent/'catalog.json');parser.add_argument('--out',type=Path,default=BASE.parent/'site');parser.add_argument('--config',type=Path,default=BASE.parent/'epg-config.json');parser.add_argument('--offline',action='store_true')
 args=parser.parse_args();build(args.catalog,args.out,args.offline,args.config)
