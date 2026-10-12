"""Existing Qwen recognition/alignment stages, behind the ASR lifecycle interface."""
import gc
import os


class QwenEngine:
    separate_alignment = True

    def load(self, config, emit):
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        from .engine import model_path, ALIGN_REPO
        from .asr_backends import local_model
        self.config = config
        self.asr_dir = local_model(config, 'qwen', emit)
        self.align_dir = config.get('aligner_model_dir') or model_path(ALIGN_REPO, config['models_dir'], emit)
        if config.get('aligner_model_dir'):
            from .asr_backends import QWEN_FILES
            from pathlib import Path
            if not all((Path(self.align_dir)/f).is_file() for f in QWEN_FILES):
                raise FileNotFoundError('指定的 Qwen 对齐模型目录不完整：'+self.align_dir)
        device = config.get('device', 'auto')
        self.use_gpu = device != 'cpu' and torch.cuda.is_available()
        if device == 'cuda' and not self.use_gpu:
            raise RuntimeError('没有可用的 CUDA。请改选自动或 CPU。')
        self.dtype = torch.bfloat16 if self.use_gpu else torch.float32
        self.kwargs = {'dtype': self.dtype, 'attn_implementation': 'sdpa', 'local_files_only': True}
        if self.use_gpu:
            free, _ = torch.cuda.mem_get_info()
            self.kwargs.update(device_map='auto', max_memory={0: max(256*1024**2, free-1200*1024**2), 'cpu': '22GiB'})
        else:
            self.kwargs['device_map'] = 'cpu'
            torch.set_num_threads(min(8, os.cpu_count() or 4))
        emit('load_asr', '加载 Qwen3-ASR-1.7B（GPU/CPU 自动分配）' if self.use_gpu else '加载 Qwen3-ASR-1.7B（CPU）', 8)
        self.processor = AutoProcessor.from_pretrained(self.asr_dir, local_files_only=True)
        self.model = AutoModelForMultimodalLM.from_pretrained(self.asr_dir, **self.kwargs).eval()
        self.placement = {k: str(v) for k, v in getattr(self.model, 'hf_device_map', {}).items()}
        self.execution = {'device': str(self.model.device), 'dtype': str(self.dtype), 'backend': 'transformers',
                          'asr_first_parameter_device': str(self.model.device), 'cuda_available': torch.cuda.is_available(),
                          'torch': torch.__version__, 'model_dir': str(self.asr_dir),
                          'asr_cuda_allocated_mb': round(torch.cuda.memory_allocated()/1024**2) if self.use_gpu else 0}

    def transcribe(self, path, uttid):
        import torch
        import soundfile as sf
        from .engine import recognition_inputs
        samples, _ = sf.read(path, dtype='float32')
        inputs = recognition_inputs(self.processor, samples, self.config.get('language', 'Chinese'), self.config.get('hotwords', ''))
        inputs = inputs.to(self.model.device, self.dtype)
        with torch.inference_mode():
            ids = self.model.generate(**inputs, max_new_tokens=2048, do_sample=False)
        generated = ids[:, inputs['input_ids'].shape[1]:]
        if generated.shape[1] >= 2048:
            raise RuntimeError('识别达到输出长度上限，请使用更短的音频分块。')
        parsed = self.processor.decode(generated, return_format='parsed')[0]
        return {'text': parsed['transcription'], 'language': parsed.get('language') or 'Chinese', 'raw': parsed}

    def load_aligner(self, emit):
        import torch
        from transformers import AutoProcessor, AutoModelForTokenClassification
        self.close()
        if self.use_gpu:
            free, _ = torch.cuda.mem_get_info()
            self.kwargs['max_memory'] = {0: max(256*1024**2, free-800*1024**2), 'cpu': '22GiB'}
        emit('load_align', '加载 Qwen3-ForcedAligner-0.6B，计算字词时间位置', 55)
        self.processor = AutoProcessor.from_pretrained(self.align_dir, local_files_only=True)
        self.model = AutoModelForTokenClassification.from_pretrained(self.align_dir, **self.kwargs).eval()
        self.execution['aligner_first_parameter_device'] = str(self.model.device)
        self.execution['aligner_model_dir'] = str(self.align_dir)

    def align(self, chunk):
        import torch
        import soundfile as sf
        samples, _ = sf.read(chunk['path'], dtype='float32')
        inputs, word_lists = self.processor.prepare_forced_aligner_inputs(
            audio=samples, transcript=chunk['text'], language=chunk['language'])
        inputs = inputs.to(self.model.device, self.dtype)
        with torch.inference_mode():
            outputs = self.model(**inputs)
        return self.processor.decode_forced_alignment(logits=outputs.logits, input_ids=inputs['input_ids'],
                    word_lists=word_lists, timestamp_token_id=self.model.config.timestamp_token_id)[0]

    def close(self):
        self.model = None
        self.processor = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
