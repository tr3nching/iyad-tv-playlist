"""Compare HEAD responses without printing stream URLs or credentials."""
import json,os,pathlib,re,subprocess,urllib.parse
text=(pathlib.Path(__file__).resolve().parent.parent/'bootstrap'/'backup-candidates.m3u').read_text(encoding='utf-8-sig')
block=next(block for block in re.split(r'(?=^#EXTINF:)',text,flags=re.M) if re.search(r'tvg-name="STAR TV PHILIPPINES(?: \*)?"',block,re.I))
url=next(line for line in block.splitlines() if line.startswith('http'));parts=urllib.parse.urlsplit(url);origin=f'{parts.scheme}://{parts.netloc}'
ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
for label,extra in [('no_user_agent',['-A','']),('mozilla',['-A','Mozilla/5.0']),('browser_headers',['-A',ua,'-H','Accept: */*','-H','Origin: '+origin,'-H','Referer: '+origin+'/'])]:
 try:
  p=subprocess.run(['curl','-sS','-I','--max-time','15','-o',os.devnull,'-w','%{http_code}',*extra,url],capture_output=True,text=True,timeout=20)
  print(json.dumps({'profile':label,'status':p.stdout or None,'curl_exit':p.returncode}))
 except subprocess.TimeoutExpired:print(json.dumps({'profile':label,'status':None,'error':'timeout'}))
