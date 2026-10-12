"""Add local speaker labels to an existing project without repeating ASR."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from transcriber.engine import run_speaker_job, save_json
from transcriber.documents import export_reading
from transcriber.timeline import export_text

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('project')
    parser.add_argument('--models',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--speakers',type=int,default=0,help='0 estimates the count automatically')
    args=parser.parse_args()
    import imageio_ffmpeg
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    config={'task':'diarization','source_project':str(Path(args.project).resolve()),
            'models_dir':str(Path(args.models).resolve()),'job_dir':str(output),
            'ffmpeg':imageio_ffmpeg.get_ffmpeg_exe(),'num_speakers':args.speakers}
    save_json(output/'config.json',config)
    def emit(stage,message,progress):
        print(json.dumps({'stage':stage,'message':message,'progress':progress},ensure_ascii=False),flush=True)
    result=run_speaker_job(config,emit)
    export_reading(result,output/'阅读版.txt','txt')
    for kind in ('srt','vtt'):
        (output/f'字幕版.{kind}').write_text(export_text(result['subtitle_segments'],kind),encoding='utf-8')
    sys.exit(0 if result.get('diarization',{}).get('status')=='complete' else 1)
