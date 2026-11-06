"""Build a conservative XMLTV guide for the iYAD channel-name tvg-id values.
Python 3.10+, standard library only. No streams, credentials, or DRM are fetched.
"""
from __future__ import annotations
import argparse, collections, copy, csv, datetime as dt, gzip, hashlib, io, json, re, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent
UTC = dt.timezone.utc
SOURCE = 'https://m3u-edit.com/epg-source.php?file=PH2.xml.gz'
SOURCES = {'PH2':SOURCE,'PH1':'https://m3u-edit.com/epg-source.php?file=PH1.xml.gz'}
MAX_BYTES = 8_000_000
PLACEHOLDERS = {'no data', 'no epg', 'no information', 'programming unavailable', 'to be announced'}
# Explicit identities, not fuzzy matching. IDs belong to the Philippines PH2 feed.
MAPPING = {
 'ABC Australia':'ABC.Australia.ph','Al Jazeera':'Al.Jazeera.ph','CNN HD':'CNN.HD.ph','ANC':'ANC.ph','Animax':'Animax.ph',
 'Arirang':'Arirang.ph','AXN':'AXN.ph','BBC Earth':'BBC.Earth.HD.ph',
 'BBC Lifestyle':'BBC.Lifestyle.ph','BBC News':'BBC.News.ph',
 'Bilyonaryo':'Bilyonaryo.News.Channel.ph','Blast Movies':'BLASTMOVIES.ph',
 'CCTV4':'CCTV.4.ph','Channel News Asia':'CNA.ph','CinemaOne':'Cinema.One.ph',
 'CRIME INVESTIGATION':'Crime.Investigation.ph','DepEd TV':'DepEd.TV.ph',
 'Dreamworks HD':'DreamWorks.HD.ph','Fashion TV HD':'Fashion.TV.HD.ph',
 'FRANCE 24':'France.24.ph','Global Trekker':'Global.Trekker.ph',
 'GMA':'GMA.ph','GTV':'GTV.ph','History HD':'History.HD.ph','Hits HD':'HITS.HD.ph',
 'Hits Movies':'HITS.MOVIES.ph','Hits Now':'HITS.NOW.ph','IBC13':'IBC.13.ph',
 'Jeepney TV':'Jeepney.TV.ph','Kapamilya Channel':'Kapamilya.Channel.ph',
 'Kapamilya Channel HD':'Kapamilya.Channel.ph','Knowledge Channel':'Knowledge.Channel.ph',
 'Lifetime':'Lifetime.SD.ph','Lotus Macau':'Lotus.Macau.ph','Metro Channel':'Metro.Channel.ph',
 'Moonbug Kids':'Moonbug.Kids.ph','MYX':'MYX.ph','NBA TV Philippines':'NBA.TV.Philippines.ph',
 'NCAA NXT':'NCAA.NXT.ph','Net25':'Net.25.ph','NHK World Japan':'NHK.World.Japan.ph',
 'Nickelodeon':'Nickelodeon.SD.ph','One News HD':'One.News.ph','One PH':'One.PH.ph',
 'One Sports':'One.Sports.HD.ph','PBA Rush':'PBA.Rush.ph','Pinoy Box Office':'PBO.ph',
 'Premier Sports':'Premier.Sports.HD.ph','Peoples Television':'PTV.4.ph',
 'Rock Action':'Rock.Action.ph','RPTV':'RPTV.HD.ph','SOLARFLIX':'Solar.Flix.ph',
 'SPOTV':'SPOTV.HD.ph','Studio Universal':'STUDIOUNIVERSAL.ph',
 'Tagalized Movie Channel':'Tagalized.Movie.Channel.ph','Tap Action Flix':'TAPACTIONFLIX.ph',
 'TAP Edge':'TAPEDGE.ph','Tap Movies':'TAP.Movies.HD.ph','TapSILOG':'Tapsilog.ph',
 'TAP Sports':'Tap.Sports.ph','TAP TV':'TAPTV.ph','TV Maria':'TV.Maria.ph',
 'TV5':'TV5.ph','TVN':'tvN.Premium.HD.ph','TVN Movies':'tvN.Movies.Pinoy.ph',
 'UAAP Varsity':'UAAP.Varsity.Channel.ph','VIVA Cinema':'VIVA.Cinema.ph'
}
PH1_MAPPING = {
 'A2Z':'A2Z.ph','ANC':['ANC.HD.ph','ANC.ph'],'Animal Planet':['ANIMAL.PLANET.HD.ph','ANIMAL.PLANET.ph'],
 'Animax':'ANIMAX.ph','Aniplus':'ANIPLUS.SD.ph','Asian Food Network':['ASIAN.FOOD.NETWORK.HD.ph','ASIAN.FOOD.NETWORK.ph'],
 'AXN':['AXN.HD.ph','AXN.ph'],'Bloomberg':'BLOOMBERG.ph','BOOMERANG':'BOOMERANG.ph',
 'Cartoon Network':['CARTOON.NETWORK.HD.ph','CARTOON.NETWORK.ph'],
 'Celestial Classic Movies':'CELESTIAL.CLASSIC.MOVIES.ph','Channel News Asia':'CHANNEL.NEWS.ASIA.ph',
 'CinemaOne':'CINEMA.ONE.ph','Cinemax':['CINEMAX.HD.ph','CINEMAX.ph'],'CineMo!':'CINEMO!.ph',
 'CRIME INVESTIGATION':['CRIME.&.INVESTIGATION.HD.ph','CRIME.&.INVESTIGATION.ph'],
 'Discovery Asia':'DISCOVERY.ASIA.ph','Discovery Channel':['DISCOVERY.CHANNEL.HD.ph','DISCOVERY.CHANNEL.ph'],
 'Dreamworks HD':'DREAMWORKS.HD.ph','DZMM Teleradyo':'DZMM.TELERADYO.ph','Euro News.':'EURONEWS.ph',
 'Fashion TV HD':'FASHION.TV.HD.ph','Food Network HD':'FOOD.NETWORK.HD.ph','Global Trekker':'GLOBAL.TREKKER.HD.ph',
 'HBO':['HBO.HD.ph','HBO.ph'],'HBO Family':['HBO.FAMILY.HD.ph','HBO.FAMILY.ph'],
 'HBO Signature':['HBO.SIGNATURE.HD.ph','HBO.SIGNATURE.ph'],'HGTV HD':'HGTV.HD.ph',
 'History HD':'HISTORY.HD.ph','Jeepney TV':'JEEPNEY.TV.ph','Kapamilya Channel':['KAPAMILYA.CHANNEL.HD.ph','KAPAMILYA.CHANNEL.ph'],
 'Kapamilya Channel HD':'KAPAMILYA.CHANNEL.HD.ph','KBS World':'KBS.WORLD.ph','Kix HD':'KIX.HD.ph',
 'Knowledge Channel':'KNOWLEDGE.CHANNEL.ph','Lifetime':['LIFETIME..HD.ph','LIFETIME.ph'],
 'Metro Channel':['METRO.CHANNEL.HD.ph','METRO.CHANNEL.SD.ph'],'MTV':'MTV.ASIA.ph','MYX':'MYX.ph',
 'National Geographic':['NATIONAL.GEOGRAPHIC.HD.ph','NATIONAL.GEOGRAPHIC.ph'],
 'NHK World Japan':'NHK.WORLD.JAPAN.ph','Nickjr':'NICK.JR..ph','Nickelodeon':'NICKELODEON.ph',
 'One Sports':'ONE.SPORTS.ph','Outdoor Channel':['OUTDOOR.CHANNEL.HD.ph','OUTDOOR.CHANNEL.ph'],
 'Pinoy Box Office':'PBO.ph','Premier Sports':['PREMIER.SPORTS.HD.ph','PREMIER.SPORTS.ph'],
 'RPTV':'RPTV.ph','SOLARSPORTS':'SOLAR.SPORTS.ph','SOLARFLIX':'SOLARFLIX.ph','SPOTV':['SPOTV.HD.ph','SPOTV.ph'],
 'TAP Edge':'TAP.EDGE.ph','Tap Movies':['TAP.MOVIES.HD.ph','TAP.MOVIES.ph'],'TAP Sports':'TAP.SPORTS.HD.ph',
 'TAP TV':'TAP.TV.ph','Thrill':'THRILL.ph','TLC':['TLC.HD.ph','TLC.ph'],
 'Tagalized Movie Channel':'TMC.(TAGALIZED.MOVIE.CHANNEL).ph','Travel Channel':['TRAVEL.CHANNEL.HD.ph','TRAVEL.CHANNEL.ph'],
 'TV5 Monde':'TV.5.MONDE.ph','TV5':'TV5.ph','Tap Action Flix':['TapAction.Flix.HD.ph','TapAction.Flix.ph'],
 'Warner TV':['WARNER.TV.HD.ph','WARNER.TV.ph']}

