"""Local acoustic speaker diarization; labels do not identify real people."""
from copy import deepcopy
from pathlib import Path
import hashlib
import os
import tarfile
import time
import urllib.request

from .reading import _stream, _word_map, join_text
from .timeline import validate_segments

BASE_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
SEGMENTATION_URL = BASE_URL+'speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2'
EMBEDDING_URL = BASE_URL+'speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx'
HASHES = {'segmentation.onnx': '220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079',
          'embedding.onnx': '1a331345f04805badbb495c775a6ddffCDD1a732567d5ec8b3d5749e3c7a5e4b'.lower(),
          'segmentation.tar.bz2': '24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488'}
UNKNOWN = '未确定'
OVERLAP = '交界待核对'


def name_speaker_clusters(raw_turns, num_speakers=0):
    """Do not count tiny automatic clusters as confidently distinct people."""
    durations = {}
    for turn in raw_turns:
        key = turn['speaker']
        durations[key] = durations.get(key, 0)+turn['end']-turn['start']
    threshold = 0 if num_speakers else min(8., max(.5, sum(durations.values())*.02))
    names, speakers, candidates = {}, 0, 0
    for turn in raw_turns:
        key = turn['speaker']
        if key not in names:
            if durations[key] >= threshold:
                speakers += 1
                names[key] = f'说话人 {speakers}'
            else:
                candidates += 1
                names[key] = f'待确认声源 {candidates}'
    turns = [dict(t, raw_speaker=t['speaker'], speaker=names[t['speaker']]) for t in raw_turns]
    return turns, {'speaker_count': speakers, 'unconfirmed_cluster_count': candidates,
                   'raw_cluster_count':len(names), 'short_cluster_threshold_seconds':threshold,
                   'clusters':[{'raw_id':key,'label':label,'speech_seconds':round(durations[key],3)} for key,label in names.items()]}


def _valid_file(path):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == HASHES[path.name]


def ensure_models(root, emit, model_dir=None):
    root = Path(model_dir) if model_dir else Path(root)/'speaker-diarization'
    if not all(_valid_file(root/name) for name in ('segmentation.onnx', 'embedding.onnx')):
        raise FileNotFoundError('说话人模型缺失或校验失败，请在“模型管理”手动下载并配置目录：'+str(root))
    return root


def _download_models(root, emit):
    """Legacy explicit acquisition helper, not used by recognition or the UI."""
    root = Path(root)/'speaker-diarization'
    root.mkdir(parents=True, exist_ok=True)
    def download(url, name):
        target = root/name
        if _valid_file(target):
            return target
        temporary = target.with_suffix(target.suffix+'.part')
        emit('speaker_download', f'下载说话人模型 {name}（仅下载模型，不上传录音）', None)
        with urllib.request.urlopen(url, timeout=45) as response, temporary.open('wb') as stream:
            total = int(response.headers.get('Content-Length', 0))
            size, last = 0, time.monotonic()
            while block := response.read(1024*1024):
                stream.write(block)
                size += len(block)
                if time.monotonic()-last >= 2:
                    emit('speaker_download', f'{name}：已下载 {size/1024**2:.1f} MB'+(f' / {total/1024**2:.1f} MB' if total else ''), None)
                    last = time.monotonic()
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != HASHES[name]:
            raise ValueError(f'{name} 校验失败，请重试下载。')
        temporary.replace(target)
        return target
    if not _valid_file(root/'segmentation.onnx'):
        archive = download(SEGMENTATION_URL, 'segmentation.tar.bz2')
        # Extract only named regular files, never archive paths or links.
        with tarfile.open(archive) as package:
            for item in package.getmembers():
                name = Path(item.name).name
                if item.isfile() and name in ('model.onnx', 'LICENSE', 'README.md'):
                    target = root/('segmentation.onnx' if name == 'model.onnx' else name)
                    target.write_bytes(package.extractfile(item).read())
        if not _valid_file(root/'segmentation.onnx'):
            raise ValueError('说话人分段模型校验失败。')
    download(EMBEDDING_URL, 'embedding.onnx')
    return root


