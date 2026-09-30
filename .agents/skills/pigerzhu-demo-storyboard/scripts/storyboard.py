"""Audio/SRT inspection and version-bound storyboard Markdown. Python stdlib only."""
import argparse
import hashlib
import html
import json
import re
import shutil
import struct
import subprocess
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def ms(value):
    m = re.fullmatch(r'(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})', value)
    if not m:
        raise ValueError('Invalid timestamp: ' + value)
    h, minute, second, milli = map(int, m.groups())
    return ((h * 60 + minute) * 60 + second) * 1000 + milli


def stamp(value):
    h, rem = divmod(value, 3600000)
    minute, rem = divmod(rem, 60000)
    second, milli = divmod(rem, 1000)
    return f'{h:02}:{minute:02}:{second:02}.{milli:03}'


def parse_srt(path, encoding='utf-8-sig'):
    # Only normalize line endings; do not strip, re-space, clean markup or renumber source text.
    raw = Path(path).read_bytes().decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n[ \t]*\n', raw.strip('\n'))
    cues = []
    for block in blocks:
        if not block.strip():
            continue
        lines = block.split('\n')
        pos = len(cues) + 1
        if len(lines) < 3 or not re.fullmatch(r'\d+', lines[0].strip()):
            raise ValueError(f'SRT block {pos}: missing index/timestamp/text')
        timing = re.fullmatch(r'\s*(\d{2,}:[0-5]\d:[0-5]\d[,.]\d{3})\s*-->\s*(\d{2,}:[0-5]\d:[0-5]\d[,.]\d{3})(?:[ \t]+(.*))?', lines[1])
        if not timing:
            raise ValueError(f'SRT block {pos}: malformed timing {lines[1]!r}')
        text = '\n'.join(lines[2:])
        if not text.strip():
            raise ValueError(f'SRT block {pos}: empty text')
        cues.append(dict(cue=pos, source_index=lines[0], start_ms=ms(timing[1]),
                         end_ms=ms(timing[2]), text=text, timing_line=lines[1]))
    if not cues:
        raise ValueError('SRT contains no cues')
    return cues


def probe(path, binary):
    run = subprocess.run([binary, '-v', 'error', '-show_entries',
                          'format=duration:stream=codec_type,duration', '-of', 'json', str(path)],
                         check=True, capture_output=True, text=True, encoding='utf-8')
    data = json.loads(run.stdout)
    streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
    if not streams:
        raise ValueError('Input has no audio stream')
    duration = streams[0].get('duration', data.get('format', {}).get('duration'))
    if duration in (None, 'N/A'):
        duration = data.get('format', {}).get('duration')
    value = Decimal(str(duration))
    if not value.is_finite() or value <= 0:
        raise ValueError('No positive measured audio duration')
    return int((value * 1000).to_integral_value(rounding=ROUND_HALF_UP)), data


def audit(cues, duration):
    issues = []
    def add(level, at, message):
        issues.append(dict(level=level, at=at, message=message))
    ids = Counter(c['source_index'].strip() for c in cues)
    for c in cues:
        loc = f"cue {c['cue']} / {stamp(c['start_ms'])}"
        if c['end_ms'] <= c['start_ms']:
            add('error', loc, '字幕结束不晚于开始')
        if c['end_ms'] > duration or c['start_ms'] >= duration:
            add('error', loc, f"字幕越过实测音频结尾 {stamp(duration)}")
        if ids[c['source_index'].strip()] > 1:
            add('warning', loc, '源字幕编号重复；以顺序 cue 定位，不修改原编号')
    for a, b in zip(cues, cues[1:]):
        loc = f"cue {a['cue']} → {b['cue']} / {stamp(b['start_ms'])}"
        if b['start_ms'] < a['start_ms']:
            add('error', loc, '源字幕起点不按时间顺序')
        if b['start_ms'] < a['end_ms']:
            add('error', loc, f"字幕重叠 {a['end_ms'] - b['start_ms']} ms，须听查并定位冲突")
        elif b['start_ms'] > a['end_ms']:
            add('note', loc, f"字幕间隙 {b['start_ms'] - a['end_ms']} ms，不自动认定为静音")
    if cues[0]['start_ms'] > 0:
        add('note', 'head', f"开头 {cues[0]['start_ms']} ms 无字幕，需听查")
    tail = duration - max(c['end_ms'] for c in cues)
    if tail > 0:
        add('note', 'tail', f'结尾 {tail} ms 无字幕，需听查')
    return issues


