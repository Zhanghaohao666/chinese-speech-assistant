import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint, QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from transcriber.app import Window
from transcriber.importing import media_path


class ImportTests(unittest.TestCase):
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
        self.audio = self.root/'中文 会议 (1).wav'
        with wave.open(str(self.audio), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b'\0\0'*1600)
        self.w = Window()
        self.w.show()
        QTest.qWait(20)
        self.original_clipboard = QMimeData()
        mime = QApplication.clipboard().mimeData()
        if mime:
            for kind in mime.formats():
                self.original_clipboard.setData(kind, mime.data(kind))
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        self.w.process = None
        if self.w.result:
            self.w.result['edited'] = False
        self.w.close()
        self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QTest.qWait(50)
        QApplication.clipboard().setMimeData(self.original_clipboard)

    def files(self, paths=None):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in (paths or [self.audio])])
        return mime

    def test_copy_file_ctrl_v_imports_even_when_search_focused(self):
        QApplication.clipboard().setMimeData(self.files())
        self.w.search.setFocus()
        QTest.keyClick(self.w.search, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.w.source, self.audio.resolve())
        self.assertEqual(self.w.search.text(), '')
        self.assertTrue(self.w.run_button.isEnabled())
        self.assertIsNone(self.w.process)

    def test_text_paste_in_editor_is_not_hijacked(self):
        QApplication.clipboard().setText('预算与下周待办')
        self.w.search.setFocus()
        QTest.keyClick(self.w.search, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.w.search.text(), '预算与下周待办')
        self.assertIsNone(self.w.source)

    def test_quoted_path_and_file_url_import(self):
        for text in [f'"{self.audio}"', QUrl.fromLocalFile(str(self.audio)).toString()]:
            mime = QMimeData()
            mime.setText(text)
            self.assertEqual(media_path(mime), self.audio.resolve())
        QApplication.clipboard().setText(f'"{self.audio}"')
        self.w.paste_button.click()
        self.assertEqual(self.w.source, self.audio.resolve())

    def test_path_shortcut_outside_editor(self):
        QApplication.clipboard().setText(str(self.audio))
        self.w.choose_button.setFocus()
        QTest.keyClick(self.w.choose_button, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.w.source, self.audio.resolve())

    def test_drop_on_transcript_imports_and_resets_highlight(self):
        mime = self.files()
        target = self.w.transcript_stack
        enter = QDragEnterEvent(QPoint(20, 20), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, enter)
        self.assertTrue(enter.isAccepted())
        self.assertTrue(self.w.transcript_panel.property('dropActive'))
        drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, drop)
        self.assertEqual(self.w.source, self.audio.resolve())
        self.assertFalse(self.w.transcript_panel.property('dropActive'))

    def test_invalid_multiple_remote_and_missing_are_rejected(self):
        mime = self.files([self.audio, self.audio])
        self.assertFalse(self.w.import_mime(mime))
        self.assertIn('一个', self.w.status.text())
        mime = QMimeData()
        mime.setUrls([QUrl('https://example.com/audio.wav')])
        self.assertFalse(self.w.import_mime(mime))
        mime = self.files([self.root/'missing.mp3'])
        self.assertFalse(self.w.import_mime(mime))
        mime.setText(str(self.root/'image.png'))
        self.assertIsNone(self.w.source)

    def test_busy_and_unsaved_edits_are_protected(self):
        self.w.process = object()
        self.assertFalse(self.w.import_mime(self.files()))
        self.assertIsNone(self.w.source)
        self.w.process = None
        result = {'audio': str(self.audio), 'duration': .1, 'segments': [{'start': 0, 'end': .1, 'text': '保留。'}]}
        path = self.root/'result.json'
        path.write_text(json.dumps(result), encoding='utf-8')
        self.w.load_result(path)
        self.w.table.item(0, 2).setText('尚未保存的修改。')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            self.assertFalse(self.w.import_mime(self.files()))
        self.assertEqual(self.w.current_segments()[0]['text'], '尚未保存的修改。')


if __name__ == '__main__':
    unittest.main()
