"""Synthetic regression checks; never consumes production media."""
import argparse
import copy
import math
import struct
import tempfile
import unittest
import wave
import zlib
from pathlib import Path

import storyboard as sb

CONFIG = None
SRT = '7\r\n00:00:00,200 --> 00:00:01,000\r\n先观察  变化。\r\n不要提前下结论。\r\n\r\n9\r\n00:00:01,000 --> 00:00:02,000\r\n如果投入$200，\r\n\r\n12\r\n00:00:02,200 --> 00:00:03,800\r\n也不保证收益。<b>原样</b>\r\n'


def test_png(path, width=1920, height=1080):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    image = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    image += chunk(b'IDAT', zlib.compress((b'\0' + b'\xc9\xdc\xe5' * width) * height)) + chunk(b'IEND', b'')
    path.write_bytes(image)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pigerzhu-test-', dir=CONFIG.work)
        self.root = Path(self.temp.name)
        self.audio = self.root / 'synthetic.wav'
        with wave.open(str(self.audio), 'wb') as wav:
            wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b''.join(struct.pack('<h', round(500 * math.sin(i * 2 * math.pi * 220 / 8000))) for i in range(32000)))
        self.srt = self.root / 'synthetic.srt'
        self.srt.write_bytes(b'\xef\xbb\xbf' + SRT.encode('utf-8'))
        self.version = self.root / 'v001'
        self.data = sb.inspect(self.audio, self.srt, self.version, CONFIG.ffprobe)
        self.inspection = self.version / 'inspection.json'
        self.plan_path = self.version / 'plan.json'
        self.plan = dict(version='synthetic-v001', listening_review='合成夹具，无真实口播，未验音画同步', shots=[])
        for sid, cues, start, end in [('A', [1], 0, 1000), ('B', [2, 3], 1000, 4000)]:
            self.plan['shots'].append(dict(id=sid, cues=cues, start_ms=start, end_ms=end,
                meaning='测试分配，不作为正式分镜', visual='测试画面', screen_text='测试短字',
                opening='先显示条件', develop='再增加信息', retain='无', transition='测试切点'))
        sb.save_json(self.plan_path, self.plan)

    def tearDown(self):
        self.temp.cleanup()

    def script_and_approve(self):
        sb.export(self.inspection, self.plan_path, 'script')
        sb.approve(self.inspection, self.plan_path, 'TEST ONLY: synthetic confirmation, not a user approval')

    def final_plan(self):
        self.plan.update(sequence_review='TEST ONLY: no visual judgment')
        for field in ('font_report', 'asset_report', 'visual_review'):
            p = self.version / (field + '.md')
            p.write_text('TEST ONLY', encoding='utf-8')
            self.plan[field] = str(p)
        for shot in self.plan['shots']:
            png = self.version / (shot['id'] + '.png')
            test_png(png)
            source = self.version / (shot['id'] + '.svg')
            source.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>test</text></svg>', encoding='utf-8')
            shot.update(png=str(png), editable=str(source), assets=[str(png)],
                stages=[dict(kind='opening', state='synthetic static fixture', png=str(png), observation='TEST ONLY'),
                        dict(kind='complete', state='synthetic static fixture', png=str(png), observation='TEST ONLY')],
                review='TEST ONLY: file validation, not image review')
        sb.save_json(self.plan_path, self.plan)

    def test_duration_and_preservation(self):
        self.assertEqual(self.data['duration_ms'], 4000)
        self.assertEqual(self.data['cues'][0]['text'], '先观察  变化。\n不要提前下结论。')
        self.assertEqual(self.data['cues'][1]['source_index'], '9')
        self.assertEqual(sb.digest(self.srt), sb.digest(self.data['sources']['srt']['path']))
        self.assertEqual(sb.digest(self.audio), sb.digest(self.data['sources']['audio']['path']))

    def test_export_complete_original_and_timing(self):
        doc = sb.export(self.inspection, self.plan_path, 'script').read_text(encoding='utf-8')
        for cue in self.data['cues']:
            self.assertIn(sb.html.escape(cue['text']), doc)
            self.assertIn(sb.stamp(cue['start_ms']), doc)
        self.assertIn('3/3', doc)
        self.assertIn('也不保证收益。&lt;b&gt;原样&lt;/b&gt;', doc)

    def test_reject_missing_duplicate_and_reordered_cues(self):
        for broken in ([2], [1, 2, 3], [3, 2]):
            with self.subTest(cues=broken):
                p = copy.deepcopy(self.plan)
                p['shots'][1]['cues'] = broken
                with self.assertRaises(ValueError):
                    sb.validate_plan(self.data, p)

    def test_timing_errors_and_edge_notes(self):
        cues = copy.deepcopy(self.data['cues'])
        cues[1]['start_ms'] = 900
        cues[-1]['end_ms'] = 4500
        problems = sb.audit(cues, 4000)
        self.assertEqual(sum(x['level'] == 'error' for x in problems), 2)
        self.assertTrue(any(x['at'] == 'head' for x in problems))
        self.assertTrue(any(x['at'] == 'tail' for x in self.data['issues']))

    def test_cut_crossing_and_reversed_time(self):
        self.plan['shots'][0]['end_ms'] = 900
        self.plan['shots'][1]['start_ms'] = 900
        self.assertTrue(any('切点' in x['message'] for x in sb.validate_plan(self.data, self.plan)))
        self.plan['shots'][1]['end_ms'] = 899
        with self.assertRaises(ValueError):
            sb.validate_plan(self.data, self.plan)

    def test_malformed_and_empty_cues(self):
        for bad in ('1\n00:00:70,000 --> 00:00:71,000\nbad', '1\n00:00:00,000 --> 00:00:01,000\n', ''):
            self.srt.write_text(bad, encoding='utf-8')
            with self.assertRaises(ValueError):
                sb.parse_srt(self.srt)

    def test_source_tamper(self):
        Path(self.data['sources']['srt']['path']).write_text('changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            sb.verified_inspection(self.inspection)

    def test_final_requires_approval(self):
        self.final_plan()
        with self.assertRaises(FileNotFoundError):
            sb.export(self.inspection, self.plan_path, 'final')

    def test_narrative_and_script_changes_invalidate_approval(self):
        self.script_and_approve()
        self.final_plan()
        self.plan['shots'][0]['opening'] = 'changed narrative'
        sb.save_json(self.plan_path, self.plan)
        with self.assertRaises(ValueError):
            sb.export(self.inspection, self.plan_path, 'final')
        self.plan['shots'][0]['opening'] = '先显示条件'
        sb.save_json(self.plan_path, self.plan)
        with (self.version / '分镜脚本.md').open('a', encoding='utf-8') as f:
            f.write('changed script')
        with self.assertRaises(ValueError):
            sb.export(self.inspection, self.plan_path, 'final')

    def test_final_valid_paths_and_all_originals(self):
        self.script_and_approve()
        self.final_plan()
        result = sb.export(self.inspection, self.plan_path, 'final').read_text(encoding='utf-8')
        for shot in self.plan['shots']:
            self.assertIn(Path(shot['png']).as_posix(), result)
            self.assertIn(Path(shot['editable']).as_posix(), result)
        for c in self.data['cues']:
            self.assertIn(sb.html.escape(c['text']), result)

    def test_missing_asset_and_wrong_png(self):
        self.script_and_approve()
        self.final_plan()
        self.plan['shots'][0]['assets'] = [str(self.version / 'missing.png')]
        sb.save_json(self.plan_path, self.plan)
        with self.assertRaises(ValueError):
            sb.export(self.inspection, self.plan_path, 'final')
        self.plan['shots'][0]['assets'] = [self.plan['shots'][0]['png']]
        sb.save_json(self.plan_path, self.plan)
        test_png(Path(self.plan['shots'][0]['png']), 50, 50)
        with self.assertRaises(ValueError):
            sb.export(self.inspection, self.plan_path, 'final')

    def test_no_overwriting_versions_or_docs(self):
        with self.assertRaises(ValueError):
            sb.inspect(self.audio, self.srt, self.version, CONFIG.ffprobe)
        sb.export(self.inspection, self.plan_path, 'script')
        with self.assertRaises(ValueError):
            sb.export(self.inspection, self.plan_path, 'script')

    def test_video_mapping_invariants(self):
        self.final_plan()
        shot = self.plan['shots'][0]
        shot['video'] = dict(file=shot['editable'], license_record=shot['editable'],
            representative_frame=shot['png'], source_url='https://example.org/clip',
            license_url='https://example.org/license', credit='Synthetic fixture', crop='fit',
            duration_ms=2000, in_ms=200, out_ms=1200, audio_start_ms=0, audio_end_ms=1000,
            representative_ms=500, speed=1, mute=True)
        self.assertEqual(sb.validate_video(shot)['out_ms'], 1200)
        for key, bad in [('speed', 0.5), ('mute', False), ('out_ms', 1500),
                         ('duration_ms', 1100), ('audio_start_ms', 1),
                         ('representative_ms', 1200), ('in_ms', 200.0)]:
            changed = copy.deepcopy(shot)
            changed['video'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                sb.validate_video(changed)

    def test_stage_order_required(self):
        self.script_and_approve()
        self.final_plan()
        self.plan['shots'][0]['stages'].reverse()
        sb.save_json(self.plan_path, self.plan)
        with self.assertRaises(ValueError):
            sb.export(self.inspection, self.plan_path, 'final')

    def test_audition_clip_bounds_and_source_unchanged(self):
        before = sb.digest(self.audio)
        clips = sb.audition(self.inspection, self.plan_path, CONFIG.ffmpeg)
        self.assertEqual(len(clips), 3)
        for clip in clips:
            self.assertTrue(Path(clip['path']).is_file())
            measured, _ = sb.probe(clip['path'], CONFIG.ffprobe)
            self.assertEqual(measured, clip['source_end_ms'] - clip['source_start_ms'])
        self.assertEqual(before, sb.digest(self.audio))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--work', default='work/pigerzhu-skill-tests')
    CONFIG = p.parse_args()
    Path(CONFIG.work).mkdir(parents=True, exist_ok=True)
    unittest.main(argv=['test_storyboard'], verbosity=2)
