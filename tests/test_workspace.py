import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from transcriber.app import Window


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for module in ['transcriber.app.ROOT', 'transcriber.workspace.ROOT']:
            mock = patch(module, self.root)
            mock.start()
            self.addCleanup(mock.stop)
        self.path = self.root/'result.json'
        self.data = {'audio': str(self.root/'missing.wav'), 'duration': 12, 'dialogue_layout': True,
                     'segments': [{'start': 1, 'end': 3, 'text': '讨论预算。'},
                                  {'start': 4, 'end': 7, 'text': '记录待办。'}]}
        self.path.write_text(json.dumps(self.data), encoding='utf-8')
        self.w = Window()
        self.addCleanup(self.close_window)
        self.w.load_result(self.path)

    def close_window(self):
        if self.w.result:
            self.w.result['edited'] = False
        self.w.close()

    def test_search_filters_view_but_export_keeps_every_segment(self):
        self.w.search.setText('预算')
        self.assertFalse(self.w.table.isRowHidden(0))
        self.assertTrue(self.w.table.isRowHidden(1))
        output = self.root/'export.srt'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(output), '')):
            self.w.export('srt')
        self.assertIn('记录待办。', output.read_text(encoding='utf-8'))
        self.w.search.setText('不存在')
        self.assertIn('没有匹配', self.w.edit_note.text())

    def test_edited_json_save_reopen_and_switch_guard(self):
        self.w.table.item(0, 2).setText('修正的预算。')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            self.w.load_result(self.path)
        self.assertEqual(self.w.current_segments()[0]['text'], '修正的预算。')
        output = self.root/'edited.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(output), '')):
            self.w.export('json')
        data = json.loads(output.read_text(encoding='utf-8'))
        self.assertFalse(data['edited'])
        self.w.load_result(output)
        self.assertEqual(self.w.current_segments(), data['segments'])

    def test_follow_uses_edited_time_and_respects_search(self):
        self.w.on_position(4500)
        self.assertEqual(self.w.table.currentRow(), 1)
        self.w.table.item(1, 0).setText('00:00:05.000')
        self.w.active_row = -1
        self.w.table.selectRow(0)
        self.w.on_position(4500)
        self.assertEqual(self.w.table.currentRow(), 0)
        self.w.on_position(5500)
        self.assertEqual(self.w.table.currentRow(), 1)
        self.w.search.setText('预算')
        self.w.active_row = -1
        self.w.table.selectRow(0)
        self.w.on_position(5500)
        self.assertEqual(self.w.table.currentRow(), 0)

    def test_slider_seeks_and_media_updates_do_not_clear_sentence_end(self):
        with patch.object(self.w.player, 'setPosition') as seek:
            self.w.seek_slider.setValue(2500)
            seek.assert_called_with(2500)
            self.w.stop_at = 3000
            seek.reset_mock()
            self.w.on_position(2600)
            seek.assert_not_called()
            self.assertEqual(self.w.stop_at, 3000)

    def test_preferences_and_history_are_persisted(self):
        self.w.device.setCurrentIndex(self.w.device.findData('cpu'))
        settings = json.loads((self.root/'ui.local.json').read_text(encoding='utf-8'))
        self.assertEqual(settings['device'], 'cpu')
        self.w.refresh_history()
        self.assertEqual(self.w.history.count(), 1)
        self.assertIn('已完成', self.w.history.item(0).text())
        self.w.job_dir = self.root/'jobs'/'test'
        self.w.job_dir.mkdir(parents=True)
        (self.w.job_dir/'config.json').write_text(json.dumps({'audio': 'failed.wav'}))
        self.w.record_job_state('失败')
        self.w.refresh_history()
        self.assertTrue(any('失败' in self.w.history.item(i).text() for i in range(self.w.history.count())))

    def test_responsive_layout_keeps_transcript_and_controls_visible(self):
        self.w.show()
        for width, height in [(1440, 900), (1280, 800), (1024, 640), (854, 534)]:
            self.w.resize(width, height)
            QTest.qWait(40)
            self.assertGreater(self.w.table.viewport().height(), 40)
            self.assertGreater(self.w.table.columnWidth(2), 220)
            self.assertEqual(self.w.notes_panel.isVisible(), width >= 1320)
            self.assertTrue(self.w.player_panel.isVisible())
        self.w.navigate(3)
        self.assertTrue(self.w.device.isVisible())


if __name__ == '__main__':
    unittest.main()
