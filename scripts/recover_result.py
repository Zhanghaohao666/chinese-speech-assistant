"""Finish a job that reached final segmentation, without running ASR again."""
import argparse
import json
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from transcriber.engine import save_json, REVISIONS
from transcriber.timeline import sentences, reconcile_model_boundaries, validate_segments, export_text
from transcriber.reading import prepare_project
from transcriber.documents import export_reading


def recover(job, output):
    started = time.perf_counter()
    job, output = Path(job).resolve(), Path(output).resolve()
    if (job/'result.json').exists():
        raise ValueError('任务已存在最终结果，不覆盖已有文件。')
    events = [json.loads(line) for line in (job/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if not any(event.get('stage') == 'segment' for event in events):
        raise ValueError('任务尚未完成全部时间对齐，不能仅从最终分段阶段恢复。')
    config = json.loads((job/'config.json').read_text(encoding='utf-8'))
    words = json.loads((job/'alignment_checkpoint.json').read_text(encoding='utf-8'))
    chunks = json.loads((job/'transcript_checkpoint.json').read_text(encoding='utf-8'))
    with wave.open(str(job/'audio.wav')) as audio:
        duration = audio.getnframes()/audio.getframerate()
    segments, adjustments = reconcile_model_boundaries(sentences(words))
    validate_segments(segments, duration)
    if not segments:
        raise ValueError('检查点没有可用转写内容。')
    result = {'schema': 1, 'audio': config['audio'], 'duration': duration,
              'segments': segments, 'words': words, 'raw_chunks': chunks, 'edited': False,
              'models': REVISIONS, 'boundary_adjustments': adjustments,
              'elapsed_seconds': None,
              'recovery': {'source_job': str(job), 'seconds': round(time.perf_counter()-started, 3),
                           'note': '仅恢复最终分段；原始识别总耗时未记录，不以恢复耗时代替。'}}
    result = prepare_project(result)
    output.mkdir(parents=True, exist_ok=True)
    save_json(output/'result.json', result)
    export_reading(result, output/'transcript.txt', 'txt')
    for kind in ('srt', 'vtt'):
        (output/f'transcript.{kind}').write_text(export_text(segments, kind), encoding='utf-8')
    save_json(job/'result.json', result)
    save_json(job/'ui_status.json', {'status': '已完成（检查点恢复）'})
    with (job/'events.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'stage': 'recovered', 'message': str(output/'result.json'),
                                'boundary_adjustments': adjustments}, ensure_ascii=False)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('job')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = recover(args.job, args.output)
    print(json.dumps({'duration': result['duration'], 'segments': len(result['segments']),
                      'adjustments': result['boundary_adjustments'], 'recovery': result['recovery']}, ensure_ascii=False))
