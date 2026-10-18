"""Regression checks for evidence gates, source identity, render timing and opening."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('video_notes', Path(__file__).with_name('video_notes.py'))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class VideoNotesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='video-notes-test-')
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        v.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=640x360:r=30:d=1.2',
               '-f', 'lavfi', '-i', 'color=c=blue:s=640x360:r=30:d=1.2', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2.4',
               '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-map', '2:a',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', cls.source])
        cls.info = v.probe(cls.source)
        cls.frames = []
        for i, t in enumerate([0.1, 0.6, 1.1, 1.3, 1.8, 2.3]):
            p = cls.root / f'f{i}.jpg'
            v.grab(cls.source, t, p)
            cls.frames.append({'time': t, 'file': str(p)})
        common = {'terms': ['固定画面'], 'subject_motion': '主体静止', 'camera_motion': '镜头固定',
                  'depth': '纯色测试画面，不判断景深', 'confidence': 'high', 'generation_prompt': '固定镜头，画面保持静止。',
                  'edit_instruction': '采用该静态画面，按边界截取。'}
        cls.plan = {'schema_version': 1, 'source': {'sha256': v.digest(cls.source), **cls.info},
                    'review': {'visual': 'complete', 'audio': 'unavailable'},
                    'shots': [dict(common, id='S1', start=0, end=1.2, observed='红色静态测试画面', evidence=cls.frames[:3]),
                              dict(common, id='S2', start=1.2, end=cls.info['duration'], observed='蓝色静态测试画面', evidence=cls.frames[3:])],
                    'joins': [{'id': 'J1', 'from_shot': 'S1', 'to_shot': 'S2', 'start': 1.0, 'end': 1.4, 'cut_time': 1.2,
                               'type': '直接切换', 'observed': '红色直接切换为蓝色', 'continuity': '纯色变化，没有动作匹配',
                               'confidence': 'high', 'evidence': [cls.frames[2], cls.frames[3]],
                               'generation_constraints': '分别制作静态纯色画面', 'edit_instruction': '在一点二秒处直接切换。',
                               'audio_observed': '未试听，声音衔接待核对'}]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def save(self, plan):
        p = self.root / 'analysis.json'
        v.write_json(p, plan)
        return p

    def test_candidates_locate_known_cut(self):
        cuts = v.cut_candidates(self.source, 0.32, self.info)
        self.assertTrue(any(abs(t - 1.2) < 1 / 30 + 0.001 for t in cuts), cuts)

    def test_complete_analysis_passes(self):
        v.validate(self.source, self.save(self.plan))

    def test_rejects_pending_and_missing_join(self):
        p = copy.deepcopy(self.plan)
        p['review']['visual'] = 'pending'
        with self.assertRaisesRegex(ValueError, '尚未完成'):
            v.validate(self.source, self.save(p))
        p = copy.deepcopy(self.plan)
        p['joins'] = []
        with self.assertRaisesRegex(ValueError, '相邻镜头'):
            v.validate(self.source, self.save(p))

    def test_rejects_wrong_source_and_one_sided_evidence(self):
        p = copy.deepcopy(self.plan)
        p['source']['sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, '指纹'):
            v.validate(self.source, self.save(p))
        p = copy.deepcopy(self.plan)
        p['joins'][0]['evidence'] = [self.frames[0], self.frames[1]]
        p['joins'][0]['start'] = 0
        with self.assertRaisesRegex(ValueError, '两侧'):
            v.validate(self.source, self.save(p))

    def test_rejects_nan_timestamp_and_existing_outputs(self):
        p = copy.deepcopy(self.plan)
        p['shots'][0]['end'] = float('nan')
        with self.assertRaisesRegex(ValueError, '有限数字'):
            v.validate(self.source, self.save(p))
        with self.assertRaisesRegex(ValueError, '已有内容'):
            v.new_directory(self.root)

    def test_rejects_subframe_coverage_gap(self):
        p = copy.deepcopy(self.plan)
        p['shots'][1]['start'] = 1.21
        with self.assertRaisesRegex(ValueError, '空隙'):
            v.validate(self.source, self.save(p))

    def test_open_dispatch_is_not_shell_and_headless_is_honest(self):
        path = self.root / 'video;literal.mp4'
        with patch.object(v.sys, 'platform', 'darwin'), patch.object(v, 'run') as call:
            self.assertEqual(v.open_player(path)['status'], 'requested')
            self.assertEqual(call.call_args.args[0], ['open', path])
        with patch.object(v.sys, 'platform', 'linux'), patch.dict(v.os.environ, {}, clear=True):
            self.assertEqual(v.open_player(path)['status'], 'unavailable')

    def test_render_preserves_duration_audio_and_decodes(self):
        args = type('Args', (), {'input': str(self.source), 'analysis': str(self.save(self.plan)),
                                'out': str(self.root / 'rendered'), 'width': 640, 'panel_height': 460,
                                'font': None, 'open': True, 'no_local_open': True})()
        v.render(args)
        result = json.loads((self.root / 'rendered/render_result.json').read_text())
        self.assertTrue(result['audio'])
        self.assertLess(abs(result['duration'] - self.info['duration']), 0.07)
        self.assertEqual(result['open']['status'], 'unavailable')
        report = Path(result['report']).read_text()
        self.assertIn('生成素材的起止条件', report)
        from PIL import ImageChops, ImageStat
        for time, card_index in [(0.5, 0), (0.75, 1), (2.2, 3)]:
            frame = self.root / f'check-{time}.jpg'
            v.grab(Path(result['video']), time, frame)
            decoded = v.Image.open(frame).convert('RGB')
            reference = v.Image.open(self.root / f'rendered/cards/card-{card_index:04}.png').convert('RGB')
            panel = decoded.crop((0, decoded.height-reference.height, decoded.width, decoded.height))
            self.assertEqual(panel.size, reference.size)
            self.assertLess(max(ImageStat.Stat(ImageChops.difference(panel, reference)).mean), 5,
                            f'标注与画面时间不匹配：{time}')


if __name__ == '__main__':
    unittest.main()
