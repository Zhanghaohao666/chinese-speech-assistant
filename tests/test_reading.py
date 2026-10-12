import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from docx import Document
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QPushButton, QInputDialog
from transcriber.reading import build_reading, aligned_split, prepare_project, reading_document
from transcriber.documents import export_reading
from transcriber.timeline import validate_segments, normalized
import test_workspace as workspace_tests


class ReadingTests(unittest.TestCase):
    def test_reading_repairs_split_words_without_twelve_second_limit(self):
        source = [{'start': 0, 'end': 11, 'text': '西秀'},
                  {'start': 11, 'end': 22, 'text': '区开展工'},
                  {'start': 22, 'end': 33, 'text': '作，落实整改'},
                  {'start': 33, 'end': 44, 'text': '措施。'}]
        result = build_reading(source)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], '西秀区开展工作，落实整改措施。')
        self.assertEqual((result[0]['start'], result[0]['end']), (0, 44))
        self.assertEqual([r['segment_id'] for r in result[0]['source_spans']], [1, 2, 3, 4])

    def test_sentence_split_uses_word_times_not_character_proportions(self):
        source = [{'start': 1, 'end': 90, 'text': '你好。最后，再见。'}]
        words = [{'word': '你好。', 'start': 1, 'end': 3},
                 {'word': '最后，', 'start': 12, 'end': 20},
                 {'word': '再见。', 'start': 60, 'end': 90}]
        result = build_reading(source, words)
        self.assertEqual([(s['start'], s['end']) for s in result], [(1, 3), (12, 90)])
        self.assertEqual(result[1]['word_range'], [1, 3])
        self.assertEqual(result[1]['source_spans'][0]['char_start'], 3)
        self.assertEqual(aligned_split(dict(source[0], word_range=[0,3]), '你好。', '最后，再见。', words), (3, 12, 1))

    def test_missing_or_mismatched_alignment_does_not_invent_internal_times(self):
        source = [{'start': 0, 'end': 90, 'text': '你好。最后，再见。'}]
        for words in (None, [{'word': '不同原文', 'start': 2, 'end': 3}]):
            result = build_reading(source, words, target_chars=1)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['timing_basis'], 'source_boundary')
            self.assertEqual((result[0]['start'], result[0]['end']), (0, 90))
        self.assertIsNone(aligned_split(dict(source[0],word_range=[0,1]), '你好。', '最后，再见。', []))

    def test_speaker_turns_and_topic_starts_split_reading(self):
        source = [{'start': 0, 'end': 3, 'text': '讨论预算。', 'speaker': '甲'},
                  {'start': 3, 'end': 6, 'text': '大家同意。', 'speaker': '甲'},
                  {'start': 6, 'end': 9, 'text': '其次，讨论时间。', 'speaker': '甲'},
                  {'start': 9, 'end': 12, 'text': '明天出发。', 'speaker': '乙'}]
        result = build_reading(source)
        self.assertEqual([s['text'] for s in result], ['讨论预算。大家同意。', '其次，讨论时间。', '明天出发。'])
        self.assertEqual([s['speaker'] for s in result], ['甲','甲','乙'])

    def test_schema_roundtrip_keeps_manual_reading_edits_and_originals(self):
        original = {'audio': '测试.wav', 'segments': [{'start': 0, 'end': 3, 'text': '原文。'}]}
        project = prepare_project(original)
        project['reading_paragraphs'][0]['text'] = '修改后的正文。'
        reopened = prepare_project(json.loads(json.dumps(project)))
        self.assertEqual(reopened['segments'][0]['text'], '修改后的正文。')
        self.assertEqual(reopened['subtitle_segments'], original['segments'])
        self.assertEqual(reopened['source_segments'], original['segments'])

    def test_txt_docx_share_document_structure_and_editorial_headings(self):
        project = prepare_project({'audio': '会议.wav', 'duration': 3,
                                   'segments': [{'start': 0, 'end': 3, 'text': '讨论预算。'}]})
        project['reading_paragraphs'][0]['chapter_title'] = '预算讨论'
        data = reading_document(project)
        expected = [data['title']] + [f'{k}：{v}' for k,v in data['metadata']] + [b['text'] for b in data['blocks']]
        self.assertIn('预算讨论（编辑整理）', expected)
        with tempfile.TemporaryDirectory() as directory:
            txt, docx = Path(directory)/'test.txt', Path(directory)/'test.docx'
            export_reading(project, txt, 'txt')
            export_reading(project, docx, 'docx')
            self.assertEqual([line for line in txt.read_text(encoding='utf-8-sig').splitlines() if line], expected)
            self.assertEqual([p.text for p in Document(docx).paragraphs], expected)
            self.assertNotIn('→', txt.read_text(encoding='utf-8-sig'))


