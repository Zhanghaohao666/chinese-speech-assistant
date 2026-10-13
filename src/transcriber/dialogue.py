"""Readable dialogue paragraphs; pause grouping is never speaker recognition."""
import math
from uuid import uuid4

from PySide6.QtCore import Qt, QSize, QRectF, QEvent, QPointF
from PySide6.QtGui import QColor, QFont, QTextDocument, QTextCursor, QTextBlockFormat, QPolygonF, QPen
from PySide6.QtWidgets import (QStyledItemDelegate, QStyle, QDialog, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QDialogButtonBox, QMenu,
    QPushButton, QMessageBox, QInputDialog)
from .theme import COLORS
from .reading import aligned_split, merge_metadata


def short_time(seconds):
    seconds = max(0, math.floor(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'


def text_document(text, width):
    document = QTextDocument()
    font = QFont('Microsoft YaHei UI')
    font.setPixelSize(17)
    document.setDefaultFont(font)
    document.setDocumentMargin(0)
    document.setPlainText(text)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    fmt = QTextBlockFormat()
    fmt.setLineHeight(147, 1)  # ProportionalHeight; stable, comfortable paragraph rhythm.
    cursor.setBlockFormat(fmt)
    document.setTextWidth(max(80, width))
    return document


class DialogueDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        width = self.parent().viewport().width() - 48
        doc = text_document(index.data() or '', width)
        return QSize(200, int(doc.size().height()) + 88)

    def paint(self, painter, option, index):
        painter.save()
        rect = QRectF(option.rect).adjusted(4, 6, -4, -6)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS['ink'] if selected else COLORS['divider']), 2 if selected else 1))
        painter.setBrush(QColor(COLORS['selection'] if selected else COLORS['pearl'] if hover else COLORS['white']))
        painter.drawRoundedRect(rect, 8, 8)
        stripe = ['cyan','purple','red','yellow'][index.row()%4]
        painter.fillRect(QRectF(rect.left()+1,rect.top()+12,4,rect.height()-24),QColor(COLORS[stripe]))
        row = index.row()
        table = self.parent()
        try:
            from .app import parse_time
            start = parse_time(table.item(row, 0).text())
            end = parse_time(table.item(row, 1).text())
            stamp, duration = short_time(start), f'{end-start:.1f} 秒'
        except ValueError:
            stamp, duration = '时间待修正', '时间待修正'
        small = QFont('Consolas')
        small.setPixelSize(13)
        painter.setFont(small)
        painter.setPen(QColor(COLORS['primary']))
        painter.setBrush(QColor(COLORS['primary']))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(rect.left()+20,rect.top()+13),QPointF(rect.left()+20,rect.top()+23),QPointF(rect.left()+27,rect.top()+18)]))
        painter.setPen(QColor(COLORS['primary']))
        painter.drawText(rect.adjusted(36, 10, -20, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, stamp)
        small = QFont('Microsoft YaHei UI')
        small.setPixelSize(13)
        painter.setFont(small)
        speaker = index.data(Qt.ItemDataRole.UserRole)
        if speaker:
            painter.setPen(QColor(COLORS['muted']))
            painter.drawText(rect.adjusted(126, 10, -20, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(speaker))
        document = text_document(index.data() or '', rect.width()-40)
        painter.translate(rect.left()+20, rect.top()+40)
        context = document.documentLayout().PaintContext()
        context.palette.setColor(context.palette.ColorRole.Text, QColor(COLORS['ink']))
        document.documentLayout().draw(painter, context)
        painter.restore()
        painter.save()
        painter.setFont(small)
        painter.setPen(QColor(COLORS['muted']))
        painter.drawText(rect.adjusted(20, 0, -20, -10), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, duration)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            area = option.rect.adjusted(4, 6, -4, -6)
            if event.position().y() < area.top()+36 and event.position().x() < area.left()+120:
                self.parent().selectRow(index.row())
                self.parent().window().play_selected()
        return False


class DialogueBehavior:
    def edit_document_info(self):
        if not self.result:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('阅读文档信息')
        dialog.resize(520, 230)
        layout = QVBoxLayout(dialog)
        title = QLineEdit(self.result.get('title', ''))
        date = QLineEdit(self.result.get('meeting_date', ''))
        date.setPlaceholderText('未确认时留空，不从文件名推断日期')
        layout.addWidget(QLabel('文档标题'))
        layout.addWidget(title)
        layout.addWidget(QLabel('会议日期'))
        layout.addWidget(date)
        layout.addWidget(QLabel('TXT、DOCX、PDF 共用这些信息；章节标题可在段落编辑中添加。'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        def save():
            self.result.update(title=title.text().strip() or '会议转写', meeting_date=date.text().strip())
            self.mark_edited(None)
            dialog.accept()
        buttons.accepted.connect(save)
        dialog.exec()

    def paragraph_menu(self, point):
        row = self.table.rowAt(point.y())
        if row < 0:
            return
        self.table.selectRow(row)
        menu = QMenu(self)
        menu.addAction('编辑文字、时间与说话人', lambda: self.edit_paragraph(row))
        if self.table.item(row, 2).data(Qt.ItemDataRole.UserRole):
            menu.addAction('重命名此说话人（两版全篇）…', lambda: self.rename_speaker(row))
        menu.addAction('播放这一段', self.play_selected)
        menu.addAction('从光标位置拆分…', lambda: self.edit_paragraph(row))
        merge = menu.addAction('与下一段合并', lambda: self.merge_next(row))
        merge.setEnabled(row < self.table.rowCount()-1)
        menu.exec(self.table.viewport().mapToGlobal(point))

    def rename_speaker(self, row):
        old = self.table.item(row, 2).data(Qt.ItemDataRole.UserRole)
        if not old or self.process:
            return
        name, ok = QInputDialog.getText(self, '重命名说话人', '对阅读版和字幕版中这个标签统一改名：', text=old)
        if not ok or not name.strip():
            return
        try:
            self.sync_view()
            for key in ('reading_paragraphs', 'subtitle_segments'):
                for part in self.result[key]:
                    if part.get('speaker') == old:
                        part['speaker'] = name.strip()
            self.result.setdefault('speaker_names', {})[old] = name.strip()
            key = 'reading_paragraphs' if self.view_kind == 'reading' else 'subtitle_segments'
            self.apply_paragraphs(self.result[key])
        except ValueError as error:
            QMessageBox.warning(self, '请检查时间', str(error))

    def apply_paragraphs(self, segments):
        from .timeline import validate_segments
        validate_segments(segments, self.result.get('duration'))
        self.result['segments'] = segments
        self.result['dialogue_layout'] = True
        self.populate_segments(segments)
        self.mark_edited(None)

    def merge_next(self, row):
        segments = self.current_segments()
        if row+1 >= len(segments):
            return
        first, second = segments[row:row+2]
        if first.get('speaker') != second.get('speaker'):
            QMessageBox.information(self, '说话人不一致', '请先核对并编辑两段的说话人标记，再合并。')
            return
        merge_metadata(first, second)
        del segments[row+1]
        self.apply_paragraphs(segments)
        self.table.selectRow(row)

    def edit_paragraph(self, row):
        if not self.result or self.process or row < 0:
            return
        from .app import parse_time
        from .timeline import timecode, validate_segments
        segments = self.current_segments()
        original = segments[row]
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑对话段落')
        dialog.resize(640, 450)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        fields = QHBoxLayout()
        start = QLineEdit(timecode(original['start']))
        end = QLineEdit(timecode(original['end']))
        start.setObjectName('paragraphStart')
        end.setObjectName('paragraphEnd')
        for caption, field in [('开始', start), ('结束', end)]:
            fields.addWidget(QLabel(caption))
            fields.addWidget(field)
        layout.addLayout(fields)
        speaker = QLineEdit(original.get('speaker', ''))
        speaker.setObjectName('paragraphSpeaker')
        speaker.setPlaceholderText('手动标注说话人（可留空，如“发言人 1”）')
        layout.addWidget(speaker)
        chapter = QLineEdit(original.get('chapter_title', ''))
        chapter.setObjectName('chapterTitle')
        chapter.setPlaceholderText('可选章节标题，导出自动标明“编辑整理”')
        chapter.setVisible(self.view_kind == 'reading')
        layout.addWidget(chapter)
        text = QPlainTextEdit(original['text'])
        text.setObjectName('paragraphText')
        layout.addWidget(text, 1)
        hint = QLabel('拆分优先使用已有字词时间；没有对应时间时需回听填写，不按字数推算。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        split = QPushButton('从光标位置拆成两段…')
        split.setObjectName('splitParagraph')
        layout.addWidget(split)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)

        def commit(split_at=None):
            try:
                updated = dict(original, start=parse_time(start.text()), end=parse_time(end.text()), text=text.toPlainText().strip())
                for key in ('start', 'end'):
                    if updated[key] == round(original[key], 3):
                        updated[key] = original[key]
                if original.get('source_spans'):
                    if updated['text'] != original['text']:
                        updated['alignment_status'] = 'text_edited'
                    if any(updated[k] != original[k] for k in ('start','end')):
                        updated['timing_basis'] = 'manual'
                updated.pop('speaker', None)
                if speaker.text().strip():
                    updated['speaker'] = speaker.text().strip()
                if chapter.text().strip():
                    updated['chapter_title'] = chapter.text().strip()
                else:
                    updated.pop('chapter_title', None)
                replacement = [updated]
                if split_at is not None:
                    cursor = text.textCursor()
                    cursor.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
                    left = cursor.selectedText().replace('\u2029', '\n').strip()
                    cursor = text.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
                    right = cursor.selectedText().replace('\u2029', '\n').strip()
                    if isinstance(split_at, tuple):
                        left_end, right_start, word_index = split_at
                        replacement = [dict(updated, end=left_end, text=left), dict(updated, start=right_start, text=right)]
                        replacement[0]['word_range'] = [updated['word_range'][0], word_index]
                        replacement[1]['word_range'] = [word_index, updated['word_range'][1]]
                    else:
                        replacement = [dict(updated, end=split_at, text=left), dict(updated, start=split_at, text=right)]
                        for part in replacement:
                            part.pop('word_range', None)
                            if part.get('source_spans'):
                                part['timing_basis'] = 'manual'
                    replacement[1].pop('chapter_title', None)
                    if original.get('paragraph_id'):
                        replacement[1]['paragraph_id'] = 'p'+uuid4().hex[:12]
                    for part in replacement:
                        if part.get('source_spans'):
                            part['source_scope'] = 'parent_paragraph'
                candidate = segments[:row] + replacement + segments[row+1:]
                validate_segments(candidate, self.result.get('duration'))
                # Only known speakers are merged during manual editing. Preserve
                # explicit splits and never regroup unknown speech after a save.
                if split_at is None and updated.get('speaker'):
                    i = 0
                    while i+1 < len(candidate):
                        a, b = candidate[i:i+2]
                        if a.get('speaker') == b.get('speaker') == updated['speaker']:
                            merge_metadata(a, b)
                            del candidate[i+1]
                        else:
                            i += 1
                self.apply_paragraphs(candidate)
                dialog.accept()
            except ValueError as error:
                hint.setText(str(error))

        def split_here():
            if text.textCursor().position() in (0, text.document().characterCount()-1):
                hint.setText('请先将文字光标放到段落中间需要拆分的位置。')
                return
            cursor = text.textCursor()
            cursor.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
            left = cursor.selectedText().replace('\u2029', '\n').strip()
            cursor = text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            right = cursor.selectedText().replace('\u2029', '\n').strip()
            boundary = aligned_split(original, left, right, self.result.get('words', []))
            if boundary is not None:
                commit(boundary)
                return
            value, ok = QInputDialog.getText(dialog, '拆分时间', '请输入这处实际音频时间（秒或 HH:MM:SS.mmm），时间不会按字数推算：')
            if ok:
                try:
                    boundary = parse_time(value)
                    if not parse_time(start.text()) < boundary < parse_time(end.text()):
                        raise ValueError('拆分时间必须在本段开始和结束之间。')
                    commit(boundary)
                except ValueError as error:
                    hint.setText(str(error))
        split.clicked.connect(split_here)
        buttons.accepted.connect(lambda: commit())
        dialog.exec()
