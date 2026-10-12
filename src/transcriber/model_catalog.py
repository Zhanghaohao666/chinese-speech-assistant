"""Manual download links and local readiness; never downloads weights."""
from pathlib import Path
from .asr_backends import ENGINES, QWEN_FILES, FIRE_REPO, FIRE_REVISION, SENSE_FOLDER
from .engine import ASR_REPO, ALIGN_REPO, REVISIONS
from .diarization import SEGMENTATION_URL, EMBEDDING_URL

CATALOG = {
    'qwen': {'name': 'Qwen3-ASR-1.7B', 'folder': ENGINES['qwen']['folder'], 'files': QWEN_FILES,
             'links': [('官方文件下载', f'https://huggingface.co/{ASR_REPO}/tree/{REVISIONS[ASR_REPO]}')],
             'help': '约 4.08 GB。下载下列 6 个文件到同一目录；使用 Qwen 还需下方对齐器。'},
    'aligner': {'name': 'Qwen3-ForcedAligner-0.6B', 'folder': 'Qwen3-ForcedAligner-0.6B-hf', 'files': QWEN_FILES,
                'links': [('官方文件下载', f'https://huggingface.co/{ALIGN_REPO}/tree/{REVISIONS[ALIGN_REPO]}')],
                'help': '约 1.84 GB，仅 Qwen 需要。下载下列 6 个文件到同一目录。'},
    'sensevoice': {'name': 'SenseVoiceSmall INT8', 'folder': SENSE_FOLDER, 'files': ENGINES['sensevoice']['files'],
                   'links': [('下载 INT8 压缩包', 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/'+SENSE_FOLDER+'.tar.bz2')],
                   'help': '权重约 239 MB。解压 tar.bz2，选择直接包含 model.int8.onnx 和 tokens.txt 的目录。'},
    'firered': {'name': 'FireRedASR2-AED', 'folder': ENGINES['firered']['folder'], 'files': ENGINES['firered']['files'],
                'links': [('官方文件下载', f'https://huggingface.co/{FIRE_REPO}/tree/{FIRE_REVISION}')],
                'help': '约 4.73 GB。下载下列 4 个文件到同一目录；不要下载第一代 FireRed。'},
    'speaker': {'name': '说话人分离（可选）', 'folder': 'speaker-diarization', 'files': ['segmentation.onnx', 'embedding.onnx'],
                'links': [('下载分段模型', SEGMENTATION_URL), ('下载声纹模型', EMBEDDING_URL)],
                'help': '合计约 45 MB。分段压缩包解压后将 model.onnx 改名为 segmentation.onnx；声纹文件改名为 embedding.onnx，放在同一目录。不使用分人可不下载。'},
}


def location(root, key, overrides=None):
    return Path((overrides or {}).get(key) or Path(root)/CATALOG[key]['folder'])


def missing_files(root, key, overrides=None):
    folder = location(root, key, overrides)
    return [name for name in CATALOG[key]['files'] if not (folder/name).is_file() or (folder/name).stat().st_size == 0]


def required_models(engine, speakers=False):
    return [engine] + (['aligner'] if engine == 'qwen' else []) + (['speaker'] if speakers else [])
