"""Reading paragraphs independent of subtitle limits, with traceable timing."""
from copy import deepcopy
from pathlib import Path
import re

from .timeline import normalized

SENTENCE_END = re.compile(r'[。！？!?]+[”’"）)]*\s*')
TOPIC_START = re.compile(r'^(?:啊[，,\s]*)?(?:那(?:么)?[，,\s]*)?(?:首先|其次|再就是|接下来|下面|最后|第[一二三四五六七八九十]+(?:个)?(?:方面|点|问题)|一是|二是|三是|好[，,]非常感谢)')


def join_text(left, right):
    separator = ' ' if left and right and left[-1].isascii() and right[0].isascii() and not left[-1].isspace() and not right[0].isspace() else ''
    return left + separator + right


def _stream(segments):
    text, spans = '', []
    for i, s in enumerate(segments):
        joined = join_text(text, s['text'])
        start = len(joined) - len(s['text'])
        spans.append((start, len(joined), i))
        text = joined
    return text, spans


def _word_map(text, words):
    """Only exact normalized matches qualify; never interpolate timestamps."""
    if not words or normalized(text) != normalized(''.join(w['word'] for w in words)):
        return None
    positions = [i for i, c in enumerate(text) if c.isalnum()]
    ranges, cursor = [], 0
    for i, word in enumerate(words):
        size = len(normalized(word['word']))
        if not size:
            continue
        ranges.append((positions[cursor], positions[cursor+size-1]+1, i))
        cursor += size
    return ranges


def build_reading(segments, words=None, target_chars=220, pause_seconds=2.0):
    """Soft length target at full sentences; explicit speakers and topic cues win.

    No semantic speaker inference. Without matching words, internal source
    boundaries cannot create new precise timestamps and are not used to split.
    """
    if not segments:
        return []
    text, sources = _stream(segments)
    mapping = _word_map(text, words)
    breaks = {len(text)}
    breaks.update(m.end() for m in SENTENCE_END.finditer(text))
    for i, (a, b, index) in enumerate(sources[1:], 1):
        prev, current = segments[index-1], segments[index]
        if prev.get('speaker') != current.get('speaker'):
            breaks.add(a)
    # A split inside an aligned token is no more precise than its original span.
    if mapping is not None:
        breaks = {p for p in breaks if not any(a < p < b for a, b, _ in mapping)}
    else:
        source_ends = {b for _, b, _ in sources} | {a for a, _, _ in sources}
        breaks &= source_ends

    units, left = [], 0
    for right in sorted(breaks):
        if not text[left:right].strip():
            continue
        refs = []
        for a, b, index in sources:
            if b > left and a < right:
                s = segments[index]
                refs.append({'segment_id': index+1, 'char_start': max(a, left)-a,
                             'char_end': min(b, right)-a, 'start': s['start'], 'end': s['end']})
        unit = {'text': text[left:right].strip(), 'source_spans': refs,
                'start': min(r['start'] for r in refs), 'end': max(r['end'] for r in refs),
                'timing_basis': 'source_boundary'}
        speakers = {segments[r['segment_id']-1].get('speaker') for r in refs}
        if len(speakers) == 1 and next(iter(speakers)):
            unit['speaker'] = next(iter(speakers))
        if mapping is not None:
            indices = [i for a, b, i in mapping if b > left and a < right]
            if indices:
                unit.update(start=words[indices[0]]['start'], end=words[indices[-1]]['end'],
                            word_range=[indices[0], indices[-1]+1], timing_basis='word_alignment')
        units.append(unit)
        left = right

    paragraphs = []
    for unit in units:
        prev = paragraphs[-1] if paragraphs else None
        split = prev and (prev.get('speaker') != unit.get('speaker') or
                          unit['start']-prev['end'] >= pause_seconds or
                          TOPIC_START.match(unit['text']) or len(prev['text']) >= target_chars)
        # Zero-length word timings and touching/overlapping aligned tokens are
        # retained in one paragraph rather than inventing a timing boundary.
        if prev and (prev['end'] > unit['start']+.001 or prev['start'] >= prev['end'] or unit['start'] >= unit['end']):
            split = False
        if not prev or split:
            paragraphs.append(unit)
        else:
            prev['text'] = join_text(prev['text'], unit['text'])
            prev['start'] = min(prev['start'], unit['start'])
            prev['end'] = max(prev['end'], unit['end'])
            prev['source_spans'].extend(unit['source_spans'])
            if 'word_range' in prev and 'word_range' in unit:
                prev['word_range'][1] = unit['word_range'][1]
            if prev.get('speaker') != unit.get('speaker'):
                prev.pop('speaker', None)
    for i, p in enumerate(paragraphs, 1):
        p['paragraph_id'] = f'p{i:04d}'
    return paragraphs


