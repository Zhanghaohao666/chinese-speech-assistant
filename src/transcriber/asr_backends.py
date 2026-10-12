"""ASR selection, model acquisition and native capability adapters."""
from pathlib import Path
import gc
import json
import os
import tarfile
import time
import urllib.request

SENSE_FOLDER = 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'
FIRE_REPO = 'FireRedTeam/FireRedASR2-AED'
FIRE_REVISION = '2304afed56eacfee6256dee5937ed22ffa0b64ec'
FIRE_FILES = ['model.pth.tar', 'cmvn.ark', 'dict.txt', 'train_bpe1000.model']
QWEN_FILES = ['config.json', 'model.safetensors', 'processor_config.json', 'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja']
ENGINES = {
    'sensevoice': {'label':'轻量快转 · SenseVoiceSmall INT8', 'name':'SenseVoiceSmall / sherpa-onnx INT8',
                  'folder':SENSE_FOLDER, 'files':['model.int8.onnx','tokens.txt'],
                  'note':'固定 CPU · 不加载强制对齐模型；显示音频块区间，原生 token 起点保存在 JSON。词汇提示不适用。'},
    'qwen': {'label':'高质量 A · Qwen3-ASR-1.7B', 'name':'Qwen3-ASR-1.7B + Qwen3-ForcedAligner-0.6B',
             'folder':'Qwen3-ASR-1.7B-hf', 'files':QWEN_FILES,
             'note':'保留现有 GPU / CPU 识别与字词对齐，复用已下载的 Qwen 缓存。支持词汇提示。'},
    'firered': {'label':'高质量 B · FireRedASR2-AED', 'name':'FireRedASR2-AED',
                'folder':'FireRedASR2-AED', 'files':FIRE_FILES,
                'note':'第二代 AED · CPU FP32 / GPU BF16 或 FP16；使用自身 CTC 对齐。缺失时只显示音频块区间。词汇提示不适用。'},
}


def engine_id(config):
    key = config.get('engine', 'qwen')
    if key not in ENGINES:
        raise ValueError(f'未知识别引擎：{key}')
    return key


def cached_path(config, key):
    return Path(config.get('asr_model_dir') or Path(config['models_dir'])/ENGINES[key]['folder'])


def local_model(config, key, emit):
    if key == 'qwen' and not config.get('asr_model_dir'):
        from .engine import model_path, ASR_REPO
        return model_path(ASR_REPO, config['models_dir'], emit)
    return str(ensure_model(config, key, emit))


def ensure_model(config, key, emit):
    folder = cached_path(config, key)
    files = ENGINES[key]['files']
    if all((folder/f).is_file() for f in files):
        return folder
    if config.get('asr_model_dir'):
        raise FileNotFoundError(f'指定的本地模型目录不完整：{folder}；需要 {", ".join(files)}')
    if not config.get('allow_model_download', False):
        raise FileNotFoundError(f'{ENGINES[key]["name"]} 尚未准备好。请在“模型管理”点击官方下载链接，下载并配置本地目录：{folder}')
    folder.mkdir(parents=True, exist_ok=True)
    emit('download', f'下载 {ENGINES[key]["name"]}，缓存位置：{folder}', None)
    if key == 'firered':
        from huggingface_hub import snapshot_download
        snapshot_download(FIRE_REPO, revision=FIRE_REVISION, local_dir=str(folder),
                          allow_patterns=FIRE_FILES+['README.md'], max_workers=2)
    elif key == 'sensevoice':
        archive = folder/'download.tar.bz2.part'
        url = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/'+SENSE_FOLDER+'.tar.bz2'
        with urllib.request.urlopen(url, timeout=60) as response, archive.open('wb') as target:
            size, last = 0, time.monotonic()
            while block := response.read(1024*1024):
                target.write(block)
                size += len(block)
                if time.monotonic()-last >= 2:
                    emit('download', f'SenseVoice INT8 已下载 {size/1024**2:.1f} MB', None)
                    last = time.monotonic()
        with tarfile.open(archive) as package:
            for member in package.getmembers():
                name = Path(member.name).name
                if member.isfile() and name in files+['LICENSE','README.md']:
                    target = folder/(name+'.part')
                    target.write_bytes(package.extractfile(member).read())
                    target.replace(folder/name)
        archive.unlink()
    if not all((folder/f).is_file() for f in files):
        raise FileNotFoundError(f'下载后模型文件仍不完整：{folder}')
    return folder


