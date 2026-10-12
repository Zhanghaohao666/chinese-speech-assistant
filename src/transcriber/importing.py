"""Local-file import shared by picker, drops and clipboard; never downloads URLs."""
from pathlib import Path
from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit, QTextEdit, QPlainTextEdit

MEDIA_EXTENSIONS = {'.wav', '.m4a', '.mp3', '.flac', '.aac', '.ogg', '.wma', '.mp4', '.mkv', '.opus', '.aiff', '.aif', '.webm', '.mov'}


def media_path(mime):
    if mime.hasUrls():
        urls = mime.urls()
        if len(urls) != 1:
            raise ValueError('一次请导入一个录音文件。')
        if not urls[0].isLocalFile():
            raise ValueError('请先将录音保存到本机，再导入本地文件。')
        value = urls[0].toLocalFile()
    elif mime.hasText():
        lines = [s.strip() for s in mime.text().strip().splitlines() if s.strip()]
        if len(lines) != 1:
            raise ValueError('请复制一个录音文件，或它的完整本地路径。')
        value = lines[0].strip('"')
        if value.lower().startswith('file:'):
            value = QUrl(value).toLocalFile()
    else:
        raise ValueError('剪贴板里没有录音文件。请在资源管理器中选中文件并按 Ctrl+C。')
    path = Path(value)
    if path.suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValueError('请选择音频或视频文件，例如 WAV、M4A、MP3。')
    if not path.is_absolute() or not path.is_file():
        raise ValueError('找不到这个本地文件，请确认文件已下载且路径有效。')
    return path.resolve()


class ImportBehavior:
    def paste_audio(self):
        return self.import_mime(QApplication.clipboard().mimeData())

    def import_mime(self, mime):
        if self.process:
            self.status.setText('正在转写，请完成或取消当前任务后再导入。')
            return False
        try:
            path = media_path(mime)
        except (ValueError, OSError) as error:
            self.status.setText(str(error))
            return False
        return bool(self.set_audio(path))

    def drop_feedback(self, active):
        if not hasattr(self, 'transcript_panel'):
            return
        panel = self.transcript_panel
        if panel.property('dropActive') == active:
            return
        panel.setProperty('dropActive', active)
        panel.style().unpolish(panel)
        panel.style().polish(panel)
        panel.update()

    def eventFilter(self, watched, event):
        if not isinstance(watched, QWidget) or watched.window() is not self:
            return super().eventFilter(watched, event)
        if QApplication.activeModalWidget() is not None:
            return super().eventFilter(watched, event)
        kind = event.type()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            try:
                media_path(event.mimeData())
                valid = not self.process
            except (ValueError, OSError):
                valid = False
            self.drop_feedback(valid and kind != QEvent.Type.Drop)
            if valid:
                event.acceptProposedAction()
                if kind == QEvent.Type.Drop:
                    self.import_mime(event.mimeData())
                return True
            # Do not insert unsupported dragged file paths into text editors.
            if event.mimeData().hasUrls():
                event.ignore()
                return True
        elif kind == QEvent.Type.DragLeave:
            self.drop_feedback(False)
        elif kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.matches(QKeySequence.StandardKey.Paste):
            mime = QApplication.clipboard().mimeData()
            focus = QApplication.focusWidget()
            editing_text = isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit))
            should_import = mime.hasUrls()
            if not should_import and not editing_text:
                try:
                    media_path(mime)
                    should_import = True
                except (ValueError, OSError):
                    pass
            if should_import:
                event.accept()
                if kind == QEvent.Type.KeyPress:
                    self.import_mime(mime)
                return True
        return super().eventFilter(watched, event)
