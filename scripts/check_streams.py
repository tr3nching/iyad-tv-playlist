"""Probe saved stream candidates; write health metadata, never rewrite the catalog."""
import argparse,concurrent.futures,datetime as dt,hashlib,json,re,time,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urljoin,urlsplit,parse_qsl
import xml.etree.ElementTree as ET

UTC=dt.timezone.utc

def entries(text,kind):
 result=[]
 for block in re.split(r'(?=^#EXTINF:)',text,flags=re.M)[1:]:
  match=re.search(r'\btvg-id="([^"]*)"',block);cid=match[1] if match else ''
  url=next((line.strip() for line in block.splitlines() if re.match(r'^https?://',line)),None)
  if not url:continue
  headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'}
  custom=re.search(r'^#KODIPROP:inputstream\.adaptive\.manifest_headers=(.*)$',block,re.M)
  if custom:
   for key,value in parse_qsl(custom[1].strip()):headers[key]=value
  check_id=hashlib.sha256((kind+'\0'+cid+'\0'+url).encode()).hexdigest()
  result.append({'id':check_id,'channel':cid,'kind':kind,'url':url,'headers':headers})
 return result

def sample(url,headers,deadline,media=False):
 remaining=deadline-time.monotonic()
 if remaining<=0:raise TimeoutError()
 request_headers=dict(headers)
 if media:request_headers['Range']='bytes=0-2047'
 req=urllib.request.Request(url,headers=request_headers)
 try:response=urllib.request.urlopen(req,timeout=min(5,remaining))
 except urllib.error.HTTPError as error:
  if not media or error.code not in (400,416):raise
  req=urllib.request.Request(url,headers=headers);response=urllib.request.urlopen(req,timeout=min(5,remaining))
 with response:
  limit=2048 if media else 1_000_000;parts=[];size=0
  while size<limit:
   if time.monotonic()>deadline:raise TimeoutError()
   chunk=response.read1(min(65536,limit-size))
   if not chunk:break
   parts.append(chunk);size+=len(chunk)
  return b''.join(parts),response.geturl()

def child(node,name):return next((c for c in node if c.tag.split('}')[-1]==name),None)
def children(node,name):return [c for c in node if c.tag.split('}')[-1]==name]
def duration(value):
 match=re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?',value or '')
 return sum(float(n or 0)*factor for n,factor in zip(match.groups(),[3600,60,1])) if match else 0

def dash_media(data,url):
 if b'<!ENTITY' in data:raise ValueError('XML entities')
 root=ET.fromstring(data);periods=children(root,'Period')
 if not periods:raise ValueError('No DASH periods')
 if len(periods)>1:return None
 period=periods[0]
 adaptations=children(period,'AdaptationSet')
 if not adaptations:raise ValueError('No DASH adaptations')
 video=[a for a in adaptations if a.get('contentType')=='video' or (a.get('mimeType') or '').startswith('video')]
 adaptation=(video or adaptations)[0];representations=children(adaptation,'Representation')
 representation=representations[0] if representations else adaptation
 hierarchy=[root,period,adaptation]+([representation] if representation is not adaptation else [])
 base=url;has_base=False
 for node in hierarchy:
  element=child(node,'BaseURL')
  if element is not None and (element.text or '').strip():base=urljoin(base,element.text.strip());has_base=True
 for node in reversed(hierarchy):
  listing=child(node,'SegmentList')
  if listing is not None:
   segments=children(listing,'SegmentURL')
   if segments:return urljoin(base,segments[-2 if len(segments)>1 else -1].get('media'))
 attrs={};timeline=None
 for node in hierarchy:
  template=child(node,'SegmentTemplate')
  if template is not None:
   attrs.update(template.attrib)
   candidate=child(template,'SegmentTimeline')
   if candidate is not None:timeline=candidate
 media=attrs.get('media')
 number=int(attrs.get('startNumber','1'));ticks=int(attrs.get('presentationTimeOffset','0'))
 if timeline is not None:
  cursor=0;index=0
  for segment in children(timeline,'S'):
   start=int(segment.get('t',cursor));length=int(segment.get('d','0'));repeat=int(segment.get('r','0'))
   if repeat<0:return None
   offset=max(0,repeat-1)
   ticks=start+length*offset;number=int(attrs.get('startNumber','1'))+index+offset
   cursor=start+length*(repeat+1);index+=repeat+1
 elif media and attrs.get('duration') and root.get('type')=='dynamic':
  availability=root.get('availabilityStartTime')
  if not availability:return None
  instant=dt.datetime.fromisoformat(availability.replace('Z','+00:00'))
  elapsed=(dt.datetime.now(UTC)-instant).total_seconds()-duration(period.get('start'))
  length=int(attrs['duration']);scale=int(attrs.get('timescale','1'))
  segment=max(0,int(elapsed*scale/length)-2)
  number+=segment;ticks+=segment*length
 if media:
  media=media.replace('$$','\0')
  values={'RepresentationID':representation.get('id',''),'Bandwidth':representation.get('bandwidth',''),'Number':number,'Time':ticks}
  def token(match):
   value=values[match[1]]
   return str(value).zfill(int(match[2])) if match[2] else str(value)
  media=re.sub(r'\$(RepresentationID|Bandwidth|Number|Time)(?:%0(\d+)d)?\$',token,media).replace('\0','$')
  if re.search(r'\$[A-Za-z]',media):return None
  return urljoin(base,media)
 return base if has_base and not base.endswith('/') else None

