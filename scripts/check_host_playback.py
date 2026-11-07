"""Health report from the publishing host; never changes playlist visibility."""
import argparse, concurrent.futures, datetime as dt, json, re, subprocess, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urljoin
from check_streams import entries, dash_media

class CheckError(Exception):
 def __init__(self,stage,reason,http=None):self.stage,self.reason,self.http=stage,reason,http

def fetch(url,headers,stage,limit):
 try:
  req=urllib.request.Request(url,headers=headers)
  with urllib.request.urlopen(req,timeout=15) as response:
   status=response.status;data=response.read(limit);return data,response.geturl(),status
 except urllib.error.HTTPError as error:raise CheckError(stage,'HTTP error',error.code)
 except Exception as error:raise CheckError(stage,type(error).__name__)

def first_link(text,master):
 lines=text.splitlines()
 if master:
  for index,line in enumerate(lines):
   if line.strip().startswith('#EXT-X-STREAM-INF:'):
    for candidate in lines[index+1:]:
     if candidate.strip() and not candidate.lstrip().startswith('#'):return candidate.strip()
  return None
 return next((line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#')),None)

def check(row,ffprobe):
 result={key:row[key] for key in ('id','channel','kind')};stage='manifest'
 try:
  data,url,_=fetch(row['url'],row['headers'],stage,1_000_000)
  if b'#EXTM3U' in data[:200]:
   for depth in range(5):
    text=data.decode('utf-8-sig',errors='replace');master='#EXT-X-STREAM-INF:' in text
    target=first_link(text,master)
    if not target:raise CheckError(stage,'No variant or media segment')
    if not master:break
    stage='variant';data,url,_=fetch(urljoin(url,target),row['headers'],stage,1_000_000)
    if b'#EXTM3U' not in data[:200]:raise CheckError(stage,'Invalid HLS playlist')
   else:raise CheckError('variant','Too many nested variants')
   stage='segment';data,_,_=fetch(urljoin(url,target),row['headers'],stage,4096)
   if not data or b'<html' in data[:200].lower():raise CheckError(stage,'Empty or invalid segment')
  elif b'<MPD' in data[:3000]:
   stage='segment';target=dash_media(data,url)
   if not target:raise CheckError(stage,'DASH segment could not be resolved')
   data,_,_=fetch(target,row['headers'],stage,4096)
   if not data or b'<html' in data[:200].lower():raise CheckError(stage,'Empty or invalid segment')
  else:raise CheckError('manifest','Unsupported or invalid manifest')
  stage='ffprobe';headers=''.join(f'{k}: {v}\r\n' for k,v in row['headers'].items())
  cmd=[ffprobe,'-v','error','-rw_timeout','30000000','-headers',headers]
  if row.get('key'):cmd+=['-cenc_decryption_key',row['key']]
  cmd+=['-show_entries','stream=codec_type','-of','json',row['url']]
  try:p=subprocess.run(cmd,capture_output=True,timeout=40)
  except subprocess.TimeoutExpired:raise CheckError(stage,'Timeout')
  except OSError:raise CheckError(stage,'ffprobe unavailable')
  stderr=p.stderr.decode(errors='replace');match=re.search(r'(?:HTTP error|Server returned)\s+(\d{3})',stderr,re.I)
  if p.returncode:raise CheckError(stage,'Could not inspect streams',int(match.group(1)) if match else None)
  try:metadata=json.loads(p.stdout.decode('utf-8'))
  except (ValueError,UnicodeDecodeError):raise CheckError(stage,'Invalid ffprobe output')
  types=sorted({s.get('codec_type') for s in metadata.get('streams',[]) if s.get('codec_type') in ('audio','video')})
  if not types:raise CheckError(stage,'No audio or video stream')
  result.update(status='PLAYABLE',stage='complete',httpStatus=None,streams=types)
 except CheckError as error:result.update(status='FAIL',stage=error.stage,httpStatus=error.http,reason=error.reason)
 except Exception as error:result.update(status='FAIL',stage=stage,httpStatus=None,reason=type(error).__name__)
 return result

def playlist_rows(path):
 text=path.read_text(encoding='utf-8-sig');rows=[]
 for block in re.split(r'(?=^#EXTINF:)',text,flags=re.M)[1:]:
  m=re.search(r'\btvg-id="([^"]*)"',block)
  if not m or m.group(1).startswith('category:'):continue
  kind='additional' if m.group(1).startswith('additional:') else 'primary'
  parsed=entries(block,kind)
  if not parsed:continue
  row=parsed[0];key=re.search(r'license_key=([a-fA-F0-9]{32}):([a-fA-F0-9]{32})',block)
  row['key']=key.group(2) if key else None;rows.append(row)
 return rows

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('site'));parser.add_argument('--ffprobe',default='ffprobe');parser.add_argument('--workers',type=int,default=16);args=parser.parse_args()
 rows=playlist_rows(args.out/'playlist.m3u')
 with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.workers,24))) as pool:results=list(pool.map(lambda row:check(row,args.ffprobe),rows))
 report={'checkedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'environment':'publishing host','scope':'Request the manifest, a media segment and ffprobe audio/video metadata. Does not confirm successful decoding or playback on your TV.','candidateCount':len(results),'playableCount':sum(r['status']=='PLAYABLE' for r in results),'channels':results}
 (args.out/'host-playback-health.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:report[k] for k in ('candidateCount','playableCount','checkedAt')}))
if __name__=='__main__':main()
