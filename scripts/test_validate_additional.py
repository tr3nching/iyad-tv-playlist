import subprocess, unittest
from unittest.mock import patch
from validate_additional import validate

class PlaybackValidationTests(unittest.TestCase):
    row = {'id':'safe-hash', 'channel':'additional:test', 'url':'https://example.com/private?token=secret', 'headers':{}}

    def test_manifest_success_without_decoded_frames_is_not_playback(self):
        with patch('validate_additional.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'frame=0\n', b'')):
            self.assertFalse(validate(self.row, 'ffmpeg')['validated'])

    def test_decoded_video_passes_without_exposing_url(self):
        with patch('validate_additional.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'frame=25\n', b'')):
            result = validate(self.row, 'ffmpeg')
            self.assertTrue(result['validated'])
            self.assertNotIn('secret', str(result))

    def test_timeout_without_video_is_not_validated(self):
        with patch('validate_additional.subprocess.run', side_effect=subprocess.TimeoutExpired([], 65, output=b'frame=0\n')):
            self.assertFalse(validate(self.row, 'ffmpeg')['validated'])

if __name__ == '__main__': unittest.main()