def detect_speakers(audio_path, models_root, emit, num_speakers=0, model_dir=None):
    import sherpa_onnx
    import soundfile as sf
    root = ensure_models(models_root, emit, model_dir=model_dir)
    started = time.perf_counter()
    threads = min(4, os.cpu_count() or 1)
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(root/'segmentation.onnx'), window_shift_ratio=.1),
            num_threads=threads, provider='cpu'),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(root/'embedding.onnx'), num_threads=threads, provider='cpu'),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=int(num_speakers) or -1, threshold=.9),
        min_duration_on=.3, min_duration_off=.5)
    if not config.validate():
        raise ValueError('说话人模型配置无效。')
    model = sherpa_onnx.OfflineSpeakerDiarization(config)
    audio, rate = sf.read(audio_path, dtype='float32')
    if rate != model.sample_rate or audio.ndim != 1:
        raise ValueError('说话人分离需要已解码的 16 kHz 单声道音频。')
    last = [-1]
    def progress(done, total):
        percent = int(100*done/max(1,total))
        if percent != last[0]:
            last[0] = percent
            emit('speaker', f'自动区分说话人 {done}/{total} · CPU 本地分析', percent)
        return 0
    emit('speaker', '加载声学分段与声纹模型 · CPU 本地分析', 0)
    result = model.process(audio, callback=progress).sort_by_start_time()
    raw = [{'start':float(item.start),'end':float(item.end),'speaker':item.speaker} for item in result]
    turns, counts = name_speaker_clusters(raw, num_speakers)
    if not turns:
        raise ValueError('没有检测到可区分的讲话，已保留转写结果。')
    return turns, {'status': 'complete', 'backend': 'sherpa-onnx', 'version': sherpa_onnx.__version__,
                   'models': 'pyannote-segmentation-3.0 + 3D-Speaker ERes2Net',
                   'model_sha256': {k:v for k,v in HASHES.items() if k.endswith('.onnx')},
                   'provider': 'cpu', 'requested_speakers': int(num_speakers), 'cluster_threshold': .9, **counts,
                   'elapsed_seconds': round(time.perf_counter()-started, 2)}


def speaker_at(start, end, turns):
    """Use acoustic overlap; bridge only small uncovered boundary gaps."""
    scores = {}
    for t in turns:
        score = max(0, min(end, t['end'])-max(start,t['start'])) if end > start else float(t['start'] <= start < t['end'])
        if score:
            scores[t['speaker']] = scores.get(t['speaker'], 0)+score
    ranked = sorted(scores, key=scores.get, reverse=True)
    if ranked:
        if len(ranked)>1 and scores[ranked[1]] >= .5*scores[ranked[0]]:
            return OVERLAP
        return ranked[0]
    point = (start+end)/2
    distances = [(max(t['start']-point, point-t['end'], 0),t['speaker']) for t in turns]
    if distances:
        distances.sort()
        if distances[0][0] <= .6:
            return distances[0][1]
    return UNKNOWN


def label_segments(segments, words, labels, turns):
    text, spans = _stream(segments)
    mapping = _word_map(text, words)
    output = []
    for left, right, segment_index in spans:
        segment = deepcopy(segments[segment_index])
        matched = [(a,b,i) for a,b,i in mapping or [] if b>left and a<right]
        # Edited text or a boundary inside an aligned token: retain text and
        # existing interval, label its span without fabricating internal times.
        if not matched or matched[0][0]<left or matched[-1][1]>right:
            segment.update(speaker=speaker_at(segment['start'],segment['end'],turns), speaker_basis='interval')
            output.append(segment)
            continue
        groups = []
        for a,b,index in matched:
            if not groups or groups[-1]['speaker'] != labels[index]:
                groups.append({'left':a,'first':index,'last':index,'speaker':labels[index]})
            else:
                groups[-1]['last'] = index
        pieces = []
        for j, group in enumerate(groups):
            a = left if j==0 else group['left']
            b = right if j+1==len(groups) else groups[j+1]['left']
            part = deepcopy(segment)
            part.update(text=text[a:b].strip(), speaker=group['speaker'], speaker_basis='word_overlap',
                        start=segment['start'] if j==0 else words[group['first']]['start'],
                        end=segment['end'] if j+1==len(groups) else words[group['last']]['end'],
                        word_range=[group['first'],group['last']+1])
            if len(groups)>1:
                part['source_scope'] = 'parent_paragraph'
                if part.get('paragraph_id'):
                    part['paragraph_id'] += f'-s{j+1}'
                if j:
                    part.pop('chapter_title', None)
            pieces.append(part)
        try:
            validate_segments(pieces)
        except ValueError:
            # Real alignment can have zero-length/overlapping boundary tokens.
            # Preserve the original valid interval as ambiguous, without changing text.
            segment.update(speaker=OVERLAP, speaker_basis='ambiguous_word_boundary')
            pieces = [segment]
        output.extend(pieces)
    validate_segments(output)
    return output


def apply_speakers(project, turns, metadata):
    data = deepcopy(project)
    words = data.get('words', [])
    labels = [speaker_at(w['start'],w['end'],turns) for w in words]
    data['speaker_turns'] = deepcopy(turns)
    data['word_speakers'] = labels
    data['reading_paragraphs'] = label_segments(data['reading_paragraphs'],words,labels,turns)
    data['subtitle_segments'] = label_segments(data['subtitle_segments'],words,labels,turns)
    data['segments'] = deepcopy(data['reading_paragraphs'])
    data['diarization'] = deepcopy(metadata)
    return data


def speaker_status(project):
    info = project.get('diarization', {})
    if info.get('status') == 'complete':
        pending = info.get('unconfirmed_cluster_count', 0)
        return f"自动区分 {info['speaker_count']} 位主要说话人"+(f' · {pending} 组短声源待确认' if pending else '')+' · 标签待回听核对'
    if info.get('status') == 'failed':
        return '说话人分离未完成 · 文字已保留，可重试'
    return '尚未自动区分说话人'
