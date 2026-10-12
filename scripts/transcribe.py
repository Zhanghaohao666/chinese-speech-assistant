"""Command-line entry point for reproducible real-audio tests."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from transcriber.engine import save_json
from transcriber.timeline import export_text
from transcriber.reading import prepare_project
from transcriber.documents import export_reading

parser = argparse.ArgumentParser()
parser.add_argument('audio')
parser.add_argument('--models', required=True)
parser.add_argument('--ffmpeg')
parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
parser.add_argument('--engine', choices=['qwen', 'sensevoice', 'firered'], default='qwen')
parser.add_argument('--asr-model-dir', default='')
parser.add_argument('--aligner-model-dir', default='')
parser.add_argument('--no-diarization', action='store_true')
parser.add_argument('--output', required=True)
parser.add_argument('--hotwords', default='')
args = parser.parse_args()
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
if not args.ffmpeg:
    import imageio_ffmpeg
    args.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
config = {'audio': str(Path(args.audio).resolve()), 'models_dir': str(Path(args.models).resolve()),
          'engine': args.engine, 'asr_model_dir': args.asr_model_dir, 'aligner_model_dir': args.aligner_model_dir,
          'diarization': not args.no_diarization,
          'ffmpeg': str(Path(args.ffmpeg).resolve()), 'device': args.device, 'hotwords': args.hotwords,
          'language': 'Chinese', 'job_dir': str(output)}
save_json(output/'config.json', config)
env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), PYTHONIOENCODING='utf-8')
r = subprocess.run([sys.executable, '-u', '-m', 'transcriber.worker', '--config', str(output/'config.json')], env=env)
if r.returncode:
    sys.exit(r.returncode)
result = json.loads((output/'result.json').read_text(encoding='utf-8'))
result = prepare_project(result)
export_reading(result, output/'transcript.txt', 'txt')
for kind in ['srt','vtt']:
    (output/f'transcript.{kind}').write_text(export_text(result['subtitle_segments'], kind), encoding='utf-8')
print(json.dumps({'elapsed_seconds': result['elapsed_seconds'], 'segments': result['segments']}, ensure_ascii=False, indent=2))
