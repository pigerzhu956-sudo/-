"""Technical checks only; this cannot claim human audiovisual review."""
import argparse
import json
import math
import subprocess
from pathlib import Path
from fractions import Fraction


def verify(video, manifest, ffprobe='ffprobe'):
    m=json.loads(Path(manifest).read_text(encoding='utf-8'))
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(video)],encoding='utf-8'))
    v=[s for s in probe['streams'] if s['codec_type']=='video'];a=[s for s in probe['streams'] if s['codec_type']=='audio']
    errors=[]
    if len(v)!=1 or len(a)!=1 or len(probe['streams'])!=2:errors.append('Expected one video and one narration audio stream')
    if v:
        s=v[0]
        for key,want in dict(codec_name='h264',pix_fmt='yuv420p',width=1920,height=1080).items():
            if s.get(key)!=want:errors.append(f'{key}: {s.get(key)} != {want}')
        if Fraction(s['avg_frame_rate'])!=m['fps']:errors.append('Frame rate mismatch')
        expected=math.ceil((m['range']['end_ms']-m['range']['start_ms'])*m['fps']/1000)
        if int(s.get('nb_read_frames',-1))!=expected:errors.append('Decoded frame count mismatch')
    if a and a[0]['codec_name']!='aac':errors.append('Narration must be AAC')
    requested=(m['range']['end_ms']-m['range']['start_ms'])/1000
    if abs(float(probe['format']['duration'])-requested)>1/m['fps']+0.05:errors.append('Duration mismatch beyond frame/AAC tolerance')
    return dict(passed=not errors,errors=errors,video=str(Path(video).resolve()),source_range=m['range'],requested_seconds=requested,probe=probe,visual_listening_review='Not performed by this script')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video',required=True);p.add_argument('--manifest',required=True);p.add_argument('--out',required=True);p.add_argument('--ffprobe',default='ffprobe')
    a=p.parse_args();r=verify(a.video,a.manifest,a.ffprobe)
    with Path(a.out).open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(passed=r['passed'],errors=r['errors']),ensure_ascii=False));raise SystemExit(0 if r['passed'] else 2)