def inspect(audio, srt, out, ffprobe='ffprobe', encoding='utf-8-sig'):
    audio, srt, out = Path(audio).resolve(), Path(srt).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('Version directory already exists; choose a new version')
    cues = parse_srt(srt, encoding)
    duration, metadata = probe(audio, ffprobe)
    out.mkdir(parents=True)
    src = out / 'inputs'
    src.mkdir()
    sources = {}
    for key, original in [('audio', audio), ('srt', srt)]:
        target = src / (key + original.suffix)
        before = digest(original)
        shutil.copy2(original, target)
        if before != digest(target) or before != digest(original):
            raise ValueError('Source changed while copying: ' + str(original))
        sources[key] = dict(original=str(original), path=str(target), sha256=before)
    data = dict(schema=1, sources=sources, encoding=encoding, duration_ms=duration,
                probe=metadata, cues=cues, issues=audit(cues, duration),
                listening_status='未听查；须核对首尾及每个切点，不能据此声称音画同步')
    save_json(out / 'inspection.json', data)
    return data


def verified_inspection(path):
    data = load(path)
    for item in data['sources'].values():
        if digest(item['path']) != item['sha256']:
            raise ValueError('Snapshot hash changed: ' + item['path'])
    parsed = parse_srt(data['sources']['srt']['path'], data['encoding'])
    if parsed != data['cues']:
        raise ValueError('Inspection cues differ from source SRT')
    return data


FIELDS = ('meaning', 'visual', 'screen_text', 'opening', 'develop', 'retain', 'transition')


def validate_plan(data, plan):
    shots, cues, duration = plan['shots'], data['cues'], data['duration_ms']
    if not shots or not str(plan.get('version', '')).strip():
        raise ValueError('Plan needs version and nonempty shots')
    flattened, ids, issues = [], [], []
    prev = None
    for shot in shots:
        sid = str(shot['id'])
        ids.append(sid)
        members = shot['cues']
        if not members or any(type(i) is not int or not 1 <= i <= len(cues) for i in members):
            raise ValueError('Invalid cue membership in ' + sid)
        flattened.extend(members)
        for key in FIELDS:
            if not isinstance(shot.get(key), str) or not shot[key].strip():
                raise ValueError(f'{sid}: missing {key}; use explicit 无 if not applicable')
        start, end = shot['start_ms'], shot['end_ms']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= duration:
            raise ValueError('Invalid source audio range: ' + sid)
        for i in members:
            c = cues[i - 1]
            if c['start_ms'] < start or c['end_ms'] > end:
                issues.append(dict(level='error', at=f'{sid} / cue {i}', message='本镜时间未包含完整字幕；不得裁掉原文'))
        if prev is not None and start != prev:
            issues.append(dict(level='error', at=sid, message='镜间时间有空隙或重叠，需明确修正切点'))
        if prev is not None:
            crossing = [c['cue'] for c in cues if c['start_ms'] < start < c['end_ms']]
            if crossing:
                issues.append(dict(level='error', at=f'{sid} / {stamp(start)}', message=f'切点穿过字幕 {crossing}'))
        prev = end
    if len(ids) != len(set(ids)):
        raise ValueError('Shot IDs must be unique')
    if flattened != list(range(1, len(cues) + 1)):
        counts = Counter(flattened)
        raise ValueError(f'Every cue must belong once in source order; counts={dict(counts)}')
    if shots[0]['start_ms'] != 0 or shots[-1]['end_ms'] != duration:
        issues.append(dict(level='error', at='head/tail', message='镜头区间须覆盖源音频首尾，注明无字幕部分的画面保持'))
    return issues


def approval_key(plan):
    # Export paths and visual QA may be filled after approval; narrative changes invalidate it.
    content = dict(version=plan['version'], shots=[{k: s[k] for k in ('id', 'cues', 'start_ms', 'end_ms') + FIELDS} for s in plan['shots']])
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def link(path):
    p = Path(path).resolve()
    return f'[{p.name}](<{p.as_posix()}>)'


def file_ok(path):
    p = Path(path)
    if not p.is_absolute() or not p.is_file() or p.stat().st_size == 0:
        raise ValueError('Expected nonempty file at absolute path: ' + str(p))
    return p


def png_size(path):
    with file_ok(path).open('rb') as f:
        head = f.read(24)
    if len(head) != 24 or head[:8] != b'\x89PNG\r\n\x1a\n' or head[12:16] != b'IHDR':
        raise ValueError('Not a PNG: ' + str(path))
    return struct.unpack('>II', head[16:24])


