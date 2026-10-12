from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import wave

from .timeline import restore_punctuation, sentences, validate_segments, reconcile_model_boundaries
from .reading import prepare_project

ASR_REPO = 'Qwen/Qwen3-ASR-1.7B-hf'
ALIGN_REPO = 'Qwen/Qwen3-ForcedAligner-0.6B-hf'
REVISIONS = {ASR_REPO: 'bcd2b5b7f32b480ab5790554cfa8347f246a14f3',
             ALIGN_REPO: 'c07281df297b9905d24a508279258cccf987a064'}


def save_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def model_path(repo, root, emit, allow_download=False):
    folder = Path(root) / repo.split('/')[-1]
    needed = ['config.json', 'model.safetensors', 'processor_config.json', 'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja']
    if not all((folder / f).is_file() for f in needed):
        if not allow_download:
            raise FileNotFoundError(f'{repo} 尚未准备好。请在“模型管理”点击官方下载链接，下载并配置本地目录：{folder}')
        from huggingface_hub import snapshot_download
        emit('download', f'首次下载 {repo}（下载进度见日志；缓存后可离线使用）', None)
        snapshot_download(repo, revision=REVISIONS[repo], local_dir=str(folder),
                          allow_patterns=['*.json', '*.safetensors', '*.jinja', 'README.md'], max_workers=2)
    return str(folder)


