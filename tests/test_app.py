import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
import unittest
import sys
import time
from unittest.mock import patch
from PySide6.QtCore import QProcess
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from transcriber.app import Window, parse_time


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        for module in ['transcriber.app.ROOT', 'transcriber.workspace.ROOT']:
            patcher = patch(module, Path(self.storage.name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_saved_result_round_trip_and_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'result.json'
            data = {'audio': str(Path(temp)/'audio.wav'), 'duration': 12,
                    'segments': [{'start': 1.125, 'end': 3.75, 'text': '你好。'}]}
            path.write_text(json.dumps(data), encoding='utf-8')
            window = Window()
            window.load_result(path)
            self.assertEqual([{k: s[k] for k in ('start', 'end', 'text')} for s in window.current_segments()], data['segments'])
            self.assertEqual(window.current_segments()[0]['source_spans'][0]['segment_id'], 1)
            window.table.item(0, 2).setText('修改后的文字。')
            self.assertTrue(window.result['edited'])
            self.assertEqual(window.current_segments()[0]['text'], '修改后的文字。')
            window.table.item(0, 1).setText('00:00:00.500')
            with self.assertRaises(ValueError):
                window.current_segments()
            window.result['edited'] = False
            window.close()

    def test_time_parser(self):
        self.assertEqual(parse_time('01:02:03.125'), 3723.125)
        self.assertEqual(parse_time('2.500'), 2.5)
        with self.assertRaises(ValueError):
            parse_time('invalid')

    def test_cancel_running_child_process(self):
        with tempfile.TemporaryDirectory() as temp:
            window = Window()
            window.job_dir = Path(temp)
            window.source = Path(temp)/'audio.wav'
            window.source.touch()
            window.process = QProcess(window)
            window.process.finished.connect(window.finished)
            window.process.start(sys.executable, ['-c', 'import time; time.sleep(60)'])
            self.assertTrue(window.process.waitForStarted(5000))
            window.set_busy(True)
            window.cancel()
            deadline = time.monotonic()+8
            while window.process is not None and time.monotonic()<deadline:
                QTest.qWait(50)
            self.assertIsNone(window.process)
            self.assertTrue(window.run_button.isEnabled())
            self.assertIn('已取消', window.status.text())
            window.close()


if __name__ == '__main__':
    unittest.main()
