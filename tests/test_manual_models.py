import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from transcriber.app import Window
from transcriber.asr_backends import ensure_model
from transcriber.engine import model_path, ASR_REPO
from transcriber.diarization import ensure_models
from transcriber.model_catalog import CATALOG, missing_files


@pytest.mark.parametrize('key', ['sensevoice', 'firered'])
def test_no_implicit_asr_download(tmp_path, key):
    with patch('urllib.request.urlopen') as network:
        with pytest.raises(FileNotFoundError, match='官方下载链接'):
            ensure_model({'models_dir':str(tmp_path)}, key, lambda *a: None)
        network.assert_not_called()


def test_qwen_and_speakers_missing_do_not_download(tmp_path):
    with patch('urllib.request.urlopen') as network:
        with pytest.raises(FileNotFoundError, match='官方下载链接'):
            model_path(ASR_REPO, tmp_path, lambda *a: None)
        with pytest.raises(FileNotFoundError, match='手动下载'):
            ensure_models(tmp_path, lambda *a: None)
        network.assert_not_called()


def test_ui_missing_models_keeps_current_document_and_opens_management(tmp_path):
    app = QApplication.instance() or QApplication([])
    with patch('transcriber.app.ROOT',tmp_path),patch('transcriber.workspace.ROOT',tmp_path):
        w=Window()
        try:
            w.source=tmp_path/'test.wav';w.source.touch()
            w.result={'edited':False,'title':'已有结果'}
            with patch.object(w,'launch_worker') as launch:
                w.start()
            launch.assert_not_called()
            assert w.result['title']=='已有结果'
            assert w.pages.currentIndex()==2
            assert 'Qwen3-ASR' in w.model_notice.text()
            assert 'Qwen3-ForcedAligner' in w.model_notice.text()
            assert not (tmp_path/'jobs').exists()
        finally:
            w.result=None;w.close()


def test_choose_directory_and_download_link(tmp_path):
    app=QApplication.instance() or QApplication([])
    with patch('transcriber.app.ROOT',tmp_path),patch('transcriber.workspace.ROOT',tmp_path):
        w=Window()
        try:
            folder=tmp_path/'用户 下载模型';folder.mkdir()
            for name in CATALOG['sensevoice']['files']:
                (folder/name).write_bytes(b'present')
            with patch('transcriber.workspace.QFileDialog.getExistingDirectory',return_value=str(folder)):
                w.choose_model_directory('sensevoice')
            assert w.model_dirs['sensevoice'].text()==str(folder)
            assert w.ready_for_models('sensevoice')
            assert '齐备' in w.model_status[3].text()
            url=CATALOG['sensevoice']['links'][0][1]
            with patch('transcriber.workspace.QDesktopServices.openUrl',return_value=True) as browser:
                w.open_model_link(url)
            browser.assert_called_once_with(QUrl(url))
            (folder/'tokens.txt').write_bytes(b'')
            assert missing_files(tmp_path,'sensevoice',{'sensevoice':str(folder)})==['tokens.txt']
        finally:
            w.close()
