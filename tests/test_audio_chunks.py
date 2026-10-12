import tempfile
from pathlib import Path
import unittest
import wave
import numpy as np
from transcriber.engine import split_audio


class AudioChunkTests(unittest.TestCase):
    def test_long_audio_has_full_coverage_with_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sr = 16000
            # Continuous speech-like energy, with a quiet boundary near 39 seconds.
            audio = (np.sin(np.arange(sr*100)*.08)*8000).astype(np.int16)
            audio[sr*39:sr*40] = 0
            path = root/'long.wav'
            with wave.open(str(path), 'wb') as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
                f.writeframes(audio.tobytes())
            duration, chunks = split_audio(path, root)
            self.assertEqual(duration, 100)
            self.assertGreater(len(chunks), 1)
            self.assertEqual(chunks[0]['core_start'], 0)
            self.assertEqual(chunks[-1]['core_end'], duration)
            for left, right in zip(chunks, chunks[1:]):
                self.assertEqual(left['core_end'], right['core_start'])
                self.assertLess(right['offset'], right['core_start'])
            for chunk in chunks:
                with wave.open(chunk['path'], 'rb') as f:
                    self.assertLessEqual(f.getnframes()/sr, 46.61)
            self.assertTrue(39 <= chunks[0]['core_end'] <= 40)


if __name__ == '__main__':
    unittest.main()