def probe(row):
 result={key:row[key] for key in ['id','channel','kind']};deadline=time.monotonic()+12
 try:
  data,url=sample(row['url'],row['headers'],deadline)
  for depth in range(4):
   if b'#EXTM3U' in data[:200]:
    text=data.decode('utf-8-sig',errors='replace');lines=text.splitlines()
    links=[line.strip() for line in lines if line.strip() and not line.startswith('#')]
    if not links:raise ValueError('Empty HLS playlist')
    if '#EXT-X-STREAM-INF:' in text:
     data,url=sample(urljoin(url,links[0]),row['headers'],deadline);continue
    target=urljoin(url,links[-2 if len(links)>1 else -1])
    if urlsplit(target).path.endswith('.m3u8'):
     data,url=sample(target,row['headers'],deadline);continue
    content,_=sample(target,row['headers'],deadline,True)
    if not content or b'<html' in content[:200].lower():raise ValueError('Invalid media response')
    result.update(reachable=True,publish=True,status='reachable',stage='media');return result
   if b'<MPD' in data[:3000]:
    target=dash_media(data,url)
    if target:
     content,_=sample(target,row['headers'],deadline,True)
     if not content or b'<html' in content[:200].lower():raise ValueError('Invalid media response')
     result.update(reachable=True,publish=True,status='reachable',stage='media')
    else:result.update(reachable=True,publish=True,status='reachable',stage='manifest_only')
    return result
   if urlsplit(url).path.lower().endswith(('.ts','.mp4','.mkv','.aac','.mp3')) and data and b'<html' not in data[:200].lower():
    result.update(reachable=True,publish=True,status='reachable',stage='media');return result
   raise ValueError('Not a supported stream response')
  raise ValueError('Playlist nesting limit')
 except Exception as error:
  reason='HTTP '+str(error.code) if isinstance(error,urllib.error.HTTPError) else type(error).__name__
  uncertain=(isinstance(error,urllib.error.HTTPError) and error.code in (401,403,429)) or isinstance(error,(TimeoutError,urllib.error.URLError,OSError,ET.ParseError)) and not isinstance(error,urllib.error.HTTPError)
  result.update(reachable=False,status='inconclusive' if uncertain else 'unreachable',publish=True,error=reason)
  return result

def check(directory):
 rows=entries((directory/'playlist-drm.m3u').read_text(encoding='utf-8'),'primary')
 candidate=directory/'backup-candidates.m3u'
 if candidate.exists():rows+=entries(candidate.read_text(encoding='utf-8'),'additional')
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(probe,rows))
 passed=sum(r['reachable'] for r in results)
 report={'checkedAt':dt.datetime.now(UTC).isoformat(),'candidateCount':len(results),'reachableCount':passed,'unreachableCount':sum(r.get('status')=='unreachable' for r in results),'inconclusiveCount':sum(r.get('status')=='inconclusive' for r in results),'hiddenCount':0,'scope':'Network-specific manifest and media-request checks; not full video decoding or DRM license validation. DASH forms whose media location cannot be resolved receive manifest-only checks.','retryPolicy':'Recheck every candidate each refresh for information only. All saved streams remain listed regardless of check result.','channels':results}
 (directory/'stream-health.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:report[k] for k in ['candidateCount','reachableCount','unreachableCount']}),flush=True)
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parent.parent/'site');args=parser.parse_args();check(args.out)
