from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import subprocess
from copy import deepcopy

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QUrl, QTimer
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QTableWidgetItem, QMessageBox

from .timeline import timecode, validate_segments, export_text
from .engine import save_json
from .ui import build_ui
from .workspace import WorkspaceBehavior
from .dialogue import DialogueBehavior, short_time
from .importing import ImportBehavior, MEDIA_EXTENSIONS, media_path
from .theme import COLORS
from .reading import prepare_project
from .documents import export_reading
from .diarization import speaker_status
from . import APP_NAME

ROOT = Path(__file__).resolve().parents[2]


def parse_time(text):
    parts = text.strip().replace(',', '.').split(':')
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) != 3:
        raise ValueError('时间请填写 HH:MM:SS.mmm 或秒数。')
    return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])


class Window(ImportBehavior, DialogueBehavior, WorkspaceBehavior, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(Path(__file__).parent/'assets/app.ico')))
        self.setAcceptDrops(True)
        self.result = None
        self.view_kind = 'reading'
        self.source = None
        self.process = None
        self.buffer = b''
        self.stop_at = None
        self.cancelled = False
        self.job_dir = None
        self.settings = {}
        local = ROOT / 'runtime.local.json'
        if local.exists():
            self.settings = json.loads(local.read_text(encoding='utf-8'))
        self.preferences = {}
        try:
            self.preferences = json.loads((ROOT/'ui.local.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        self.notes_requested = True
        self.playback_segments = None
        self.active_row = -1
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        build_ui(self)
        self.player.positionChanged.connect(self.on_position)
        self.player.durationChanged.connect(self.on_duration)
        self.player.playbackStateChanged.connect(self.sync_playback)
        self.player.errorOccurred.connect(self.media_error)
        self.device.setCurrentIndex(max(0, self.device.findData(self.preferences.get('device', 'auto'))))
        self.hotwords.setText(self.preferences.get('hotwords', ''))
        self.diarization_enabled.setChecked(self.preferences.get('diarization', False))
        self.speaker_count.setValue(self.preferences.get('num_speakers', 0))
        self.follow_playback.setChecked(self.preferences.get('follow_playback', True))
        self.engine.setCurrentIndex(max(0, self.engine.findData(self.preferences.get('engine', 'qwen'))))
        for key, field in self.model_dirs.items():
            field.setText(self.preferences.get('model_dirs', {}).get(key, ''))
            field.editingFinished.connect(self.save_preferences)
        self.engine.currentIndexChanged.connect(self.engine_changed)
        self.device.currentIndexChanged.connect(self.save_preferences)
        self.hotwords.editingFinished.connect(self.save_preferences)
        self.diarization_enabled.toggled.connect(self.save_preferences)
        self.speaker_count.valueChanged.connect(self.save_preferences)
        self.follow_playback.toggled.connect(self.save_preferences)
        self.set_busy(False)
        self.adapt_layout()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        QApplication.instance().installEventFilter(self)

    def set_audio(self, path):
        if self.process:
            return
        path = Path(path)
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            self.status.setText('请选择本机上的音频或视频文件。')
            return False
        if self.result:
            if self.result.get('edited') and QMessageBox.question(self, '未保存的修改', '导入新音频会清空当前结果，是否继续？') != QMessageBox.StandardButton.Yes:
                return
            self.result = None
            self.table.setRowCount(0)
            self.set_busy(False)
        self.source = path.resolve()
        self.file_label.setText(str(self.source))
        self.player.setSource(QUrl.fromLocalFile(str(self.source)))
        self.stop_at = None
        self.playback_segments = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.search.clear()
        self.filter_transcript()
        self.transcript_stack.setCurrentIndex(0)
        self.update_heading()
        self.set_state('ready', '待转写')
        self.empty_title.setText('录音已就绪。')
        self.empty_description.setText(f'{self.source.name}\n点击上方“开始转写”，即可生成对话文字。')
        self.status.setText('录音已就绪 · 可在设置中选择计算设备和词汇提示')
        self.set_busy(False)
        self.navigate(0)
        return True

    def choose(self):
        formats = ' '.join('*'+ext for ext in sorted(MEDIA_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, '选择录音', '', f'音频与视频 ({formats});;所有文件 (*)')
        if path:
            self.set_audio(path)

    def dragEnterEvent(self, event):
        try:
            media_path(event.mimeData())
        except (ValueError, OSError):
            event.ignore()
            return
        if not self.process:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.drop_feedback(False)
        if self.import_mime(event.mimeData()):
            event.acceptProposedAction()

    def start(self):
        if not self.source or self.process:
            return
        if not self.ready_for_models(self.engine.currentData(), self.diarization_enabled.isChecked()):
            return
        if self.result and self.result.get('edited'):
            if QMessageBox.question(self, '开始新任务', '当前修改尚未保存。开始新任务将清空表格，是否继续？') != QMessageBox.StandardButton.Yes:
                return
        self.result = None
        self.playback_segments = None
        self.table.setRowCount(0)
        self.search.clear()
        self.filter_transcript()
        self.log.clear()
        self.progress.setValue(0)
        self.stop_at = None
        self.player.pause()
        self.job_dir = ROOT / 'jobs' / time.strftime('%Y%m%d-%H%M%S')
        self.job_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg = self.settings.get('ffmpeg')
        if not ffmpeg or not Path(ffmpeg).is_file():
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        config = {'audio': str(self.source), 'job_dir': str(self.job_dir), 'ffmpeg': ffmpeg,
                  'engine': self.engine.currentData(),
                  'asr_model_dir': self.model_dirs[self.engine.currentData()].text().strip(),
                  'aligner_model_dir': self.model_dirs['aligner'].text().strip(),
                  'speaker_model_dir': self.model_dirs['speaker'].text().strip(),
                  'models_dir': self.settings.get('models_dir', str(ROOT / 'models')),
                  'hotwords': self.hotwords.text().strip(), 'device': self.device.currentData(), 'language': 'Chinese',
                  'diarization': self.diarization_enabled.isChecked(), 'num_speakers': self.speaker_count.value()}
        self.launch_worker(config)

    def diarize_existing(self):
        if not self.result or self.process or not self.source or not self.source.is_file():
            return
        if not self.ready_for_models('speaker'):
            return
        try:
            self.sync_view()
        except ValueError as error:
            QMessageBox.warning(self, '请检查时间', str(error))
            return
        self.job_dir = ROOT/'jobs'/(time.strftime('%Y%m%d-%H%M%S')+'-speakers')
        self.job_dir.mkdir(parents=True, exist_ok=True)
        snapshot = dict(self.result, segments=deepcopy(self.result['reading_paragraphs']))
        save_json(self.job_dir/'source_project.json', snapshot)
        ffmpeg = self.settings.get('ffmpeg')
        if not ffmpeg or not Path(ffmpeg).is_file():
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        config = {'task': 'diarization', 'source_project': str(self.job_dir/'source_project.json'),
                  'audio': str(self.source), 'job_dir': str(self.job_dir), 'ffmpeg': ffmpeg,
                  'models_dir': self.settings.get('models_dir', str(ROOT/'models')),
                  'speaker_model_dir': self.model_dirs['speaker'].text().strip(),
                  'num_speakers': self.speaker_count.value()}
        self.log.clear()
        self.stop_at = None
        self.player.pause()
        self.launch_worker(config)

    def launch_worker(self, config):
        save_json(self.job_dir / 'config.json', config)
        self.buffer = b''
        self.cancelled = False
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONPATH', str(ROOT / 'src'))
        env.insert('PYTHONIOENCODING', 'utf-8')
        env.insert('HF_HUB_DISABLE_TELEMETRY', '1')
        self.process.setProcessEnvironment(env)
        self.process.setProgram(sys.executable.replace('pythonw.exe', 'python.exe'))
        self.process.setArguments(['-u', '-m', 'transcriber.worker', '--config', str(self.job_dir / 'config.json')])
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.set_busy(True)
        self.started = time.monotonic()
        self.stage_text = '启动识别进程'
        self.timer.start()
        self.record_job_state('处理中')
        self.process.start()

    def set_busy(self, busy):
        self.diarize_button.setEnabled(not busy and self.result is not None and self.source is not None and self.source.is_file())
        self.diarization_enabled.setEnabled(not busy)
        self.speaker_count.setEnabled(not busy)
        self.view_mode.setEnabled(not busy and self.result is not None)
        for control in [self.choose_button, self.paste_button, self.empty_paste, self.empty_import, self.load_button, self.hotwords, self.device]:
            control.setEnabled(not busy)
        self.engine.setEnabled(not busy)
        for field in self.model_dirs.values():
            field.setEnabled(not busy)
        self.update_engine_controls(busy)
        self.run_button.setEnabled(not busy and self.source is not None and self.source.is_file())
        self.run_button.setVisible(not busy)
        self.run_button.setText('重新转写' if self.result else '开始转写')
        self.run_button.setObjectName('' if self.result else 'primary')
        self.run_button.style().unpolish(self.run_button)
        self.run_button.style().polish(self.run_button)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.table.setEnabled(not busy)
        self.export_button.setEnabled(not busy and self.result is not None)
        for action in self.export_buttons:
            action.setEnabled(not busy and self.result is not None)
        playable = self.source is not None and self.source.is_file()
        self.transport.setEnabled(playable and not busy)
        self.seek_slider.setEnabled(playable and not busy)
        self.play_button.setEnabled(playable and self.result is not None and not busy)
        if busy:
            self.set_state('busy', '处理中')
            self.wait_title.setText('正在整理你的会议')
            self.wait_note.setText('任务在后台运行，可以随时查看日志或取消。')
            self.transcript_stack.setCurrentIndex(2)

    def media_error(self, error, text):
        self.log.appendPlainText('播放错误：' + text)
        self.status.setText('音频无法播放：' + text)

    def tick(self):
        self.status.setText(f'{self.stage_text} · 已用时 {int(time.monotonic()-self.started)} 秒')

    def read_stdout(self):
        if not self.process:
            return
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            text = line.decode('utf-8', errors='replace').strip()
            if not text:
                continue
            with (self.job_dir/'events.jsonl').open('a', encoding='utf-8') as f:
                f.write(text+'\n')
            try:
                event = json.loads(text)
                self.log.appendPlainText(event['message'])
                if event['stage'] != 'text':
                    self.stage_text = event['message'].splitlines()[-1]
                p = event.get('progress')
                if p is not None:
                    self.progress.setRange(0, 100)
                    self.progress.setValue(int(p))
                elif event['stage'] in ['download', 'speaker_download']:
                    self.progress.setRange(0, 0)
                if event['stage'] == 'done':
                    self.load_result(event['message'])
            except (ValueError, KeyError, TypeError):
                self.log.appendPlainText(text)

    def read_stderr(self):
        if not self.process:
            return
        text = bytes(self.process.readAllStandardError()).decode('utf-8', errors='replace')
        with (self.job_dir/'runtime.log').open('a', encoding='utf-8') as f:
            f.write(text)
        self.log.appendPlainText(text[-2500:])

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText('无法启动 Python，请检查测试环境。')
            self.finished(1, QProcess.ExitStatus.CrashExit)

    def finished(self, code, status):
        self.read_stdout()
        self.read_stderr()
        self.timer.stop()
        if self.process:
            self.process.deleteLater()
        self.process = None
        self.set_busy(False)
        self.progress.setRange(0, 100)
        if self.cancelled:
            self.set_state('ready', '已取消')
            self.record_job_state('已取消')
            self.transcript_stack.setCurrentIndex(1 if self.result else 0)
            self.status.setText('任务已取消，已完成阶段的中间结果保留在 jobs 文件夹。')
        elif code == 0 and self.result:
            self.set_state('done', '转写完成')
            self.record_job_state('已完成')
            elapsed = self.result.get('last_operation_seconds', self.result.get('elapsed_seconds'))
            timing = f' · 用时 {elapsed:.1f} 秒' if elapsed is not None else ''
            self.status.setText(f"完成 · {len(self.result['segments'])} 段{timing} · {speaker_status(self.result)}")
        else:
            self.set_state('failed', '处理失败')
            self.record_job_state('失败')
            self.wait_title.setText('这次转写未能完成')
            self.wait_note.setText('查看任务日志中的原因，调整设置后可重新转写。')
            self.transcript_stack.setCurrentIndex(1 if self.result else 2)
            self.log.show()
            self.status.setText('处理失败 · 已完成阶段的中间结果保留在任务目录。')

    def cancel(self):
        if self.process:
            self.cancelled = True
            pid = self.process.processId()
            if os.name == 'nt' and pid:
                # Stop only this job's process tree, including its FFmpeg child.
                try:
                    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], timeout=5,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                except (OSError, subprocess.TimeoutExpired):
                    self.process.kill()
            else:
                self.process.kill()
            self.cancel_button.setEnabled(False)
            self.stage_text = '正在取消任务'

    def load_result(self, path):
        if not self.process and not self.discard_edits():
            return
        result = json.loads(Path(path).read_text(encoding='utf-8'))
        validate_segments(result['segments'], result.get('duration'))
        result = prepare_project(result)
        self.view_kind = 'reading'
        self.view_mode.blockSignals(True)
        self.view_mode.setCurrentIndex(0)
        self.view_mode.blockSignals(False)
        self.result = result
        self.stop_at = None
        self.player.pause()
        self.playback_segments = None
        self.active_row = -1
        self.search.clear()
        self.source = Path(result['audio'])
        self.populate_segments(result['segments'])
        self.transcript_stack.setCurrentIndex(1)
        self.update_heading()
        self.on_duration(round(result.get('duration', 0)*1000))
        self.set_state('done', '转写完成')
        self.progress.setValue(100)
        self.remember_project(path)
        self.player.setSource(QUrl.fromLocalFile(result['audio']))
        if not self.process:
            self.set_busy(False)
            self.status.setText(f"已载入 {len(result['segments'])} 段 · {speaker_status(result)}")

    def populate_segments(self, segments):
        self.table.blockSignals(True)
        self.table.setRowCount(len(segments))
        for i, segment in enumerate(segments):
            for j, value in enumerate([timecode(segment['start']), timecode(segment['end']), segment['text']]):
                item = QTableWidgetItem(value)
                if j < 2:
                    font = QFont('Cascadia Mono')
                    font.setPixelSize(12)
                    item.setFont(font)
                    item.setForeground(QColor(COLORS['primary']))
                    item.setToolTip('点击跳转 · 双击编辑，格式 HH:MM:SS.mmm')
                else:
                    font = QFont('Microsoft YaHei UI')
                    font.setPixelSize(16)
                    item.setFont(font)
                    item.setData(Qt.ItemDataRole.UserRole, segment.get('speaker'))
                    item.setData(Qt.ItemDataRole.UserRole+1, deepcopy(segment))
                    item.setToolTip('点击左上角时间回放 · 双击编辑 · 右键合并或拆分')
                self.table.setItem(i, j, item)
        self.table.blockSignals(False)
        self.resize_rows()
        self.filter_transcript()

    def open_result(self):
        if self.process:
            return
        path, _ = QFileDialog.getOpenFileName(self, '打开转写项目', str(ROOT), '项目文件 (*.json)')
        if path:
            try:
                self.load_result(path)
            except Exception as e:
                QMessageBox.warning(self, '无法打开', str(e))

    def mark_edited(self, item):
        if self.result:
            self.result['edited'] = True
            self.playback_segments = None
            self.set_state('ready', '有未保存的修改')
            self.filter_transcript()
            self.resize_rows()

    def current_segments(self):
        result = []
        for i in range(self.table.rowCount()):
            saved = deepcopy(self.table.item(i, 2).data(Qt.ItemDataRole.UserRole+1) or {})
            values = {'start': parse_time(self.table.item(i, 0).text()),
                      'end': parse_time(self.table.item(i, 1).text()), 'text': self.table.item(i, 2).text().strip()}
            for key in ('start', 'end'):
                if key in saved and values[key] == round(saved[key], 3):
                    values[key] = saved[key]  # Display rounding is not a timing edit.
            if saved.get('source_spans') and values['text'] != saved.get('text'):
                saved['alignment_status'] = 'text_edited'
            if saved.get('source_spans') and any(values[k] != saved.get(k) for k in ('start', 'end')):
                saved['timing_basis'] = 'manual'
            saved.update(values)
            saved.pop('speaker', None)
            result.append(saved)
            speaker = self.table.item(i, 2).data(Qt.ItemDataRole.UserRole)
            if speaker:
                result[-1]['speaker'] = speaker
        validate_segments(result, self.result.get('duration') if self.result else None)
        return result

    def sync_view(self):
        if self.result:
            segments = self.current_segments()
            key = 'reading_paragraphs' if self.view_kind == 'reading' else 'subtitle_segments'
            self.result[key] = deepcopy(segments)
            self.result['segments'] = segments

    def switch_view(self, index):
        if not self.result:
            return
        try:
            self.sync_view()
        except ValueError as error:
            self.view_mode.blockSignals(True)
            self.view_mode.setCurrentIndex(0 if self.view_kind == 'reading' else 1)
            self.view_mode.blockSignals(False)
            QMessageBox.warning(self, '请检查当前时间', str(error))
            return
        self.view_kind = 'reading' if index == 0 else 'subtitle'
        key = 'reading_paragraphs' if index == 0 else 'subtitle_segments'
        self.result['segments'] = deepcopy(self.result[key])
        self.player.pause()
        self.stop_at = None
        self.playback_segments = None
        self.active_row = -1
        self.populate_segments(self.result['segments'])
        self.status.setText('阅读版用于 TXT / DOCX / PDF；字幕版用于 SRT / VTT。两版编辑分别保存。')

    def play_selected(self):
        if not self.result:
            return
        row = self.table.currentRow()
        if row < 0:
            row = 0
            self.table.selectRow(row)
        try:
            segment = self.current_segments()[row]
            self.stop_at = round(segment['end']*1000)
            self.player.setPosition(round(segment['start']*1000))
            self.player.play()
        except Exception as e:
            QMessageBox.warning(self, '请检查时间', str(e))

    def on_position(self, position):
        self.position_label.setText(short_time(position/1000))
        if not self.seek_slider.isSliderDown():
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(position)
            self.seek_slider.blockSignals(False)
        self.highlight_position(position)
        if self.stop_at is not None and position >= self.stop_at:
            self.player.pause()
            self.stop_at = None

    def export(self, kind):
        try:
            self.sync_view()
            path, _ = QFileDialog.getSaveFileName(self, '导出结果', str(ROOT / f'{Path(self.result["audio"]).stem}.{kind}'), f'{kind.upper()} (*.{kind})')
            if not path:
                return
            if not Path(path).suffix:
                path += '.'+kind
            if kind == 'json':
                data = dict(self.result, segments=deepcopy(self.result['reading_paragraphs']), edited=False)
                save_json(path, data)
                self.result['edited'] = False
                self.remember_project(path)
                self.set_state('done', '修改已保存')
            elif kind in ('txt', 'docx', 'pdf'):
                export_reading(self.result, path, kind)
            else:
                Path(path).write_text(export_text(self.result['subtitle_segments'], kind), encoding='utf-8')
            self.status.setText('已保存：'+path)
        except Exception as e:
            QMessageBox.warning(self, '无法导出', str(e))

    def closeEvent(self, event):
        if self.process:
            self.cancel()
            if self.process:
                self.process.waitForFinished(3000)
        if self.result and self.result.get('edited'):
            if QMessageBox.question(self, '未保存的修改', '修改尚未保存。确认关闭？') != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.player.stop()
        self.player.setSource(QUrl())
        QApplication.instance().removeEventFilter(self)
        event.accept()


def main():
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('wwh.SpeechAssistant.Desktop')
    app = QApplication(sys.argv)
    window = Window()
    if len(sys.argv) > 1:
        if sys.argv[1].lower().endswith('.json'):
            window.load_result(sys.argv[1])
        else:
            window.set_audio(sys.argv[1])
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
