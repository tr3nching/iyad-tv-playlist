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
MAX_BYTES = 8_000_000
PLACEHOLDERS = {'no data', 'no epg', 'no information', 'programming unavailable', 'to be announced'}
# Explicit identities, not fuzzy matching. IDs belong to the Philippines PH2 feed.
MAPPING = {
 'ABC Australia':'ABC.Australia.ph','ANC':'ANC.ph','Animax':'Animax.ph',
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
 'TV5':'TV5.ph','UAAP Varsity':'UAAP.Varsity.Channel.ph','VIVA Cinema':'VIVA.Cinema.ph'
}

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

def build(catalog, out, offline=False):
 now=dt.datetime.now(UTC); out.mkdir(parents=True,exist_ok=True)
 data,meta=fetch(SOURCE,'ph2.xml.gz',offline)
 source=decode(data); by_id=collections.defaultdict(list)
 for p in source.findall('programme'): by_id[p.get('channel')].append(p)
 source_names={c.get('id'):c.findtext('display-name','') for c in source.findall('channel')}
 channels=[c for c in json.loads(catalog.read_text(encoding='utf-8')) if c.get('enabled')]
 root=ET.Element('tv',{'generator-info-name':'iYAD conservative EPG mapper','source-info-url':SOURCE})
 rows=[]; skipped=collections.Counter(); stats=[]; total=0
 for channel in channels:
  name=re.sub(r'\s+', ' ', channel['name']).strip(); sid=MAPPING.get(name); programmes=[]; seen=set(); invalid=0; placeholders=0
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
  future=[p for p in programmes if p[1]>now]
  reason='mapped' if future else ('no current real programmes' if sid else 'no unambiguous regional mapping')
  if future:
   c=ET.SubElement(root,'channel',{'id':name});ET.SubElement(c,'display-name').text=name
   for _,_,p in programmes:root.append(p)
   overlaps=sum(1 for a,b in zip(programmes,programmes[1:]) if b[0]<a[1])
   gaps=sum(1 for a,b in zip(programmes,programmes[1:]) if (b[0]-a[1]).total_seconds()>60)
   stats.append({'channel':name,'source_id':sid,'programmes':len(programmes),'upcoming':len(future),
                 'first_utc':programmes[0][0].isoformat(),'last_utc':programmes[-1][1].isoformat(),
                 'overlaps':overlaps,'gaps_over_60_seconds':gaps,'invalid_rejected':invalid,
                 'placeholder_rejected':placeholders,'independent_broadcast_confirmation':False})
   total+=len(programmes)
  else:skipped[reason]+=1
  rows.append({'playlist_tvg_id':name,'source_id':sid or '', 'status':reason,
               'source_url':SOURCE if sid else '', 'upcoming_programmes':len(future),
               'placeholder_rejected':placeholders, 'region':'Philippines' if sid else ''})
 if not stats or total<100: raise RuntimeError('Refusing to publish empty/inadequate EPG')
 ET.indent(root,space='  '); xml=ET.tostring(root,encoding='utf-8',xml_declaration=True)
 tmp=out/'epg.xml.tmp';tmp.write_bytes(xml);tmp.replace(out/'epg.xml')
 (out/'epg.xml.gz').write_bytes(gzip.compress(xml,mtime=0))
 (out/'mapping.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 with (out/'mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 report={'generated_utc':now.isoformat(),'enabled_channels':len(channels),'mapped_channels':len(stats),
         'unmapped_channels':len(channels)-len(stats),'programmes':total,'source':meta,
         'timezone_policy':'Parse explicit source offsets; convert to UTC without shifting instants. Player offset must be 0.',
         'verification_scope':'Identity matching and timestamp integrity checked. Independent broadcaster checks are recorded separately; not every broadcast is independently confirmed.',
         'total_overlaps':sum(s['overlaps'] for s in stats),
         'unmapped_reasons':dict(skipped),'channels':stats}
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 (out/'epg-status.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k not in ['channels','source']},indent=2))
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--catalog',type=Path,default=BASE.parent/'iyad-channels.json')
 parser.add_argument('--out',type=Path,default=BASE/'output');parser.add_argument('--offline',action='store_true')
 args=parser.parse_args();build(args.catalog,args.out,args.offline)