def approve(inspection, plan_path, evidence):
    data, plan = verified_inspection(inspection), load(plan_path)
    errors = [x for x in data['issues'] + validate_plan(data, plan) if x['level'] == 'error']
    if errors:
        raise ValueError('Resolve timing errors before approval: ' + json.dumps(errors, ensure_ascii=False))
    script = Path(inspection).parent / '分镜脚本.md'
    if not evidence.strip() or not script.is_file():
        raise ValueError('Need actual user confirmation evidence and the complete exported script')
    # Require the script to match this plan, not an older narrative.
    marker = '计划指纹：' + approval_key(plan)
    if marker not in script.read_text(encoding='utf-8'):
        raise ValueError('Export the current complete script first')
    record = dict(plan_sha256=approval_key(plan), script_sha256=digest(script),
                  inspection_sha256=digest(inspection), evidence=evidence)
    target = Path(inspection).parent / 'approval.json'
    if target.exists():
        raise ValueError('Approval exists; revise in a new version')
    save_json(target, record)


def validate_video(shot):
    """Validate an actual local normal-speed clip against the narration interval."""
    v = shot['video']
    for key in ('file', 'license_record', 'representative_frame'):
        file_ok(v[key])
    for key in ('source_url', 'license_url', 'credit', 'crop'):
        if not isinstance(v.get(key), str) or not v[key].strip():
            raise ValueError('Video missing provenance/crop: ' + key)
    for key in ('duration_ms', 'in_ms', 'out_ms', 'audio_start_ms', 'audio_end_ms', 'representative_ms'):
        if type(v.get(key)) is not int:
            raise ValueError('Video timestamps must be integer milliseconds: ' + key)
    if v.get('speed') != 1 or v.get('mute') is not True:
        raise ValueError('Stock clip must play at normal speed with source sound muted')
    if (v['audio_start_ms'], v['audio_end_ms']) != (shot['start_ms'], shot['end_ms']):
        raise ValueError('Video mapping does not match narration shot')
    if not 0 <= v['in_ms'] < v['out_ms'] <= v['duration_ms']:
        raise ValueError('Video selection exceeds measured footage')
    if v['out_ms'] - v['in_ms'] != shot['end_ms'] - shot['start_ms']:
        raise ValueError('Video selection cannot cover shot at normal speed')
    if not v['in_ms'] <= v['representative_ms'] < v['out_ms']:
        raise ValueError('Representative frame is outside selected footage')
    if png_size(v['representative_frame']) != (1920, 1080):
        raise ValueError('Video representative frame has wrong size')
    return v