def prepare_project(result):
    """Migrate old projects without replacing saved manual edits."""
    data = deepcopy(result)
    if data.get('reading_schema') == 1:
        data['segments'] = deepcopy(data['reading_paragraphs'])
        return data
    source = deepcopy(data.get('subtitle_segments', data['segments']))
    data['source_segments'] = deepcopy(source)
    data['subtitle_segments'] = deepcopy(source)
    # Existing saved dialogue projects may contain edits or explicit splits.
    # Preserve them. Fresh ASR results get the new reading structure.
    if data.get('dialogue_layout'):
        paragraphs = deepcopy(data['segments'])
    else:
        paragraphs = build_reading(source, data.get('words'))
    data.update(reading_schema=1, schema=2, reading_paragraphs=paragraphs,
                segments=deepcopy(paragraphs), dialogue_layout=True)
    data.setdefault('title', Path(data.get('audio', '会议')).stem + ' 会议转写')
    return data


def merge_metadata(first, second):
    """Keep provenance when the user explicitly merges paragraphs."""
    if first.get('source_spans') or second.get('source_spans'):
        first['source_spans'] = first.get('source_spans', []) + second.get('source_spans', [])
    if 'word_range' in first and 'word_range' in second:
        first['word_range'] = [first['word_range'][0], second['word_range'][1]]
    else:
        first.pop('word_range', None)
    first.update(end=second['end'], text=join_text(first['text'], second['text']))


def aligned_split(segment, left_text, right_text, words):
    """Return existing word boundaries only when the edited text still matches."""
    selected = segment.get('word_range')
    if not selected:
        return None
    lo, hi = selected
    available = words[lo:hi]
    if normalized(left_text+right_text) != normalized(''.join(w['word'] for w in available)):
        return None
    count, target = 0, len(normalized(left_text))
    for index, word in enumerate(available[:-1], lo):
        count += len(normalized(word['word']))
        if count == target:
            a, b = word['end'], words[index+1]['start']
            if segment['start'] < a <= b < segment['end']:
                return a, b, index+1
        if count > target:
            break
    return None


def reading_document(project):
    """One semantic document consumed by TXT, DOCX and PDF writers."""
    from .diarization import speaker_status
    blocks = []
    for p in project['reading_paragraphs']:
        if p.get('chapter_title', '').strip():
            blocks.append({'type': 'heading', 'text': p['chapter_title'].strip()+'（编辑整理）'})
        prefix = display_time(p['start']) if p.get('start') is not None else '时间未标注'
        if p.get('speaker'):
            prefix += ' · '+p['speaker']
        blocks.append({'type': 'paragraph', 'text': f'[{prefix}] {p["text"]}'})
    duration = project.get('duration')
    return {'title': project.get('title') or Path(project.get('audio', '会议')).stem+' 会议转写',
            'metadata': [('录音文件', Path(project.get('audio', '')).name or '未提供'),
                         ('录音时长', display_time(duration) if duration is not None else '未提供'),
                         ('会议日期', project.get('meeting_date') or '未填写'),
                         ('内容说明', '按完整句与话题提示组段；'+speaker_status(project)+'。正文保留转写原文，未经人工校对。'),
                         ('时间说明', project.get('timing_note') or '每段显示起始时间至秒；原始时间与来源条目保存在项目 JSON 中。')],
            'blocks': blocks}


def display_time(seconds):
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
