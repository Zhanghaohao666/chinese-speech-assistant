import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

import pytest
from PySide6.QtWidgets import QApplication
from transcriber.asr_backends import engine_id, ensure_model
from transcriber.engine import native_chunk_segments, run_job
from transcriber.app import Window
from transcriber.reading import reading_document, prepare_project


def test_default_and_invalid_selection():
    assert engine_id({}) == 'qwen'
    with pytest.raises(ValueError, match='未知识别引擎'):
        engine_id({'engine': 'not-an-engine'})


def test_custom_directory_failure_never_downloads(tmp_path):
    with patch('urllib.request.urlopen') as download:
        with pytest.raises(FileNotFoundError, match='目录不完整'):
            ensure_model({'asr_model_dir': str(tmp_path)}, 'sensevoice', lambda *args: None)
        download.assert_not_called()


def test_coarse_time_preserves_text_without_manufacturing_words():
    chunk = {'text': '完整的话。下一句话。', 'offset': 10, 'core_start': 10, 'core_end': 20,
             'token_starts': [1, 2], 'timestamps': None}
    segments, words, _, warning = native_chunk_segments(chunk, 20)
    assert words == [] and warning
    assert segments == [{'text': chunk['text'], 'start': 10, 'end': 20, 'timing_basis': 'audio_chunk'}]


@pytest.mark.parametrize('stamps', [
    [{'text': '错误', 'start_time': 0, 'end_time': 1}],
    [{'text': '你好', 'start_time': 0, 'end_time': 99}],
    [{'text': '你好', 'start_time': float('nan'), 'end_time': 1}],
])
def test_invalid_native_timing_falls_back_without_losing_text(stamps):
    segments, words, _, warning = native_chunk_segments(
        {'text': '你好。', 'offset': 10, 'core_start': 10, 'core_end': 20, 'timestamps': stamps}, 30)
    assert words == [] and warning
    assert segments[0]['text'] == '你好。'
    assert segments[0]['timing_basis'] == 'audio_chunk'


def test_worker_releases_backend_on_load_and_inference_failure(tmp_path):
    audio = tmp_path/'audio.wav'
    audio.touch()
    for stage in ('load', 'transcribe'):
        backend = Mock()
        backend.execution = {'device': 'cpu', 'dtype': 'int8'}
        getattr(backend, stage).side_effect = RuntimeError('模拟错误')
        with patch('transcriber.engine.prepare_audio'), patch('transcriber.engine.split_audio', return_value=(2, [{'path': str(audio)}])), \
                patch('transcriber.asr_backends.make_backend', return_value=backend):
            with pytest.raises(RuntimeError, match='模拟错误'):
                run_job({'engine': 'sensevoice', 'job_dir': str(tmp_path), 'audio': str(audio), 'ffmpeg': 'unused'}, lambda *a: None)
        backend.close.assert_called_once()


def test_selection_persists_and_worker_receives_selected_parameters(tmp_path):
    app = QApplication.instance() or QApplication([])
    with patch('transcriber.app.ROOT', tmp_path), patch('transcriber.workspace.ROOT', tmp_path):
        window = Window()
        try:
            assert window.engine.currentData() == 'qwen'
            window.engine.setCurrentIndex(window.engine.findData('firered'))
            window.model_dirs['firered'].setText(str(tmp_path/'本地模型'))
            window.save_preferences()
            assert not window.hotwords.isEnabled()
            assert window.device.isEnabled()
            audio = tmp_path/'test.wav'
            audio.touch()
            window.source = audio
            with patch.object(window, 'launch_worker') as launch, patch.object(window, 'ready_for_models', return_value=True):
                window.start()
            config = launch.call_args.args[0]
            assert config['engine'] == 'firered'
            assert config['asr_model_dir'] == str(tmp_path/'本地模型')
            window.set_busy(True)
            assert not window.engine.isEnabled()
            assert not window.model_dirs['firered'].isEnabled()
            window.set_busy(False)
            window.engine.setCurrentIndex(window.engine.findData('sensevoice'))
            assert not window.device.isEnabled()
            assert json.loads((tmp_path/'ui.local.json').read_text(encoding='utf-8'))['engine'] == 'sensevoice'
        finally:
            window.close()


def test_reading_exports_warn_about_coarse_time():
    project = prepare_project({'audio': 'test.wav', 'segments': [{'start': 0, 'end': 10, 'text': '你好。'}],
                               'timing_note': '音频块时间，非精确句子起止。'})
    assert dict(reading_document(project)['metadata'])['时间说明'] == project['timing_note']