def prepare_audio(source, output, ffmpeg):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    subprocess.run([str(ffmpeg), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                    '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(output)],
                   check=True, capture_output=True, creationflags=flags)


def split_audio(path, directory, max_seconds=45, overlap=.8):
    """Disk-backed bounded chunks, preferring a quiet cut; overlap avoids cutting a phoneme."""
    import numpy as np
    import soundfile as sf
    chunks = []
    with wave.open(str(path), 'rb') as f:
        sr, total = f.getframerate(), f.getnframes()
        duration = total / sr
        start = 0
        while start < total:
            end = min(total, start + round(max_seconds * sr))
            if end < total:
                search_start = max(start + int(20 * sr), end - 10 * sr)
                f.setpos(search_start)
                audio = np.frombuffer(f.readframes(end - search_start), dtype=np.int16).astype(np.float32) / 32768
                width = int(.1 * sr)
                rms = np.array([np.sqrt(np.mean(audio[i:i+width]**2)) for i in range(0, len(audio)-width, width)])
                if len(rms) and rms.min() < .015:
                    end = search_start + int(rms.argmin()) * width + width // 2
            a, b = max(0, start - round(overlap*sr)), min(total, end + round(overlap*sr))
            f.setpos(a)
            samples = np.frombuffer(f.readframes(b-a), dtype=np.int16).astype(np.float32)/32768
            name = Path(directory) / f'chunk_{len(chunks):05d}.wav'
            sf.write(str(name), samples, sr, subtype='PCM_16')
            chunks.append({'path': str(name), 'offset': a/sr, 'core_start': start/sr, 'core_end': end/sr})
            start = end
    return duration, chunks


def recognition_inputs(processor, samples, language='Chinese', hotwords=''):
    # The pinned Transformers helper silently ignores prompt=. Use the official
    # chat template directly, with vocabulary in system and forced-language prefill.
    messages = [
        {'role': 'system', 'content': [{'type': 'text', 'text': ('Vocabulary: ' + hotwords) if hotwords else ''}]},
        {'role': 'user', 'content': [{'type': 'audio', 'audio': samples}]},
        {'role': 'assistant', 'content': [{'type': 'text', 'text': f'language {language}<asr_text>'}]},
    ]
    return processor.apply_chat_template(messages, tokenize=True, return_dict=True,
                                         continue_final_message=True, add_generation_prompt=False)


def native_chunk_segments(chunk, duration):
    """Use only complete validated native intervals, otherwise retain chunk bounds."""
    stamps = chunk.get('timestamps')
    if stamps:
        try:
            words = restore_punctuation(chunk['text'], stamps, chunk['offset'])
            segments, repairs = reconcile_model_boundaries(sentences(words))
            validate_segments(segments, duration)
            if not segments or any(w['start'] < chunk['core_start'] or w['end'] > chunk['core_end']+.05 for w in words):
                raise ValueError('字词时间超出对应音频块')
            for segment in segments:
                segment['timing_basis'] = 'firered_ctc'
            return segments, words, repairs, None
        except (ValueError, KeyError, TypeError, IndexError) as error:
            reason = str(error)
    else:
        reason = '后端未提供完整字词起止时间'
    return ([{'start': chunk['core_start'], 'end': chunk['core_end'],
              'text': chunk['text'], 'timing_basis': 'audio_chunk'}], [], [], reason)


def run_job(config, emit):
    from .asr_backends import engine_id, make_backend, ENGINES
    started = time.perf_counter()
    key = engine_id(config)
    emit('init', '初始化 '+ENGINES[key]['name'], 0)
    job = Path(config['job_dir'])
    job.mkdir(parents=True, exist_ok=True)
    source = Path(config['audio']).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    emit('decode', '正在解码音频', 2)
    audio_path = job / 'audio.wav'
    prepare_audio(source, audio_path, config['ffmpeg'])
    # Coarse-time backends cannot reliably de-duplicate overlapping text.
    # Reuse quiet-cut preprocessing, without overlap for the new engines.
    duration, chunks = split_audio(audio_path, job, max_seconds=45 if key == 'qwen' else 30,
                                  overlap=.8 if key == 'qwen' else 0)
    if not chunks:
        raise ValueError('音频为空')
    backend = make_backend(key)
    transcript_chunks, words, segments, boundary_adjustments, timing_warnings = [], [], [], [], []
    metrics = {}
    try:
        t = time.perf_counter()
        backend.load(config, emit)
        metrics['load_seconds'] = round(time.perf_counter()-t, 3)
        emit('device', '实际识别设备：'+backend.execution['device']+' · '+backend.execution['dtype'], 9)
        if key != 'qwen' and config.get('hotwords'):
            emit('warning', '当前引擎不支持词汇提示，该设置未传入模型。', None)
        t = time.perf_counter()
        for i, chunk in enumerate(chunks):
            emit('asr', f'{ENGINES[key]["name"]} · 识别中文 {i+1}/{len(chunks)}',
                 10 + round((42 if key == 'qwen' else 70)*i/len(chunks)))
            output = backend.transcribe(chunk['path'], f'chunk_{i:05d}')
            transcript_chunks.append({**chunk, **output})
            save_json(job / 'transcript_checkpoint.json', transcript_chunks)
            emit('text', output['text'], None)
        metrics['inference_seconds'] = round(time.perf_counter()-t, 3)
        if getattr(backend, 'separate_alignment', False):
            t = time.perf_counter()
            backend.load_aligner(emit)
            for i, chunk in enumerate(transcript_chunks):
                emit('align', f'时间对齐 {i+1}/{len(chunks)}', 60 + round(22*i/len(chunks)))
                if not chunk['text'].strip():
                    continue
                stamps = backend.align(chunk)
                chunk['timestamps'] = stamps
                chunk['timing_basis'] = 'qwen_forced_alignment'
                save_json(job / 'transcript_checkpoint.json', transcript_chunks)
                aligned = restore_punctuation(chunk['text'], stamps, chunk['offset'])
                words.extend(w for w in aligned if chunk['core_start'] <= (w['start']+w['end'])/2 < chunk['core_end'])
                save_json(job / 'alignment_checkpoint.json', words)
            metrics['alignment_with_load_seconds'] = round(time.perf_counter()-t, 3)
        execution = dict(backend.execution)
        placement = getattr(backend, 'placement', {})
    finally:
        backend.close()
    emit('segment', '整理转写文字与时间来源', 84)
    if key == 'qwen':
        segments, boundary_adjustments = reconcile_model_boundaries(sentences(words))
    else:
        for i, chunk in enumerate(transcript_chunks):
            if not chunk['text'].strip():
                continue
            chunk_segments, aligned, repairs, warning = native_chunk_segments(chunk, duration)
            segments.extend(chunk_segments)
            words.extend(aligned)
            boundary_adjustments.extend({'chunk': i, **item} for item in repairs)
            if warning:
                timing_warnings.append({'chunk': i, 'reason': warning})
        save_json(job / 'alignment_checkpoint.json', words)
    validate_segments(segments, duration)
    if not segments:
        raise ValueError('未识别到讲话，原始输出已保留在任务目录。')
    if boundary_adjustments:
        emit('boundary', f'已处理 {len(boundary_adjustments)} 处模型时间重叠；原始字词时间保留在项目中。', 85)
    timing_note = ('包含音频块时间：开始时间和时长仅表示所在音频块，不是精确的句子起止；原生 token 起点保存在 raw_chunks。'
                   if timing_warnings else '时间来自模型字词对齐，属于模型预测，请回听核对。')
    if timing_warnings:
        emit('warning', timing_note, 85)
    result = {'schema': 1, 'audio': str(source), 'duration': duration, 'segments': segments,
              'words': words, 'raw_chunks': transcript_chunks, 'edited': False,
              'engine': key, 'model_name': ENGINES[key]['name'],
              'models': {repo: ('local_unverified' if config.get('asr_model_dir' if repo == ASR_REPO else 'aligner_model_dir') else revision)
                         for repo, revision in REVISIONS.items()} if key == 'qwen' else {'asr': ENGINES[key]['name']},
              'device_map': placement, 'execution': execution, 'metrics': metrics,
              'timing_note': timing_note, 'timing_warnings': timing_warnings,
              'boundary_adjustments': boundary_adjustments}
    result = prepare_project(result)
    if config.get('diarization', True):
        def speaker_emit(stage, message, progress):
            emit(stage, message, None if progress is None else 85 + round(progress*.14))
        result = add_speakers_safely(result, audio_path, config, speaker_emit)
    result['elapsed_seconds'] = round(time.perf_counter()-started, 2)
    save_json(job / 'result.json', result)
    emit('done', str(job / 'result.json'), 100)
    return result


def add_speakers_safely(project, audio_path, config, emit):
    """A diarization failure must not discard a successful transcription."""
    from copy import deepcopy
    from .diarization import detect_speakers, apply_speakers
    try:
        turns, info = detect_speakers(audio_path, config['models_dir'], emit, config.get('num_speakers', 0),
                                     model_dir=config.get('speaker_model_dir'))
        return apply_speakers(project, turns, info)
    except Exception as error:
        result = deepcopy(project)
        result['diarization'] = {'status': 'failed', 'error': str(error)}
        emit('warning', '说话人分离未完成，转写文字已保留，可重试：'+str(error), 99)
        return result


def run_speaker_job(config, emit):
    """Apply speakers to an existing project, preserving edited text and originals."""
    started = time.perf_counter()
    job = Path(config['job_dir'])
    job.mkdir(parents=True, exist_ok=True)
    result = prepare_project(json.loads(Path(config['source_project']).read_text(encoding='utf-8')))
    audio = job/'audio.wav'
    emit('decode', '解码录音，保留已有文字与修改，仅补做说话人分离', 0)
    prepare_audio(result['audio'], audio, config['ffmpeg'])
    result = add_speakers_safely(result, audio, config, emit)
    result['last_operation'] = 'diarization'
    result['last_operation_seconds'] = round(time.perf_counter()-started, 2)
    result['edited'] = False
    save_json(job/'result.json', result)
    emit('done', str(job/'result.json'), 100)
    return result
