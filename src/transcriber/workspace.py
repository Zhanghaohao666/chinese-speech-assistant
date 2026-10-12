"""Workspace navigation and native media interactions around the existing worker."""
import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QAbstractItemView, QFileDialog

from .engine import save_json
from .timeline import timecode
from .dialogue import short_time
from .kinetic import playback_icon
from .asr_backends import ENGINES, QWEN_FILES
from . import APP_NAME
from .model_catalog import CATALOG, location, missing_files, required_models

ROOT = Path(__file__).resolve().parents[2]


class WorkspaceBehavior:
    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        if index == 1:
            self.refresh_history()
        elif index == 2:
            self.refresh_models()

    def set_state(self, state, text):
        self.badge.setText(text)
        self.badge.setProperty('state', state)
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def update_heading(self):
        name = self.result.get('title') if self.result else None
        self.meeting_title.setText(name or (self.source.stem if self.source else '从一段录音开始'))
        if self.source:
            actual = self.result.get('model_name', 'Qwen3-ASR-1.7B') if self.result else ENGINES[self.engine.currentData()]['name']
            self.file_label.setText(f'{self.source.name}  ·  {actual}  ·  本地处理')
            self.file_label.setToolTip(str(self.source))

    def toggle_notes(self):
        self.notes_requested = not self.notes_requested
        self.adapt_layout()

    def adapt_layout(self):
        compact = self.width() < 1100
        self.sidebar.setFixedWidth(72 if compact else 208)
        self.brand.setText('wwh' if compact else APP_NAME)
        self.brand.setStyleSheet('font-size: 16px;' if compact else 'font-size: 19px;')
        self.brand_note.setVisible(not compact)
        self.local_note.setVisible(not compact)
        labels = ['工作台', '历史会议', '模型管理', '设置']
        for btn, title in zip(self.nav_buttons, labels):
            btn.setText('' if compact else title)
            btn.setStyleSheet('padding: 12px 8px;' if compact else '')
        allowed = self.width() >= 1320
        self.notes_panel.setVisible(allowed and self.notes_requested)
        self.notes_toggle.setEnabled(allowed)
        self.notes_toggle.setToolTip('窗口宽度不足，已自动收起纪要面板' if not allowed else '显示或收起纪要面板')
        self.notes_toggle.setText('收起纪要' if allowed and self.notes_requested else '纪要面板')
        short = self.height() < 740
        self.file_label.setVisible(not short)
        self.eyebrow.setVisible(not short)
        self.workspace_layout.setSpacing(8 if short else 16)
        self.body_layout.setContentsMargins(16 if compact else 24, 16 if short else 24,
                                           16 if compact else 24, 16 if short else 24)
        self.resize_rows()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'notes_panel'):
            self.adapt_layout()

    def resize_rows(self):
        if not hasattr(self, 'table'):
            return
        self.table.resizeRowsToContents()
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, max(68, self.table.rowHeight(row)))

    def filter_transcript(self):
        query = self.search.text().strip().casefold()
        found = 0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            matches = item is not None and query in item.text().casefold()
            self.table.setRowHidden(row, not matches)
            found += int(matches)
        self.count_label.setText(f'{found} / {self.table.rowCount()} 段' if query else f'{found} 段')
        note = '点击开始时间回放 · 双击编辑 · 右键合并 / 拆分 · 时长含段内停顿'
        if self.result and self.result.get('timing_warnings'):
            note = '音频块时间（非精确句子起止） · '+note
        self.edit_note.setText('没有匹配的内容，请换个关键词。' if query and not found else note)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.stop_at = None
            self.player.play()

    def sync_playback(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.transport.setText('暂停' if playing else '播放')
        self.transport.setIcon(playback_icon(playing))

    def on_duration(self, duration):
        self.seek_slider.setRange(0, duration)
        self.duration_label.setText('/ ' + short_time(duration/1000))

    def seek_position(self, position):
        self.stop_at = None
        self.player.setPosition(position)

    def seek_cell(self, row, column):
        if column not in (0, 1):
            return
        try:
            segment = self.current_segments()[row]
            self.seek_position(round(segment['start' if column == 0 else 'end']*1000))
        except (ValueError, IndexError) as error:
            self.status.setText('请先修正时间：' + str(error))

    def highlight_position(self, position):
        if not self.result or not self.follow_playback.isChecked():
            return
        if self.table.state() == QAbstractItemView.State.EditingState:
            return
        # Only parse the edited table after edits, not on every media tick.
        if self.playback_segments is None:
            try:
                self.playback_segments = self.current_segments()
            except ValueError:
                return
        row = next((i for i, seg in enumerate(self.playback_segments)
                    if seg['start']*1000 <= position < seg['end']*1000), -1)
        if row >= 0 and row != self.active_row:
            self.active_row = row
            if not self.table.isRowHidden(row):
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 2), QAbstractItemView.ScrollHint.EnsureVisible)

    def save_preferences(self):
        self.preferences.update(device=self.device.currentData(), hotwords=self.hotwords.text(),
                                engine=self.engine.currentData(),
                                model_dirs={key: field.text().strip() for key, field in self.model_dirs.items()},
                                follow_playback=self.follow_playback.isChecked(),
                                diarization=self.diarization_enabled.isChecked(), num_speakers=self.speaker_count.value())
        try:
            save_json(ROOT/'ui.local.json', self.preferences)
            self.settings_status.setText('设置已自动保存。')
        except OSError as error:
            self.settings_status.setText('设置未保存：' + str(error))

    def update_engine_controls(self, busy=False):
        key = self.engine.currentData()
        self.engine_note.setText(ENGINES[key]['note'])
        self.hotwords.setEnabled(not busy and key == 'qwen')
        self.device.setEnabled(not busy and key != 'sensevoice')
        self.device.setToolTip('SenseVoice 固定使用 CPU INT8；此选项仅对 Qwen / FireRed 生效。')

    def engine_changed(self):
        self.update_engine_controls(bool(self.process))
        self.save_preferences()
        self.update_heading()

    def remember_project(self, path):
        path = str(Path(path).resolve())
        self.preferences['recent_projects'] = [path] + [p for p in self.preferences.get('recent_projects', []) if p != path][:49]
        self.save_preferences()

    def refresh_history(self):
        self.history.clear()
        records = {}
        for path in self.preferences.get('recent_projects', []):
            records[str(Path(path).resolve())] = Path(path)
        jobs = ROOT/'jobs'
        if jobs.exists():
            for directory in jobs.iterdir():
                if directory.is_dir():
                    path = directory/'result.json'
                    records[str(path.resolve())] = path
        rows = []
        for path in records.values():
            try:
                is_result = path.is_file()
                config = path if is_result else path.parent/'config.json'
                data = json.loads(config.read_text(encoding='utf-8'))
                title = data.get('title') or Path(data['audio']).stem
                timestamp = config.stat().st_mtime
                state = '已完成' if is_result else '未完成'
                if not is_result:
                    metadata = path.parent/'ui_status.json'
                    if metadata.exists():
                        state = json.loads(metadata.read_text(encoding='utf-8')).get('status', state)
                        if state == '处理中':
                            state = '处理中' if self.process and path.parent == self.job_dir else '已中断'
                rows.append((timestamp, title, state, path, is_result, data))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for timestamp, title, state, path, complete, data in sorted(rows, key=lambda row: row[0], reverse=True):
            duration = f"  ·  {data['duration']:.1f} 秒" if 'duration' in data else ''
            text = f'{title}\n{time.strftime("%Y-%m-%d  %H:%M", time.localtime(timestamp))}{duration}    ·    {state}'
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, (str(path), complete))
            self.history.addItem(item)
        self.history_note.setText(f'{len(rows)} 个本地项目 · 未完成任务可打开对应目录查看日志。' if rows else '还没有历史任务。导入一段录音开始吧。')
        self.filter_history()

    def filter_history(self):
        query = self.history_search.text().strip().casefold()
        for index in range(self.history.count()):
            item = self.history.item(index)
            item.setHidden(query not in item.text().casefold())

    def open_history(self, item):
        if self.process:
            self.history_note.setText('当前任务仍在处理中，完成或取消后才能切换会议。')
            return
        path, complete = item.data(Qt.ItemDataRole.UserRole)
        if complete:
            try:
                self.load_result(path)
                self.navigate(0)
            except (OSError, ValueError, KeyError, TypeError) as error:
                QMessageBox.warning(self, '无法打开会议', str(error))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def record_job_state(self, state):
        if self.job_dir and self.job_dir.exists():
            try:
                save_json(self.job_dir/'ui_status.json', {'status': state})
                if self.pages.currentIndex() == 1:
                    self.refresh_history()
            except OSError as error:
                self.log.appendPlainText('状态记录未保存：' + str(error))

    def refresh_models(self):
        root = Path(self.settings.get('models_dir', str(ROOT/'models')))
        overrides = {k: f.text().strip() for k, f in self.model_dirs.items()}
        for key, index in [('qwen', 0), ('sensevoice', 3), ('firered', 4), ('aligner', 1), ('speaker', 2)]:
            folder = location(root, key, overrides)
            missing = missing_files(root, key, overrides)
            total = len(CATALOG[key]['files'])
            self.model_status[index].setText('●  本地文件齐备' if not missing else f'待补全 · {total-len(missing)}/{total} 文件')
            self.model_status[index].setToolTip(str(folder) + ('\n缺少：' + '、'.join(missing) if missing else ''))
            self.model_locations[key].setText('当前目录：'+str(folder))
        self.model_path_label.setText('缓存位置：' + str(root))

    def open_model_link(self, url):
        if not QDesktopServices.openUrl(QUrl(url)):
            self.model_notice.setText('未能打开浏览器，请复制链接手动访问：'+url)
            self.model_notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def open_download_guide(self):
        path = ROOT/'模型下载指南.html'
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.model_notice.setText('请点击各模型的官方下载链接，按卡片列出的文件名下载到同一目录，然后选择该目录。')

    def choose_model_directory(self, key):
        if self.process:
            self.model_notice.setText('请等待当前任务结束，再修改模型目录。')
            return
        path = QFileDialog.getExistingDirectory(self, '选择 '+CATALOG[key]['name']+' 所在目录', self.model_dirs[key].text())
        if path:
            self.model_dirs[key].setText(path)
            self.save_preferences()
            self.refresh_models()

    def ready_for_models(self, engine, speakers=False):
        root = self.settings.get('models_dir', str(ROOT/'models'))
        overrides = {k: f.text().strip() for k, f in self.model_dirs.items()}
        missing = [CATALOG[k]['name'] for k in required_models(engine, speakers) if missing_files(root, k, overrides)]
        if missing:
            self.navigate(2)
            self.model_notice.setText('请先下载并选择目录：'+ '、'.join(missing)+'。文件齐备后回到工作台开始转写。')
            return False
        return True

    def open_models_folder(self):
        path = Path(self.settings.get('models_dir', str(ROOT/'models')))
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def discard_edits(self):
        return not (self.result and self.result.get('edited')) or QMessageBox.question(
            self, '未保存的修改', '切换会议会丢弃当前未保存的编辑，是否继续？') == QMessageBox.StandardButton.Yes
