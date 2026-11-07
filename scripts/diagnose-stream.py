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

# Diagnostic only: report errors without exposing request URLs or keys.
from check_local_playback import candidates
primary=candidates(root/'playlist-drm.m3u','primary')
for row in primary:
 if row['channel'] not in ('TV5','One PH'):continue
 headers=''.join(f'{key}: {value}\r\n' for key,value in row['headers'].items())
 command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-rw_timeout','25000000','-headers',headers]
 if row.get('key'):command+=['-cenc_decryption_key',row['key']]
 command+=['-i',row['url'],'-map','0:v:0','-frames:v','25','-an','-progress','pipe:1','-f','null','-']
 try:
  p=subprocess.run(command,capture_output=True,timeout=40);err=p.stderr.decode(errors='replace');out=p.stdout.decode(errors='replace');import re
  frames=max([int(n) for n in re.findall(r'^frame=(\d+)',out,re.M)],default=0)
  statuses=re.findall(r'(?:HTTP error|Server returned)\s+(\d{3})',err,re.I)
  classes=[phrase for phrase in ('Invalid data found','No such file or directory','Error opening input','Connection refused','timed out','Invalid argument','Error when loading first segment') if phrase.lower() in err.lower()]
  print(json.dumps({'channel':row['channel'],'method':'decode','frames':frames,'http':statuses,'errors':classes,'exit':p.returncode}),flush=True)
 except subprocess.TimeoutExpired:print(json.dumps({'channel':row['channel'],'method':'decode','error':'timeout'}),flush=True)