class SenseVoiceEngine:
    """INT8 CPU only. Do not convert start-only token times into word intervals."""
    def load(self, config, emit):
        import sherpa_onnx
        if config.get('device') == 'cuda':
            emit('device', '轻量快转固定使用 CPU INT8；GPU 选项仅适用于高质量引擎。', None)
        folder = ensure_model(config, 'sensevoice', emit)
        emit('load_asr', '加载 SenseVoiceSmall · sherpa-onnx INT8 · CPU', 8)
        self.model = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(folder/'model.int8.onnx'), tokens=str(folder/'tokens.txt'),
            num_threads=min(4,os.cpu_count() or 1), provider='cpu', language='zh', use_itn=True)
        self.execution = {'device':'cpu','dtype':'int8','backend':'sherpa-onnx',
                          'version':sherpa_onnx.__version__,'threads':min(4,os.cpu_count() or 1),'model_dir':str(folder)}

    def transcribe(self, path, uttid):
        import soundfile as sf
        samples, rate = sf.read(path, dtype='float32')
        stream = self.model.create_stream()
        stream.accept_waveform(rate, samples)
        self.model.decode_stream(stream)
        result = stream.result
        raw = json.loads(str(result))
        return {'text':raw['text'], 'raw':raw, 'timestamps':None,
                'timing_basis':'audio_chunk', 'token_starts':raw.get('timestamps',[])}

    def close(self):
        self.model = None
        gc.collect()


class FireRedEngine:
    """Second-generation AED; GPU half precision, CPU float32."""
    def load(self, config, emit):
        import torch
        from importlib.metadata import version
        if version('sentencepiece') != '0.2.0':
            raise RuntimeError('FireRed Windows 已验证 sentencepiece==0.2.0；0.2.1 曾造成原生崩溃。请按锁定依赖安装后重试。')
        from .vendor.fireredasr2.asr import FireRedAsr2, FireRedAsr2Config
        requested = config.get('device','auto')
        gpu = requested != 'cpu' and torch.cuda.is_available()
        if requested == 'cuda' and not gpu:
            raise RuntimeError('没有可用的 CUDA。请改选自动或 CPU。')
        if not gpu:
            torch.set_num_threads(min(8,os.cpu_count() or 1))
        folder = ensure_model(config, 'firered', emit)
        precision = ('BF16' if torch.cuda.is_bf16_supported() else 'FP16') if gpu else 'FP32'
        emit('load_asr', f'加载 FireRedASR2-AED · {"CUDA" if gpu else "CPU"} · {precision}', 8)
        self.model = FireRedAsr2.from_pretrained('aed', str(folder), FireRedAsr2Config(
            use_gpu=gpu, use_half=gpu, beam_size=3, nbest=1, return_timestamp=True))
        param = next(self.model.model.parameters())
        self.execution = {'device':str(param.device), 'dtype':str(param.dtype), 'backend':'FireRedASR2-AED / PyTorch',
                          'torch':torch.__version__, 'model_dir':str(folder),
                          'model_revision':'local_unverified' if config.get('asr_model_dir') else FIRE_REVISION,
                          'code_revision':'4e7d9aaf4482a47cec1724807026b9b151926eb5'}

    def transcribe(self, path, uttid):
        results = self.model.transcribe([uttid],[str(path)])
        if not results or 'dur_s' not in results[0]:
            raise RuntimeError('FireRedASR2-AED 未返回有效推理结果；请查看此前的特征提取或解码错误日志。')
        raw = results[0]
        stamps = [{'text':token,'start_time':start,'end_time':end} for token,start,end in raw.get('timestamp',[])]
        return {'text':raw['text'],'raw':raw,'timestamps':stamps,
                'timing_basis':'firered_ctc' if stamps else 'audio_chunk'}

    def close(self):
        self.model = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def make_backend(key):
    if key == 'qwen':
        from .qwen_backend import QwenEngine
        return QwenEngine()
    if key == 'sensevoice':
        return SenseVoiceEngine()
    if key == 'firered':
        return FireRedEngine()
    raise ValueError(f'未知识别引擎：{key}')
