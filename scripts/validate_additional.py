"""Validate decoded video before publishing additional source entries."""
import argparse, concurrent.futures, datetime as dt, json, os, re, shutil, subprocess
from pathlib import Path
from check_streams import entries

def validate(row, executable, timeout=65):
    result = {'id': row['id'], 'channel': row['channel'], 'validated': False, 'decodedFrames': 0}
    headers = ''.join(f'{key}: {value}\r\n' for key, value in row['headers'].items())
    command = [executable, '-hide_banner', '-loglevel', 'error', '-nostdin', '-rw_timeout', '60000000',
               '-headers', headers, '-i', row['url'], '-map', '0:v:0', '-frames:v', '25', '-an',
               '-progress', 'pipe:1', '-f', 'null', '-']
    try:
        process = subprocess.run(command, capture_output=True, timeout=timeout)
        output = process.stdout.decode('utf-8', errors='replace')
        result['decodedFrames'] = max([int(x) for x in re.findall(r'^frame=(\d+)', output, re.M)], default=0)
        result['validated'] = result['decodedFrames'] >= 25
        if not result['validated']:
            error = process.stderr.decode('utf-8', errors='replace')
            http = re.search(r'\b(?:HTTP error|Server returned)\s+(\d{3})', error)
            result['reason'] = f'HTTP {http[1]}' if http else 'No confirmed decoded video'
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or b'').decode('utf-8', errors='replace')
        result['decodedFrames'] = max([int(x) for x in re.findall(r'^frame=(\d+)', output, re.M)], default=0)
        result['validated'] = result['decodedFrames'] >= 25
        if not result['validated']: result['reason'] = 'No confirmed video within startup allowance'
    except OSError:
        result['reason'] = 'Decoder unavailable'
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('site'))
    parser.add_argument('--ffmpeg', default=os.environ.get('FFMPEG') or shutil.which('ffmpeg'))
    args = parser.parse_args()
    if not args.ffmpeg: raise RuntimeError('FFmpeg is required for decoded playback validation')
    candidates = entries((args.out/'backup-candidates.m3u').read_text(encoding='utf-8-sig'), 'additional')
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda row: validate(row, args.ffmpeg), candidates))
    report = {'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'candidateCount': len(results),
              'validatedCount': sum(row['validated'] for row in results),
              'scope': 'At least 25 decoded video frames per exact stream identity. Up to 65 seconds startup. Network-specific snapshot, not sustained playback or every TV app.',
              'channels': results}
    temporary = args.out/'backup-validation.json.tmp'
    temporary.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    temporary.replace(args.out/'backup-validation.json')
    print(json.dumps({key: report[key] for key in ['candidateCount','validatedCount']}))

if __name__ == '__main__': main()
