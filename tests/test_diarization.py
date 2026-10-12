import json
import unittest
from unittest.mock import patch
from copy import deepcopy
from pathlib import Path
from PySide6.QtWidgets import QInputDialog
from transcriber.diarization import speaker_at, apply_speakers, label_segments, UNKNOWN, OVERLAP, speaker_status, name_speaker_clusters
from transcriber.reading import prepare_project, reading_document
from transcriber.engine import add_speakers_safely
from transcriber.timeline import normalized, validate_segments, export_text
import test_workspace as workspace_tests


class SpeakerTests(unittest.TestCase):
    def setUp(self):
        self.turns = [{'start':0,'end':4,'speaker':'说话人 1'},
                      {'start':4,'end':8,'speaker':'说话人 2'},
                      {'start':8,'end':12,'speaker':'说话人 1'}]
        self.words = [{'start':i,'end':i+1,'word':c} for i,c in enumerate('今天讨论预算然后讨论日程')]
        self.project = prepare_project({'audio':'meeting.wav','duration':12,
                          'words':self.words,'segments':[{'start':0,'end':12,'text':'今天讨论预算然后讨论日程'}]})
        self.meta = {'status':'complete','speaker_count':2}

    def test_acoustic_overlap_and_unknown_gap(self):
        self.assertEqual(speaker_at(1,2,self.turns),'说话人 1')
        self.assertEqual(speaker_at(4,4,self.turns),'说话人 2')
        self.assertEqual(speaker_at(20,21,self.turns),UNKNOWN)
        self.assertEqual(speaker_at(3.5,4.5,self.turns),OVERLAP)

    def test_short_clusters_remain_visible_as_uncertain_not_extra_people(self):
        raw=[{'start':0,'end':.4,'speaker':8},{'start':1,'end':100,'speaker':2},
             {'start':101,'end':200,'speaker':7},{'start':201,'end':205,'speaker':2}]
        turns,stats=name_speaker_clusters(raw)
        self.assertEqual(stats['speaker_count'],2)
        self.assertEqual(stats['unconfirmed_cluster_count'],1)
        self.assertEqual(turns[0]['speaker'],'待确认声源 1')
        self.assertEqual(turns[1]['speaker'],turns[3]['speaker'])
        self.assertEqual(turns[0]['raw_speaker'],8)

    def test_turn_changes_split_both_views_at_real_words_and_keep_sources(self):
        result = apply_speakers(self.project,self.turns,self.meta)
        for key in ('reading_paragraphs','subtitle_segments'):
            parts = result[key]
            self.assertEqual([p['speaker'] for p in parts],['说话人 1','说话人 2','说话人 1'])
            self.assertEqual([(p['start'],p['end']) for p in parts],[(0,4),(4,8),(8,12)])
            self.assertEqual(''.join(p['text'] for p in parts),'今天讨论预算然后讨论日程')
            validate_segments(parts,12)
        self.assertEqual(result['source_segments'],self.project['source_segments'])
        self.assertEqual(result['words'],self.words)
        self.assertNotIn('speaker',self.project['reading_paragraphs'][0])
        self.assertEqual(result['reading_paragraphs'][1]['source_scope'],'parent_paragraph')

    def test_edited_text_kept_without_inventing_timestamps(self):
        self.project['reading_paragraphs'][0]['text']='人工修改后的内容。'
        result = apply_speakers(self.project,self.turns,self.meta)
        parts=result['reading_paragraphs']
        self.assertEqual(len(parts),1)
        self.assertEqual(parts[0]['text'],'人工修改后的内容。')
        self.assertEqual((parts[0]['start'],parts[0]['end']),(0,12))
        self.assertEqual(parts[0]['speaker_basis'],'interval')

    def test_invalid_internal_word_boundary_retains_original_text(self):
        words = [{'start':0,'end':5,'word':'甲'}, {'start':4,'end':6,'word':'乙'}]
        result = label_segments([{'start':0,'end':6,'text':'甲乙'}],words,['说话人 1','说话人 2'],self.turns)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['text'],'甲乙')
        self.assertEqual(result[0]['speaker'],OVERLAP)

    def test_failure_preserves_transcription_and_reports_failure(self):
        events=[]
        with patch('transcriber.diarization.detect_speakers',side_effect=RuntimeError('download failed')):
            result=add_speakers_safely(self.project,'unused.wav',{'models_dir':'unused'},lambda *x:events.append(x))
        self.assertEqual(result['segments'],self.project['segments'])
        self.assertEqual(result['diarization']['status'],'failed')
        self.assertIn('未完成',speaker_status(result))
        self.assertEqual(events[-1][0],'warning')

    def test_reading_export_includes_speaker_and_accurate_status(self):
        result=apply_speakers(self.project,self.turns,self.meta)
        doc=reading_document(result)
        self.assertIn('说话人 1',doc['blocks'][0]['text'])
        self.assertTrue(any('自动区分 2 位主要说话人' in v for k,v in doc['metadata']))
        self.assertFalse(any('尚未自动' in v for k,v in doc['metadata']))
        for kind in ('srt','vtt'):
            self.assertIn('[说话人 2]',export_text(result['subtitle_segments'],kind))


class SpeakerWorkspaceTests(unittest.TestCase):
    setUpClass=classmethod(workspace_tests.WorkspaceTests.setUpClass.__func__)
    setUp=workspace_tests.WorkspaceTests.setUp
    close_window=workspace_tests.WorkspaceTests.close_window

    def test_speaker_preferences_persist(self):
        self.w.diarization_enabled.setChecked(False)
        self.w.speaker_count.setValue(4)
        saved=json.loads((self.root/'ui.local.json').read_text(encoding='utf-8'))
        self.assertFalse(saved['diarization'])
        self.assertEqual(saved['num_speakers'],4)

    def test_rename_updates_both_views_without_changing_text(self):
        self.w.table.item(0,2).setData(256,'说话人 1')
        self.w.result['subtitle_segments'][0]['speaker']='说话人 1'
        with patch.object(QInputDialog,'getText',return_value=('主持人',True)):
            self.w.rename_speaker(0)
        self.assertEqual(self.w.current_segments()[0]['speaker'],'主持人')
        self.assertEqual(self.w.result['subtitle_segments'][0]['speaker'],'主持人')
        self.assertEqual(self.w.current_segments()[0]['text'],'讨论预算。')

    def test_existing_job_snapshots_edits_and_does_not_clear_result(self):
        self.w.source=self.root/'test.wav'
        self.w.source.write_bytes(b'placeholder')
        self.w.settings['ffmpeg']=str(self.w.source)
        self.w.table.item(0,2).setText('保存这段修改。')
        with patch.object(self.w,'launch_worker') as launch, patch.object(self.w,'ready_for_models',return_value=True):
            self.w.diarize_existing()
        config=launch.call_args.args[0]
        self.assertEqual(config['task'],'diarization')
        snapshot=json.loads(Path(config['source_project']).read_text(encoding='utf-8'))
        self.assertEqual(snapshot['reading_paragraphs'][0]['text'],'保存这段修改。')
        self.assertEqual(self.w.current_segments()[0]['text'],'保存这段修改。')


if __name__=='__main__':
    unittest.main()
