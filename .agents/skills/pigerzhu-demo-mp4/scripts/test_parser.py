import html
import tempfile
import unittest
from pathlib import Path
from parse_storyboard import parse


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for f in ['audio.wav','page.png','page.svg','asset.svg']:(self.root/f).write_bytes(b'synthetic fixture')
        (self.root/'srt.srt').write_text('4\n00:00:00,100 --> 00:00:01,000\n保留  两个空格 & <标签>\n\n8\n00:00:01,100 --> 00:00:01,900\n第二句\n',encoding='utf-8')
        def shot(sid,a,b,index,num,x,y,words):
            return f'## 镜 {sid}\n源音频绝对区间：{a} → {b}\ncue {index}｜源编号 {num}｜{x} → {y}\n\n<pre>{html.escape(words)}</pre>\n完成态 PNG：[page](<page.png>)\n可编辑源：[source](<page.svg>)\n独立素材：\n- [asset](<asset.svg>)\n阶段检查：\n'
        self.text='# 分镜说明\n源音频实测时长：00:00:02.000\n同版 audio：[audio](<audio.wav>)\n同版 srt：[srt](<srt.srt>)\n'+shot('A','00:00:00.000','00:00:01.050',1,4,'00:00:00.100','00:00:01.000','保留  两个空格 & <标签>')+shot('B','00:00:01.050','00:00:02.000',2,8,'00:00:01.100','00:00:01.900','第二句')
        self.doc=self.root/'分镜说明.md';self.doc.write_text(self.text,encoding='utf-8')

    def tearDown(self):self.tmp.cleanup()
    def run_parse(self,text=None,**kwargs):
        if text is not None:self.doc.write_text(text,encoding='utf-8')
        return parse(self.doc,probe=False,**kwargs)
    def test_verbatim_and_all_cues(self):
        m=self.run_parse();self.assertEqual(m['shots'][0]['cues'][0]['text'],'保留  两个空格 & <标签>');self.assertEqual(len(m['shots']),2)
    def test_midrange_keeps_full_context(self):
        m=self.run_parse(start='1.2',end='1.8');self.assertEqual(m['range'],dict(start_ms=1200,end_ms=1800));self.assertEqual(m['shots'][0]['start_ms'],0)
    def test_reject_changed_original(self):
        with self.assertRaises(ValueError):self.run_parse(self.text.replace('第二句','改写'))
    def test_reject_duplicate_cue(self):
        with self.assertRaises(ValueError):self.run_parse(self.text.replace('cue 2','cue 1'))
    def test_reject_shot_gap(self):
        with self.assertRaises(ValueError):self.run_parse(self.text.replace('00:00:01.050 →','00:00:01.060 →'))
    def test_reject_outside_range(self):
        with self.assertRaises(ValueError):self.run_parse(end='3')
    def test_reject_missing_asset(self):
        with self.assertRaises(ValueError):self.run_parse(self.text.replace('<asset.svg>','<missing.svg>'))
    def test_reject_crossed_cue(self):
        with self.assertRaises(ValueError):self.run_parse(self.text.replace('00:00:01.050','00:00:00.900'))


if __name__=='__main__':unittest.main(verbosity=2)
