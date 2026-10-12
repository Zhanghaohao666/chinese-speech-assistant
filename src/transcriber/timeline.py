"""Keep recognition text intact while grouping real forced-alignment timestamps."""
from __future__ import annotations

import copy
import math
import re
from .vendor.pyvideotrans_segment import _resegment


def normalized(text):
    return ''.join(c.casefold() for c in text if c.isalnum())


def restore_punctuation(text, timestamps, offset=0.0):
    positions = [i for i, c in enumerate(text) if c.isalnum()]
    expected = normalized(text)
    actual = ''.join(normalized(t['text']) for t in timestamps)
    if actual != expected:
        raise ValueError('对齐器返回的字词与识别原文不一致，已停止导出，避免生成错误时间戳。')
    words, cursor = [], 0
    for item in timestamps:
        size = len(normalized(item['text']))
        if not size:
            continue
        a = positions[cursor] if cursor else 0
        cursor += size
        b = positions[cursor] if cursor < len(positions) else len(text)
        start, end = float(item['start_time']) + offset, float(item['end_time']) + offset
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
            raise ValueError('对齐模型返回了无效时间戳。')
        words.append({'word': text[a:b], 'start': start, 'end': end})
    return words


def sentences(words, max_seconds=8, min_seconds=1):
    """Reuse pyVideoTrans segmentation, preserving hard sentence boundaries."""
    clauses, current = [], []
    for word in words:
        current.append(word)
        if re.search(r'[。！？!?][”\"’）)]*\s*$', word['word']):
            clauses.append(current)
            current = []
    if current:
        clauses.append(current)
    result = []
    for clause in clauses:
        items = _resegment([{'text': ''.join(w['word'] for w in clause),
                              'start': clause[0]['start'], 'end': clause[-1]['end'],
                              'words': copy.deepcopy(clause)}], 'zh',
                            int(max_seconds * 1000), int(min_seconds * 1000))
        # Upstream normalizes whitespace; recover exact source spans in order.
        cursor = 0
        for item in items:
            target = normalized(item.text)
            consumed, original = '', ''
            while cursor < len(clause) and len(consumed) < len(target):
                fragment = clause[cursor]['word']
                consumed += normalized(fragment)
                original += fragment
                cursor += 1
            if consumed != target:
                raise ValueError('字幕分段未完整保留识别文字。')
            result.append({'start': item.start_time / 1000, 'end': item.end_time / 1000,
                           'text': original.strip()})
        if cursor != len(clause):
            raise ValueError('字幕分段遗漏了字词。')
    return result


def timecode(seconds, separator='.'):
    ms = round(float(seconds) * 1000)
    if ms < 0:
        raise ValueError('时间不能为负数')
    sec, milli = divmod(ms, 1000)
    minute, sec = divmod(sec, 60)
    hour, minute = divmod(minute, 60)
    return f'{hour:02d}:{minute:02d}:{sec:02d}{separator}{milli:03d}'


def reconcile_model_boundaries(segments, max_overlap=.05):
    """Repair model overlaps, merging ambiguous intervals without losing text.

    Used once on model output, never on user edits. Keep raw alignment intact
    and record each repair. Invalid individual intervals still raise an error.
    """
    result, sources = [], []
    adjustments = []
    for i, segment in enumerate(segments, 1):
        validate_segments([segment])
        current = copy.deepcopy(segment)
        current_sources = [i]
        while result:
            previous = result[-1]
            overlap = previous['end'] - current['start']
            if overlap <= .001:
                break
            boundary = round((previous['end'] + current['start']) / 2, 3)
            audit = {'previous_segment': sources[-1][-1],
                     'next_segment': current_sources[0],
                     'original_previous_end': previous['end'],
                     'original_next_start': current['start'],
                     'overlap_seconds': round(overlap, 6)}
            if overlap <= max_overlap + 1e-9 and previous['start'] < boundary < current['end']:
                audit.update(kind='adjust', boundary=boundary)
                adjustments.append(audit)
                previous['end'] = current['start'] = boundary
                break
            # Ambiguous or backwards intervals share one span. Backtrack if
            # its start now overlaps another earlier segment; keep text order.
            current_sources = sources.pop() + current_sources
            audit.update(kind='merge', source_segments=current_sources[:],
                         original_intervals=[[previous['start'], previous['end']],
                                             [current['start'], current['end']]])
            adjustments.append(audit)
            current['start'] = min(previous['start'], current['start'])
            current['end'] = max(previous['end'], current['end'])
            current['text'] = previous['text'] + '\n' + current['text']
            result.pop()
        result.append(current)
        sources.append(current_sources)
    return result, adjustments


def validate_segments(segments, duration=None):
    last = 0.0
    for i, segment in enumerate(segments, 1):
        a, b = float(segment['start']), float(segment['end'])
        if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b):
            raise ValueError(f'第 {i} 句起止时间无效，结束时间必须大于开始时间。')
        if a < last - .001:
            raise ValueError(f'第 {i} 句与上一句重叠，请先校正时间。')
        if duration is not None and b > duration + .05:
            raise ValueError(f'第 {i} 句超出音频时长。')
        if not segment['text'].strip():
            raise ValueError(f'第 {i} 句内容为空。')
        last = b


def export_text(segments, kind):
    validate_segments(segments)
    def body(segment):
        return f"[{segment['speaker']}] {segment['text']}" if segment.get('speaker') else segment['text']
    if kind == 'srt':
        return '\n\n'.join(f"{i}\n{timecode(s['start'], ',')} --> {timecode(s['end'], ',')}\n{body(s)}"
                            for i, s in enumerate(segments, 1)) + '\n'
    if kind == 'vtt':
        return 'WEBVTT\n\n' + '\n\n'.join(f"{timecode(s['start'])} --> {timecode(s['end'])}\n{body(s)}" for s in segments) + '\n'
    return '\n\n'.join(f"[{timecode(s['start'])} → {timecode(s['end'])}] {s['text']}" for s in segments) + '\n'
