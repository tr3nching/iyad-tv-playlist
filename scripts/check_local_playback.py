"""Local playback checks for a rotating batch of saved channels."""
import argparse, concurrent.futures, datetime as dt, json, re, subprocess
from pathlib import Path
from check_streams import entries

LIMIT = 3

def evaluate(previous, outcome):
    """Only explicit missing-media responses count; uncertain results keep state."""
    state = dict(previous)
    if outcome == 'played':
        state.update(failures=0, published=True)
    elif outcome == 'confirmed_failure':
        state['failures'] = state.get('failures', 0) + 1
        if state['failures'] >= LIMIT: state['published'] = False
    return state

def candidates(path, kind):
    text = path.read_text(encoding='utf-8-sig')
    result = entries(text, kind)
    blocks = re.split(r'(?=^#EXTINF:)', text, flags=re.M)[1:]
    drm = {}
    for block in blocks:
        name = re.search(r'\btvg-id="([^"]*)"',block)
        key = re.search(r'license_key=([a-fA-F0-9]{32}):([a-fA-F0-9]{32})',block)
        if name and key: drm[name.group(1)] = key.group(2)
    for row in result: row['key'] = drm.get(row['channel'])
    return result

def probe(row, executable):
    headers = ''.join(f'{key}: {value}\r\n' for key,value in row['headers'].items())
    command = [executable,'-hide_banner','-loglevel','error','-nostdin','-rw_timeout','40000000','-headers',headers]
    if row.get('key'): command += ['-cenc_decryption_key',row['key']]
    command += ['-i',row['url'],'-map','0:v:0','-frames:v','25','-an','-progress','pipe:1','-f','null','-']
    try:
        process = subprocess.run(command,capture_output=True,timeout=50)
        frames = max([int(n) for n in re.findall(r'^frame=(\d+)',process.stdout.decode(errors='replace'),re.M)],default=0)
        if frames >= 25: return 'played'
        http = re.search(r'(?:HTTP error|Server returned)\s+(\d{3})',process.stderr.decode(errors='replace'))
        return 'confirmed_failure' if http and http.group(1) in ('404','410') else 'inconclusive'
    except (subprocess.TimeoutExpired,OSError): return 'inconclusive'

def run(out, executable, batch_size):
    state_path=out/'local-playback-state.json'
    try: state=json.loads(state_path.read_text(encoding='utf-8'))
    except FileNotFoundError: state={'version':1,'origin':'local','cursor':0,'channels':[]}
    if state.get('origin') != 'local' or state.get('version') != 1: raise ValueError('Invalid local playback state')
    previous={row['id']:row for row in state.get('channels',[])}
    primary=candidates(out/'playlist-drm.m3u','primary')
    backup=candidates(out/'backup-candidates.m3u','additional')
    rows=primary+backup
    visible=set(row['channel'] for row in entries((out/'playlist.m3u').read_text(encoding='utf-8-sig'),'published'))
    records={}
    for row in rows:
        prior=previous.get(row['id'])
        # A new exact link starts fresh. Existing visible sources stay visible on migration.
        records[row['id']]=prior or {'id':row['id'],'channel':row['channel'],'kind':row['kind'],'failures':0,'published':row['kind']=='primary' or row['channel'] in visible}
    start=int(state.get('cursor',0)) % max(len(rows),1)
    selected=[rows[(start+i)%len(rows)] for i in range(min(batch_size,len(rows)))] if rows else []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: outcomes=list(pool.map(lambda row:probe(row,executable),selected))
    for row,outcome in zip(selected,outcomes):
        updated=evaluate(records[row['id']],outcome)
        updated.update(lastResult=outcome,lastCheckedAt=dt.datetime.now(dt.timezone.utc).isoformat())
        records[row['id']]=updated
    result={'version':1,'origin':'local','updatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'cursor':(start+len(selected))%max(len(rows),1),'batchSize':len(selected),'channels':list(records.values())}
    temp=state_path.with_suffix('.json.tmp');temp.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');temp.replace(state_path)
    print(json.dumps({'checked':len(selected),'played':outcomes.count('played'),'confirmed_failures':outcomes.count('confirmed_failure'),'inconclusive':outcomes.count('inconclusive')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('site'));parser.add_argument('--ffmpeg',required=True);parser.add_argument('--batch-size',type=int,default=48);args=parser.parse_args();run(args.out,args.ffmpeg,max(1,args.batch_size))
