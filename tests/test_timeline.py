import unittest
import math
from transcriber.timeline import restore_punctuation, sentences, export_text, timecode, validate_segments, normalized, reconcile_model_boundaries


def stamped(text, step=.25):
    return [{'text': c, 'start_time': i*step, 'end_time': (i+1)*step}
            for i, c in enumerate(c for c in text if c.isalnum())]


class TimelineTests(unittest.TestCase):
    def test_punctuation_is_preserved(self):
        text = '你好，张老师。今天开会！'
        words = restore_punctuation(text, stamped(text), 10)
        self.assertEqual(''.join(w['word'] for w in words), text)
        self.assertEqual(words[0]['start'], 10)

    def test_sentence_boundary_even_with_no_pause(self):
        text = '你好。我们开始开会。谢谢！'
        result = sentences(restore_punctuation(text, stamped(text)))
        self.assertEqual([s['text'] for s in result], ['你好。', '我们开始开会。', '谢谢！'])
        validate_segments(result)

    def test_mixed_english_spacing_preserved(self):
        text = '使用 OpenAI API 做测试。'
        tokens = ['使', '用', 'OpenAI', 'API', '做', '测', '试']
        stamps = [{'text': t, 'start_time': i*.1, 'end_time': (i+1)*.1} for i, t in enumerate(tokens)]
        words = restore_punctuation(text, stamps)
        result = sentences(words)
        self.assertEqual(''.join(s['text'] for s in result), text)

    def test_refuses_mismatched_alignment(self):
        with self.assertRaises(ValueError):
            restore_punctuation('你好', stamped('您好'))

    def test_invalid_timestamps(self):
        for start, end in [(-1, 1), (2, 1), (0, math.nan), (1, 1)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_segments([{'start': start, 'end': end, 'text': '测试'}])

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            validate_segments([{'start': 0, 'end': 2, 'text': '甲'}, {'start': 1.9, 'end': 3, 'text': '乙'}])

    def test_thirty_ms_model_overlap_is_reconciled_without_changing_text(self):
        source = [{'start': 1633.419, 'end': 1635.5, 'text': '前句。'},
                  {'start': 1635.47, 'end': 1636.83, 'text': '嗯，'}]
        result, audit = reconcile_model_boundaries(source)
        validate_segments(result, 1794.176)
        self.assertEqual(result[0]['end'], 1635.485)
        self.assertEqual(result[1]['start'], 1635.485)
        self.assertEqual(source[0]['end'], 1635.5)
        self.assertEqual([s['text'] for s in result], [s['text'] for s in source])
        self.assertEqual(audit[0]['overlap_seconds'], .03)

    def test_large_or_unsplittable_overlap_is_merged(self):
        for source in [
            [{'start': 0, 'end': 2, 'text': '甲'}, {'start': 1.9, 'end': 3, 'text': '乙'}],
            [{'start': 1.99, 'end': 2, 'text': '甲'}, {'start': 1.97, 'end': 2.03, 'text': '乙'}],
        ]:
            result, audit = reconcile_model_boundaries(source)
            validate_segments(result)
            self.assertEqual(result, [{'start': min(s['start'] for s in source),
                                       'end': max(s['end'] for s in source), 'text': '甲\n乙'}])
            self.assertEqual(audit[0]['kind'], 'merge')
            self.assertEqual(audit[0]['source_segments'], [1, 2])
            self.assertEqual(source[0]['text'], '甲')

    def test_backward_overlap_backtracks_and_preserves_text_order(self):
        source = [{'start': 0, 'end': 2, 'text': 'first'},
                  {'start': 3, 'end': 4, 'text': 'second'},
                  {'start': 1, 'end': 5, 'text': 'third'},
                  {'start': 5, 'end': 6, 'text': 'last'}]
        result, audit = reconcile_model_boundaries(source)
        validate_segments(result)
        self.assertEqual(result, [{'start': 0, 'end': 5, 'text': 'first\nsecond\nthird'}, source[3]])
        self.assertEqual(audit[-1]['source_segments'], [1, 2, 3])

    def test_model_repair_does_not_hide_invalid_intervals(self):
        for start, end in [(1, math.nan), (2, 1), (-1, 2), (1, 1)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                reconcile_model_boundaries([{'start': 0, 'end': 3, 'text': '甲'},
                                            {'start': start, 'end': end, 'text': '乙'}])

    def test_correct_model_boundaries_are_unchanged(self):
        source = [{'start': 0, 'end': 1, 'text': '甲'}, {'start': 1.1, 'end': 2, 'text': '乙'}]
        result, audit = reconcile_model_boundaries(source)
        self.assertEqual(source, result)
        self.assertEqual(audit, [])

    def test_export_formats_and_long_duration(self):
        data = [{'start': 90000.125, 'end': 90001.75, 'text': '测试'}]
        self.assertIn('25:00:00,125 --> 25:00:01,750', export_text(data, 'srt'))
        self.assertTrue(export_text(data, 'vtt').startswith('WEBVTT\n\n'))
        self.assertIn('25:00:00.125', export_text(data, 'txt'))
        self.assertEqual(timecode(59.9998), '00:01:00.000')

    def test_long_text_never_drops_characters(self):
        text = '这是一个用于测试长句子分段时不能遗漏任何字词的例子'*8
        result = sentences(restore_punctuation(text, stamped(text)))
        self.assertGreater(len(result), 1)
        self.assertEqual(normalized(''.join(s['text'] for s in result)), normalized(text))
        validate_segments(result)

    def test_pause_uses_real_boundaries(self):
        words = restore_punctuation('我们开始，然后结束。', stamped('我们开始，然后结束。'))
        for w in words[4:]:
            w['start'] += 5
            w['end'] += 5
        result = sentences(words)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['end'], 1)
        self.assertEqual(result[1]['start'], 6)

    def test_pause_does_not_leave_two_character_fragment(self):
        words = restore_punctuation('我是你爹。', stamped('我是你爹。', step=.8))
        for w in words[2:]:
            w['start'] += 2
            w['end'] += 2
        result = sentences(words)
        self.assertEqual([s['text'] for s in result], ['我是你爹。'])


if __name__ == '__main__':
    unittest.main()
