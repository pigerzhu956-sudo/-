"""Read a confirmed storyboard document, not any previous project's plan JSON."""
import argparse
import hashlib
import html
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

TS = r'\d{2}:\d{2}:\d{2}[.,]\d{3}'
LINK = r'\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s]+))\s*\)'


def milliseconds(value):
    value = str(value).replace(',', '.')
    if ':' not in value:
        return round(float(value) * 1000)
    h, m, s = value.split(':')
    if not (0 <= int(m) < 60 and 0 <= float(s) < 60):
        raise ValueError('Invalid time: ' + value)
    return round((int(h)*3600 + int(m)*60 + float(s))*1000)


def digest(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local(raw, base):
    raw = unquote(raw)
    if re.match(r'^(https?|data|javascript):', raw, re.I):
        raise ValueError('Expected local file, not URL: ' + raw)
    p = Path(raw)
    if not p.is_absolute():
        p = base / p
    p = p.resolve()
    if not p.is_file() or p.stat().st_size == 0:
        raise ValueError('Missing or empty linked file: ' + str(p))
    return str(p)


def linked(text, label, base):
    m = re.search(r'(?m)^' + label + r'\s*[：:]\s*' + LINK, text)
    if not m:
        raise ValueError('Missing document field: ' + label)
    return local(m.group(1) or m.group(2), base)


def srt_cues(file):
    raw = Path(file).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    cues = []
    for block in re.split(r'\n[ \t]*\n', raw.strip('\n')):
        m = re.fullmatch(r'(\d+)\n(' + TS + r')\s*-->\s*(' + TS + r')\n([\s\S]+)', block)
        if not m:
            raise ValueError('Malformed SRT block: ' + block[:100])
        cues.append(dict(index=len(cues)+1, source_index=m[1], start_ms=milliseconds(m[2]), end_ms=milliseconds(m[3]), text=m[4]))
    for i, c in enumerate(cues):
        if c['end_ms'] <= c['start_ms'] or (i and c['start_ms'] < cues[i-1]['end_ms']):
            raise ValueError('Overlapping or reversed SRT cue ' + str(i+1))
    return cues


def parse(document, start=None, end=None, ffprobe='ffprobe', probe=True):
    doc = Path(document).resolve()
    text = doc.read_text(encoding='utf-8-sig')
    audio = linked(text, r'同版 (?:audio|音频)', doc.parent)
    srt = linked(text, r'同版 (?:srt|SRT|字幕)', doc.parent)
    duration_match = re.search(r'源音频实测时长[：:]\s*(' + TS + ')', text)
    if not duration_match:
        raise ValueError('Missing measured audio duration')
    duration = milliseconds(duration_match[1])
    for label, file in [('audio', audio), ('srt', srt)]:
        match = re.search(r'同版 ' + label + r'[：:][^\n]*\nSHA-256[：:]\s*([a-fA-F0-9]{64})', text)
        if match and digest(file) != match[1].lower():
            raise ValueError('Source hash differs from document: ' + label)
    audio_probe = None
    if probe:
        audio_probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', audio], encoding='utf-8'))
        if not any(s['codec_type'] == 'audio' for s in audio_probe['streams']):
            raise ValueError('Source has no audio stream')
        measured = float(audio_probe['format']['duration'])*1000
        if abs(measured-duration) > 50:
            raise ValueError(f'Document/audio duration conflict: {duration} vs {measured}')
    cues = srt_cues(srt)
    sections = list(re.finditer(r'(?m)^## 镜\s+(\S+)\s*$', text))
    if not sections:
        raise ValueError('No shot sections; adapt parser to actual document, do not guess')
    shots, covered = [], []
    for i, match in enumerate(sections):
        part = text[match.end():sections[i+1].start() if i+1 < len(sections) else len(text)]
        interval = re.search(r'源音频绝对区间[：:]\s*(' + TS + r')\s*→\s*(' + TS + ')', part)
        if not interval:
            raise ValueError('Missing interval for shot ' + match[1])
        shot = dict(id=match[1], start_ms=milliseconds(interval[1]), end_ms=milliseconds(interval[2]),
                    png=linked(part, '完成态 PNG', doc.parent), editable=linked(part, '可编辑源', doc.parent), cues=[], document_section=part)
        for c in re.finditer(r'cue\s+(\d+)｜源编号\s+(\d+)｜(' + TS + r')\s*→\s*(' + TS + r')\s*\n\s*<pre>([\s\S]*?)</pre>', part):
            index = int(c[1])
            if not 1 <= index <= len(cues):
                raise ValueError('Cue index out of range')
            observed = dict(index=index, source_index=c[2], start_ms=milliseconds(c[3]), end_ms=milliseconds(c[4]), text=html.unescape(c[5]))
            if observed != cues[index-1]:
                raise ValueError('Verbatim/time mismatch at cue ' + str(index))
            if observed['start_ms'] < shot['start_ms'] or observed['end_ms'] > shot['end_ms']:
                raise ValueError('Shot boundary crosses cue ' + str(index))
            shot['cues'].append(observed)
            covered.append(index)
        assets = re.search(r'独立素材[：:]([\s\S]*?)(?:阶段检查[：:]|\Z)', part)
        shot['assets'] = [local(m[1] or m[2], doc.parent) for m in re.finditer(LINK, assets[1])] if assets else []
        if not shot['assets']:
            raise ValueError('Missing independent assets for shot ' + shot['id'])
        shot['stages'] = [dict(kind=m[1], time_ms=int(m[2])) for m in re.finditer(r'- (opening|reveal|complete) / [^\n]*?#t=(\d+)', part)]
        if '### 实拍视频区间映射' in part:
            mapping = re.search(r'素材内 ('+TS+r') → ('+TS+r') 对应源音频 ('+TS+r') → ('+TS+r')', part)
            if not mapping:
                raise ValueError('Missing actual footage time mapping')
            a, b, c, d = [milliseconds(x) for x in mapping.groups()]
            if (c,d) != (shot['start_ms'],shot['end_ms']) or b-a != d-c:
                raise ValueError('Footage does not cover shot at normal speed')
            if '素材原声关闭' not in part:
                raise ValueError('Footage mute contract missing')
            crop = re.search(r'裁切/缩放[：:]([^\n]+)', part)
            if not crop or '全幅' not in crop[1] or '无额外裁切' not in crop[1]:
                raise ValueError('Non-default video crop: agent must implement the documented crop explicitly')
            video_file = linked(part, '本地视频', doc.parent)
            if probe:
                vp = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_streams', '-of', 'json', video_file], encoding='utf-8'))['streams'][0]
                if b > float(vp['duration'])*1000+1 or abs(vp['width']/vp['height']-16/9) > 0.001:
                    raise ValueError('Video range/aspect does not match full-frame contract')
            shot['video'] = dict(file=video_file, in_ms=a, out_ms=b, mute=True, speed=1, crop=crop[1].strip())
        shots.append(shot)
    if covered != list(range(1,len(cues)+1)):
        raise ValueError('Missing, duplicate or out-of-order cues')
    cursor=0
    for s in shots:
        if s['start_ms'] != cursor or s['end_ms'] <= cursor:
            raise ValueError('Shot gap/overlap at ' + s['id'])
        cursor=s['end_ms']
    if cursor != duration:
        raise ValueError('Shots do not cover complete audio duration')
    a = 0 if start is None else milliseconds(start)
    b = duration if end is None else milliseconds(end)
    if not 0 <= a < b <= duration:
        raise ValueError('Requested source interval is outside narration')
    return dict(schema=1, document=str(doc), document_sha256=digest(doc), audio=audio, srt=srt,
                audio_sha256=digest(audio), srt_sha256=digest(srt), duration_ms=duration,
                range=dict(start_ms=a,end_ms=b), canvas=[1920,1080],fps=30,shots=shots,audio_probe=audio_probe)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--document',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--start');p.add_argument('--end');p.add_argument('--ffprobe',default='ffprobe')
    args=p.parse_args()
    data=parse(args.document,args.start,args.end,args.ffprobe)
    target=Path(args.out).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(out=str(target),shots=len(data['shots']),cues=sum(len(s['cues']) for s in data['shots']),range=data['range']),ensure_ascii=False))