def ids(mapping,name):
 value=mapping.get(name,[])
 return [value] if isinstance(value,str) else value

def parse_time(s):
 if not re.fullmatch(r'\d{14} [+-]\d{4}', s or ''): raise ValueError('Missing explicit XMLTV UTC offset')
 return dt.datetime.strptime(s, '%Y%m%d%H%M%S %z').astimezone(UTC)

def stamp(t): return t.astimezone(UTC).strftime('%Y%m%d%H%M%S +0000')
def norm(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def fetch(url, cache, offline=False):
 path=BASE/'cache'/cache; path.parent.mkdir(exist_ok=True)
 if offline: return path.read_bytes(), {'url':url,'cached':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 req=urllib.request.Request(url,headers={'User-Agent':'iyad-playlist-epg/1.0','Accept-Encoding':'identity'})
 with urllib.request.urlopen(req, timeout=30) as response:
  data=response.read(MAX_BYTES+1)
  if len(data)>MAX_BYTES: raise ValueError('Source exceeds download limit')
  meta={'url':url,'cached':False,'retrieved_utc':dt.datetime.now(UTC).isoformat(),
        'last_modified':response.headers.get('Last-Modified'),'sha256':hashlib.sha256(data).hexdigest()}
 path.write_bytes(data)
 return data,meta

def decode(data):
 if data[:2]==b'\x1f\x8b':
  with gzip.GzipFile(fileobj=io.BytesIO(data)) as archive:data=archive.read(40_000_001)
 if len(data)>40_000_000: raise ValueError('Source expands past size limit')
 if b'<!ENTITY' in data: raise ValueError('XML entities prohibited')
 return ET.fromstring(data)

def load_sources(offline=False):
 feeds={}; metadata={}
 for label,url in SOURCES.items():
  try:
   data,meta=fetch(url,label.lower()+'.xml.gz',offline); source=decode(data)
   by_id=collections.defaultdict(list)
   for p in source.findall('programme'):by_id[p.get('channel')].append(p)
   names={c.get('id'):c.findtext('display-name','') for c in source.findall('channel')}
   valid=[]; offsets=collections.Counter()
   for p in source.findall('programme'):
    try:
     a=parse_time(p.get('start'));b=parse_time(p.get('stop'))
     if b>a:valid.append((a,b));offsets[p.get('start')[-5:]]+=1
    except ValueError:pass
   meta.update({'channel_definitions':len(names),'programme_entries':len(source.findall('programme')),
    'valid_timestamp_entries':len(valid),'encoded_offsets':dict(offsets),
    'first_utc':min((a.isoformat() for a,b in valid),default=None),
    'last_utc':max((b.isoformat() for a,b in valid),default=None)})
   feeds[label]={'programmes':by_id,'names':names};metadata[label]=meta
  except Exception as error:
   feeds[label]={'programmes':{},'names':{}}
   metadata[label]={'url':url,'error':str(error),'channel_definitions':0,'programme_entries':0}
 return feeds,metadata

def check_source_alignment(feeds):
 """Compare the nearest same-title occurrence within 12h, never alter an instant.
 Repeated titles are deduplicated by channel/title/start. Need evidence from >=2 channels.
 """
 histogram=collections.Counter();exact_channels=set();examples=[];seen=set()
 ph1,ph2=feeds['PH1'],feeds['PH2']
 for name in sorted(set(PH1_MAPPING)&set(MAPPING)):
  second=collections.defaultdict(list)
  for p in ph2['programmes'].get(MAPPING[name],[]):
   title=norm(p.findtext('title',''))
   if not title or title in {norm(x) for x in PLACEHOLDERS}:continue
   try:second[title].append(parse_time(p.get('start')))
   except ValueError:pass
  for cid in ids(PH1_MAPPING,name):
   for p in ph1['programmes'].get(cid,[]):
    title=norm(p.findtext('title',''))
    if (not title or title==norm(ph1['names'].get(cid,'')) or
        title==norm(ph2['names'].get(MAPPING[name],'')) or not second[title] or len(second[title])>4):continue
    try:start=parse_time(p.get('start'))
    except ValueError:continue
    key=(name,title,start)
    if key in seen:continue
    seen.add(key);match=min(second[title],key=lambda x:abs((start-x).total_seconds()))
    delta=int((start-match).total_seconds())
    if abs(delta)>43200:continue
    histogram[delta]+=1
    if delta==0:exact_channels.add(name)
    if len(examples)<12:examples.append({'channel':name,'title':p.findtext('title'),
      'ph1_utc':start.isoformat(),'ph2_utc':match.isoformat(),'delta_seconds':delta})
 if not any(ph1['programmes'].values()):state='no_programmes';eligible=False
 elif not histogram:state='insufficient_comparable_programmes';eligible=False
 else:
  top,count=histogram.most_common(1)[0]
  # A coherent shifted minority must not be hidden by a larger aligned channel.
  substantial_shift=any(delta!=0 and n>=3 and n>=sum(histogram.values())*0.10
                        for delta,n in histogram.items())
  eligible=not substantial_shift and histogram[0]>=3 and len(exact_channels)>=2
  state='nonzero_shift_requires_review' if substantial_shift else ('aligned_to_PH2_examples' if eligible else 'insufficient_alignment_evidence')
 return {'PH1_eligible':eligible,'state':state,'delta_histogram_seconds':dict(histogram),
  'exact_match_channels':sorted(exact_channels),'examples':examples,
  'correction_applied_seconds':0,'scope':'Cross-feed comparison only; no independent PH1 confirmation without programme timestamps.'}

def build(catalog, out, offline=False):
 now=dt.datetime.now(UTC); out.mkdir(parents=True,exist_ok=True)
 feeds,source_meta=load_sources(offline);alignment=check_source_alignment(feeds)
 channels=[c for c in json.loads(catalog.read_text(encoding='utf-8')) if c.get('enabled')]
 root=ET.Element('tv',{'generator-info-name':'iYAD conservative EPG mapper','source-info-url':SOURCE})
 rows=[]; skipped=collections.Counter(); stats=[]; total=0
 for channel in channels:
  name=re.sub(r'\s+', ' ', channel['name']).strip(); programmes=[]; invalid=0;placeholders=0;sid=None;selected=None
  candidates=[('PH2',cid) for cid in ids(MAPPING,name)]+[('PH1',cid) for cid in ids(PH1_MAPPING,name)]
  attempts=[]
  for label,candidate in candidates:
   allowed=label=='PH2' or alignment['PH1_eligible']
   candidate_programmes,candidate_invalid,candidate_placeholders=prepare_channel(
     name,candidate,feeds[label],now)
   upcoming=sum(p[1]>now for p in candidate_programmes)
   overlaps=sum(1 for a,b in zip(candidate_programmes,candidate_programmes[1:]) if b[0]<a[1])
   attempts.append({'source':label,'source_id':candidate,'upcoming_programmes':upcoming,
                    'eligible':allowed,'placeholder_rejected':candidate_placeholders,'overlaps':overlaps})
   if allowed and upcoming and overlaps==0:
    programmes=candidate_programmes;sid=candidate;selected=label
    invalid=candidate_invalid;placeholders=candidate_placeholders;break
  future=[p for p in programmes if p[1]>now]
  reason='mapped' if future else ('no current eligible real programmes' if candidates else 'no unambiguous regional mapping')
  if future:
   c=ET.SubElement(root,'channel',{'id':name});ET.SubElement(c,'display-name').text=name
   for _,_,p in programmes:root.append(p)
   overlaps=sum(1 for a,b in zip(programmes,programmes[1:]) if b[0]<a[1])
   gaps=sum(1 for a,b in zip(programmes,programmes[1:]) if (b[0]-a[1]).total_seconds()>60)
   stats.append({'channel':name,'source':selected,'source_id':sid,'programmes':len(programmes),'upcoming':len(future),
                 'first_utc':programmes[0][0].isoformat(),'last_utc':programmes[-1][1].isoformat(),
                 'overlaps':overlaps,'gaps_over_60_seconds':gaps,'invalid_rejected':invalid,
                 'placeholder_rejected':placeholders,'independent_broadcast_confirmation':False})
   total+=len(programmes)
  else:skipped[reason]+=1
  rows.append({'playlist_tvg_id':name,'source':selected or '', 'source_id':sid or '', 'status':reason,
               'source_url':SOURCES[selected] if selected else '', 'upcoming_programmes':len(future),
               'placeholder_rejected':placeholders,'candidate_ids':' | '.join(f'{a}:{b}' for a,b in candidates),
               'region':'Philippines' if candidates else '', 'attempts':attempts})
 if not stats or total<100: raise RuntimeError('Refusing to publish empty/inadequate EPG')
 ET.indent(root,space='  '); xml=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 tmp=out/'epg.xml.tmp';tmp.write_bytes(xml);tmp.replace(out/'epg.xml')
 (out/'epg.xml.gz').write_bytes(gzip.compress(xml,mtime=0))
 (out/'mapping.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 with (out/'mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=[k for k in rows[0] if k!='attempts'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 for label,meta in source_meta.items():
  chosen=[s for s in stats if s['source']==label]
  meta.update({'selected_channels':len(chosen),'selected_programmes':sum(x['programmes'] for x in chosen),
               'eligible':label=='PH2' or alignment['PH1_eligible']})
 report={'generated_utc':now.isoformat(),'enabled_channels':len(channels),'mapped_channels':len(stats),
         'unmapped_channels':len(channels)-len(stats),'programmes':total,'source':source_meta['PH2'],
         'sources':source_meta,'cross_source_alignment':alignment,
         'source_counts':{label:{k:meta.get(k,0) for k in ['channel_definitions','programme_entries','selected_channels','selected_programmes']} for label,meta in source_meta.items()},
         'merge_policy':'Prefer PH2 current real schedule; otherwise eligible PH1 HD then SD. Select one source per channel; never interleave schedules or shift timestamps.',
         'timezone_policy':'Parse explicit source offsets; convert to UTC without shifting instants. Player offset must be 0.',
         'verification_scope':'Identity matching and timestamp integrity checked. Independent broadcaster checks are recorded separately; not every broadcast is independently confirmed.',
         'total_overlaps':sum(s['overlaps'] for s in stats),
         'unmapped_reasons':dict(skipped),'channels':stats}
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 (out/'epg-status.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k not in ['channels','source','sources']},indent=2))
 return report

def prepare_channel(name,sid,feed,now):
 programmes=[];seen=set();invalid=0;placeholders=0
 by_id=feed['programmes'];source_names=feed['names']
 titles={norm(p.findtext('title','')) for p in by_id.get(sid,[])}
 only_station_name=bool(titles) and (titles=={norm(source_names.get(sid,''))} or
                                  (name=='IBC13' and titles=={'ibctv13'}))
 for p in by_id.get(sid,[]):
   title=p.findtext('title','').strip()
   if name=='Arirang':title=title.removesuffix('"n":"').strip()
   if not title or title.lower() in PLACEHOLDERS or only_station_name:
    placeholders+=1; continue
   try: start=parse_time(p.get('start')); stop=parse_time(p.get('stop'))
   except ValueError: invalid+=1; continue
   if stop<=start: invalid+=1; continue
   if stop<now-dt.timedelta(hours=24) or start>now+dt.timedelta(days=8):continue
   key=(start,stop,title)
   if key in seen:continue
   seen.add(key); q=copy.deepcopy(p);q.set('channel',name);q.set('start',stamp(start));q.set('stop',stamp(stop))
   q.find('title').text=title
   programmes.append((start,stop,q))
 programmes.sort(key=lambda x:(x[0],x[1]))
 return programmes,invalid,placeholders

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--catalog',type=Path,default=BASE.parent/'iyad-channels.json')
 parser.add_argument('--out',type=Path,default=BASE/'output');parser.add_argument('--offline',action='store_true')
 args=parser.parse_args();build(args.catalog,args.out,args.offline)
