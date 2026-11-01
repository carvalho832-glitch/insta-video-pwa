from pathlib import Path
import re
import unittest
from download_quality import QUALITY_FORMATS, build_command

class QualityTests(unittest.TestCase):
    def test_max_uses_unrestricted_best_source(self):
        cmd=build_command("https://www.instagram.com/reel/abcd/", "video.%(ext)s", "max")
        self.assertEqual(cmd[cmd.index("--format")+1], "bv+ba/b")
        self.assertNotIn("720", cmd[cmd.index("--format")+1])
        self.assertIn("--merge-output-format", cmd)
        self.assertIn("--remux-video", cmd)
        self.assertIn("mp4", cmd)

    def test_limited_qualities_restrict_heights(self):
        for q in ("1080", "720"):
            cmd=build_command("https://fb.watch/abc123/", "video.%(ext)s", q)
            select=cmd[cmd.index("--format")+1]
            self.assertIn("height<="+q, select)
            self.assertTrue(select.startswith("bv["))

    def test_rejects_unexpected_quality(self):
        with self.assertRaises(ValueError):
            build_command("https://example.com/", "video.%(ext)s", "bad")

    def test_output_stays_same(self):
        for q in QUALITY_FORMATS:
            cmd=build_command("https://www.facebook.com/reel/123456/", "video.%(ext)s", q)
            self.assertEqual(cmd[-1], "https://www.facebook.com/reel/123456/")
            self.assertEqual(cmd[-2], "video.%(ext)s")

    def test_form_and_version(self):
        root=Path(__file__).resolve().parent
        html=(root/"web/index.html").read_text(encoding="utf-8")
        self.assertIn('id="videoQuality"', html)
        for val in QUALITY_FORMATS:
            self.assertIn('value="'+val+'"', html)
        self.assertIn("JSON.stringify({url,quality:qualitySelect.value})",html)
        self.assertIn("reelsalva-v4",(root/"web/sw.js").read_text(encoding="utf-8"))
        self.assertIn("ffmpeg",(root/"Dockerfile").read_text(encoding="utf-8"))

    def test_yt_dlp_accepts_format_syntax(self):
        from yt_dlp import YoutubeDL
        ydl=YoutubeDL({"quiet":True,"format_sort":["res","fps","codec:h264:m4a","ext:mp4:m4a"]})
        for quality,expression in QUALITY_FORMATS.items():
            self.assertTrue(callable(ydl.build_format_selector(expression)),quality)

if __name__=="__main__":
    unittest.main()