class ReadingWorkspaceTests(unittest.TestCase):
    setUpClass = classmethod(workspace_tests.WorkspaceTests.setUpClass.__func__)
    setUp = workspace_tests.WorkspaceTests.setUp
    close_window = workspace_tests.WorkspaceTests.close_window

    def test_loading_and_sync_preserve_raw_float_times_and_provenance(self):
        data = {'audio': str(self.root/'missing.wav'), 'duration': 6,
                'segments': [{'start': 1.1234, 'end': 5.9876, 'text': '你好。'}]}
        self.path.write_text(json.dumps(data), encoding='utf-8')
        self.w.load_result(self.path)
        self.w.sync_view()
        p = self.w.result['reading_paragraphs'][0]
        self.assertEqual((p['start'], p['end']), (1.1234, 5.9876))
        self.assertEqual(p['timing_basis'], 'source_boundary')
        self.assertEqual(p['source_spans'][0]['start'], 1.1234)

    def test_editor_split_uses_aligned_word_times_without_prompting(self):
        data = {'audio': str(self.root/'missing.wav'), 'duration': 6,
                'segments': [{'start': 1, 'end': 5, 'text': '第一句。第二句。'}],
                'words': [{'word': '第一句。', 'start': 1, 'end': 2},
                          {'word': '第二句。', 'start': 3, 'end': 5}]}
        self.path.write_text(json.dumps(data), encoding='utf-8')
        self.w.load_result(self.path)
        errors = []
        def split():
            dialog = QApplication.activeModalWidget()
            try:
                editor = dialog.findChild(QPlainTextEdit, 'paragraphText')
                cursor = editor.textCursor()
                cursor.setPosition(4)
                editor.setTextCursor(cursor)
                with patch.object(QInputDialog, 'getText', side_effect=AssertionError('must use word times')):
                    dialog.findChild(QPushButton, 'splitParagraph').click()
            except Exception as error:
                errors.append(error)
                dialog.reject()
        QTimer.singleShot(0, split)
        self.w.edit_paragraph(0)
        self.assertFalse(errors, errors)
        self.w.sync_view()
        paragraphs = self.w.result['reading_paragraphs']
        self.assertEqual([(s['start'],s['end']) for s in paragraphs], [(1,2),(3,5)])
        self.assertEqual([s['word_range'] for s in paragraphs], [[0,1],[1,2]])
        self.assertTrue(all(s['source_spans'] for s in paragraphs))

    def test_view_switch_keeps_separate_edits_and_export_routes(self):
        self.w.table.item(0,2).setText('阅读版修正。')
        self.w.view_mode.setCurrentIndex(1)
        self.assertEqual(self.w.current_segments()[0]['text'], '讨论预算。')
        self.w.table.item(0,2).setText('字幕版修正。')
        self.w.view_mode.setCurrentIndex(0)
        self.assertEqual(self.w.current_segments()[0]['text'], '阅读版修正。')
        for kind, expected in [('txt','阅读版修正。'),('srt','字幕版修正。')]:
            output = self.root/f'test.{kind}'
            with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(output),'')):
                self.w.export(kind)
            self.assertIn(expected, output.read_text(encoding='utf-8-sig'))
        self.assertEqual(self.w.result['source_segments'][0]['text'], '讨论预算。')
        output = self.root/'both.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(output),'')):
            self.w.export('json')
        self.w.load_result(output)
        self.assertEqual(self.w.current_segments()[0]['text'], '阅读版修正。')
        self.w.view_mode.setCurrentIndex(1)
        self.assertEqual(self.w.current_segments()[0]['text'], '字幕版修正。')


if __name__ == '__main__':
    unittest.main()
