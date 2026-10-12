"""Export both reading documents and subtitles from an existing ASR project."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from transcriber.reading import prepare_project
from transcriber.documents import export_reading
from transcriber.engine import save_json
from transcriber.timeline import export_text

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    project = prepare_project(json.loads(Path(args.project).read_text(encoding='utf-8')))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    save_json(output/'阅读项目.json', project)
    for kind in ('txt', 'docx', 'pdf'):
        export_reading(project, output/f'阅读版.{kind}', kind)
    for kind in ('srt', 'vtt'):
        (output/f'字幕版.{kind}').write_text(export_text(project['subtitle_segments'], kind), encoding='utf-8')
    print(f"阅读版 {len(project['reading_paragraphs'])} 段；字幕版 {len(project['subtitle_segments'])} 条")