def export(inspection, plan_path, phase):
    data, plan = verified_inspection(inspection), load(plan_path)
    issues = data['issues'] + validate_plan(data, plan)
    root = Path(inspection).parent
    final = phase == 'final'
    if final:
        record = load(root / 'approval.json')
        if record['plan_sha256'] != approval_key(plan) or record['inspection_sha256'] != digest(inspection) or record['script_sha256'] != digest(root / '分镜脚本.md'):
            raise ValueError('Confirmation does not cover the current script/plan/source version')
        if any(x['level'] == 'error' for x in issues):
            raise ValueError('Unresolved timing conflicts')
        for key in ('font_report', 'asset_report', 'visual_review'):
            file_ok(plan[key])
        if not plan.get('sequence_review', '').strip():
            raise ValueError('Missing actual sequential review record')
    name = '分镜说明.md' if final else '分镜脚本.md'
    lines = [f'# {name[:-3]}', '', f"版本：{plan['version']}", '', '计划指纹：' + approval_key(plan), '',
             f"源音频实测时长：{stamp(data['duration_ms'])}（{data['duration_ms']} ms）", '',
             f"字幕覆盖：{len(data['cues'])}/{len(data['cues'])}，顺序不变，每条恰好一次；{len(plan['shots'])} 镜。", '',
             '只验分镜；不代表最终音画同步通过。', '']
    for key, item in data['sources'].items():
        lines.extend([f"同版 {key}：{link(item['path'])}", f"SHA-256：{item['sha256']}", f"原始位置：{item['original']}", ''])
    lines += ['## 时间、首尾与切点核对', '', '听查记录：' + plan.get('listening_review', data['listening_status']), '']
    for issue in issues:
        lines += [f"- [{issue['level']}] {issue['at']}：{issue['message']}"]
    if not issues:
        lines += ['自动时间检查未发现冲突；仍需实际听查。']
    lines += ['', '候选切点（源音频绝对时间）：' + '、'.join(stamp(s['start_ms']) for s in plan['shots'][1:]), '']
    if final:
        for key in ('font_report', 'asset_report', 'visual_review'):
            lines += [f'{key}：{link(plan[key])}', '']
        lines += ['全片联看记录：' + plan['sequence_review'], '']
    labels = dict(meaning='对象、动作与关系', visual='主画面', screen_text='精简上屏字', opening='开场先看什么', develop='之后增加什么与完成态', retain='连续页保留什么', transition='镜头衔接')
    for shot in plan['shots']:
        lines += [f"## 镜 {shot['id']}", '', f"源音频绝对区间：{stamp(shot['start_ms'])} → {stamp(shot['end_ms'])}", '', '### 完整逐字原文', '']
        for i in shot['cues']:
            c = data['cues'][i - 1]
            lines += [f"cue {i}｜源编号 {c['source_index']}｜{stamp(c['start_ms'])} → {stamp(c['end_ms'])}", '', '<pre>' + html.escape(c['text']) + '</pre>', '']
        for key, label in labels.items():
            lines += [f'### {label}', '', shot[key], '']
        if shot.get('media_decision'):
            lines += ['### 媒介选择与理由', '', shot['media_decision'], '']
        if final:
            expected = tuple(plan.get('canvas', [1920, 1080]))
            if png_size(shot['png']) != expected:
                raise ValueError('Wrong PNG canvas: ' + shot['png'])
            source = file_ok(shot['editable'])
            if source.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError('Flattened image is not editable source')
            if not shot.get('assets') or not shot.get('stages') or not shot.get('review', '').strip():
                raise ValueError('Need independent assets, stage screenshots and actual page review')
            kinds = [stage.get('kind') for stage in shot['stages']]
            if kinds[0] != 'opening' or kinds[-1] != 'complete' or any(k != 'reveal' for k in kinds[1:-1]):
                raise ValueError('Stages must be opening, optional reveal(s), complete in order')
            lines += [f"完成态 PNG：{link(shot['png'])}", '', f"可编辑源：{link(source)}", '', '独立素材：', '']
            for asset in shot['assets']:
                lines += ['- ' + link(file_ok(asset))]
            lines += ['', '阶段检查：', '']
            for stage in shot['stages']:
                if png_size(stage['png']) != expected:
                    raise ValueError('Wrong stage PNG size')
                if not stage.get('state', '').strip() or not stage.get('observation', '').strip():
                    raise ValueError('Stage needs reproducible state and actual observation')
                lines += [f"- {stage['kind']} / {stage['state']}：{link(stage['png'])}；{stage['observation']}"]
            lines += ['', '本页验收：' + shot['review'], '']
            if shot.get('media_kind') == 'video':
                v = validate_video(shot)
                lines += ['### 实拍视频区间映射', '',
                          f"本地视频：{link(v['file'])}", '',
                          f"来源：[{v['credit']}]({v['source_url']})；[许可]({v['license_url']})", '',
                          f"许可与限制记录：{link(v['license_record'])}", '',
                          f"素材内 {stamp(v['in_ms'])} → {stamp(v['out_ms'])} 对应源音频 {stamp(v['audio_start_ms'])} → {stamp(v['audio_end_ms'])}", '',
                          '播放速度：1 倍；素材原声关闭；保留原口播。', '',
                          '裁切/缩放：' + v['crop'], '',
                          f"代表帧：{link(v['representative_frame'])}（素材内 {stamp(v['representative_ms'])}）", '']
    target = root / name
    if target.exists():
        raise ValueError('Document already exists; create a new version to revise')
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return target


def audition(inspection, plan_path, ffmpeg):
    data, plan = verified_inspection(inspection), load(plan_path)
    validate_plan(data, plan)
    root = Path(inspection).parent / 'audition'
    root.mkdir(exist_ok=False)
    points = [('head', 0)] + [(f'cut-{i}', s['start_ms']) for i, s in enumerate(plan['shots'][1:], 1)] + [('tail', data['duration_ms'])]
    result = []
    for name, point in points:
        start, end = max(0, point - 1500), min(data['duration_ms'], point + 1500)
        out = root / (name + '.wav')
        subprocess.run([ffmpeg, '-v', 'error', '-n', '-i', data['sources']['audio']['path'],
                        '-ss', f'{start / 1000:.3f}', '-t', f'{(end-start)/1000:.3f}', '-vn', '-c:a', 'pcm_s16le', str(out)], check=True)
        result.append(dict(path=str(out.resolve()), source_start_ms=start, source_end_ms=end, cut_ms=point))
    save_json(root / 'index.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('inspect')
    for key in ('audio', 'srt', 'out'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--encoding', default='utf-8-sig')
    for name in ('export', 'approve', 'audition'):
        p = commands.add_parser(name)
        p.add_argument('--inspection', required=True)
        p.add_argument('--plan', required=True)
        if name == 'export':
            p.add_argument('--phase', choices=['script', 'final'], required=True)
        elif name == 'approve':
            p.add_argument('--evidence', required=True)
        else:
            p.add_argument('--ffmpeg', default='ffmpeg')
    a = vars(parser.parse_args())
    command = a.pop('command')
    if 'plan' in a:
        a['plan_path'] = a.pop('plan')
    result = globals()[command](**a)
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(2)
