import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer, Qt, QPoint
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit, QPlainTextEdit, QPushButton, QInputDialog
from PySide6.QtTest import QTest
from transcriber.dialogue import short_time
from transcriber.reading import build_reading
import test_workspace as workspace_tests


class GroupTests(unittest.TestCase):
    def test_period_does_not_break_paragraph_and_times_remain_real(self):
        original = [{'start': 0, 'end': 2, 'text': '第一句。'}, {'start': 2.5, 'end': 5, 'text': '第二句。'}]
        result = build_reading(original)
        self.assertEqual([{k:s[k] for k in ('start','end','text')} for s in result], [{'start': 0, 'end': 5, 'text': '第一句。第二句。'}])
        self.assertEqual(len(original), 2)
        self.assertNotIn('speaker', result[0])

    def test_speaker_changes_override_paragraph_heuristic(self):
        original = [{'start': 0, 'end': 2, 'text': '一。', 'speaker': '甲'},
                    {'start': 2, 'end': 4, 'text': '二。', 'speaker': '乙'},
                    {'start': 4, 'end': 7, 'text': '三。', 'speaker': '乙'},
                    {'start': 7, 'end': 9, 'text': '四。'}]
        result = build_reading(original)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1]['text'], '二。三。')
        self.assertNotIn('speaker', result[2])

    def test_unknown_pause_is_not_a_speaker_label_and_reading_has_no_time_cap(self):
        original = [{'start': 0, 'end': 8, 'text': '讨论一。'},
                    {'start': 10, 'end': 12, 'text': '讨论二。'},
                    {'start': 12, 'end': 25, 'text': '讨论三。'}]
        result = build_reading(original)
        self.assertEqual([s['text'] for s in result], ['讨论一。', '讨论二。讨论三。'])
        self.assertTrue(all('speaker' not in s for s in result))
        self.assertEqual(short_time(65.9), '01:05')
        self.assertEqual(short_time(3601), '01:00:01')


class DialogueInteractionTests(unittest.TestCase):
    # Reuse isolated storage, without running the same regressions twice.
    setUpClass = classmethod(workspace_tests.WorkspaceTests.setUpClass.__func__)
    setUp = workspace_tests.WorkspaceTests.setUp
    close_window = workspace_tests.WorkspaceTests.close_window
    def in_dialog(self, action):
        errors = []
        def handle():
            dialog = QApplication.activeModalWidget()
            try:
                action(dialog)
            except Exception as error:
                errors.append(error)
                dialog.reject()
        QTimer.singleShot(0, handle)
        return errors

    def test_manual_merge_preserves_text_and_bounds(self):
        self.w.merge_next(0)
        self.assertEqual(self.w.current_segments(), [{'start': 1, 'end': 7, 'text': '讨论预算。记录待办。'}])
        self.assertTrue(self.w.result['edited'])

    def test_dialog_speaker_merges_only_adjacent_matching_speaker(self):
        self.w.table.item(0, 2).setData(Qt.ItemDataRole.UserRole, '发言人 1')
        def action(dialog):
            dialog.findChild(QLineEdit, 'paragraphSpeaker').setText('发言人 1')
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        errors = self.in_dialog(action)
        self.w.edit_paragraph(1)
        self.assertFalse(errors, errors)
        self.assertEqual(len(self.w.current_segments()), 1)
        self.assertEqual(self.w.current_segments()[0]['speaker'], '发言人 1')

    def test_split_uses_entered_time_and_keeps_both_texts(self):
        self.w.merge_next(0)
        def action(dialog):
            editor = dialog.findChild(QPlainTextEdit, 'paragraphText')
            cursor = editor.textCursor()
            cursor.setPosition(5)
            editor.setTextCursor(cursor)
            with patch.object(QInputDialog, 'getText', return_value=('4', True)):
                dialog.findChild(QPushButton, 'splitParagraph').click()
        errors = self.in_dialog(action)
        self.w.edit_paragraph(0)
        self.assertFalse(errors, errors)
        self.assertEqual(self.w.current_segments(), [
            {'start': 1, 'end': 4, 'text': '讨论预算。'},
            {'start': 4, 'end': 7, 'text': '记录待办。'}])

    def test_timestamp_click_plays_exact_start_and_stops_at_end(self):
        self.w.show()
        QTest.qWait(30)
        rect = self.w.table.visualItemRect(self.w.table.item(1, 2))
        self.w.table.scrollToItem(self.w.table.item(1, 2))
        QTest.qWait(30)
        rect = self.w.table.visualItemRect(self.w.table.item(1, 2))
        with patch.object(self.w.player, 'setPosition') as seek, patch.object(self.w.player, 'play') as play:
            QTest.mouseClick(self.w.table.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.x()+30, rect.y()+22))
        seek.assert_called_with(4000)
        play.assert_called_once()
        self.assertEqual(self.w.stop_at, 7000)


if __name__ == '__main__':
    unittest.main()
