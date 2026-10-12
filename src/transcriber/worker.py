import argparse
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    def emit(stage, message, progress):
        print(json.dumps({'stage': stage, 'message': message, 'progress': progress}, ensure_ascii=False), flush=True)
    try:
        from .engine import run_job, run_speaker_job
        (run_speaker_job if config.get('task') == 'diarization' else run_job)(config, emit)
    except Exception:
        detail = traceback.format_exc()
        Path(config['job_dir']).mkdir(parents=True, exist_ok=True)
        Path(config['job_dir'], 'error.log').write_text(detail, encoding='utf-8')
        emit('error', detail, None)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
