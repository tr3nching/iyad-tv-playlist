"""Compare stream HEAD responses without printing stream URLs or keys."""
import concurrent.futures,json,os,pathlib,subprocess
from check_streams import entries
root=pathlib.Path(__file__).resolve().parent.parent/'bootstrap'
rows=entries((root/'playlist-drm.m3u').read_text(encoding='utf-8-sig'),'primary')+entries((root/'backup-candidates.m3u').read_text(encoding='utf-8-sig'),'additional')
want={'TV5':'TV5','Jeepney TV':'Jeepney TV','One PH':'One PH','additional:startvphilippines:8fbad275b125':'Star TV additional','additional:cinemo:fb72504d47ac':'CineMo additional'}
tasks=[]
for row in rows:
 if row['channel'] not in want:continue
 h=row['headers'];profiles=[('no_user_agent',['-A','']),('mozilla',['-A','Mozilla/5.0']),('browser_headers',['-A',h['User-Agent'],'-H','Accept: */*','-H','Origin: '+h['Origin'],'-H','Referer: '+h['Referer']])]
 for label,extra in profiles:
  tasks.append((want[row['channel']],row['url'],label,extra,'HEAD'))
  if row['channel'] in ('TV5','One PH'):tasks.append((want[row['channel']],row['url'],label,extra,'GET'))
def check(task):
 name,url,label,extra,method=task
 try:
  p=subprocess.run(['curl','-sS',*(['-I'] if method=='HEAD' else ['-L','--max-redirs','5','--range','0-2047']),'--max-time','12','-o',os.devnull,'-w','%{http_code}',*extra,url],capture_output=True,text=True,timeout=17)
  return {'channel':name,'method':method,'profile':label,'status':p.stdout or None,'curl_exit':p.returncode}
 except subprocess.TimeoutExpired:return {'channel':name,'method':method,'profile':label,'status':None,'error':'timeout'}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 for result in pool.map(check,tasks):print(json.dumps(result),flush=True)

# These are diagnostic-only checks; they never affect the local visibility counters.
from check_local_playback import candidates,probe
primary=candidates(root/'playlist-drm.m3u','primary')
for row in primary:
 if row['channel'] in ('TV5','One PH'):
  print(json.dumps({'channel':row['channel'],'method':'decode','profile':'browser_headers','result':probe(row,'ffmpeg')}),flush=True)
