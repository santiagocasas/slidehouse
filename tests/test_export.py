import tempfile
import unittest
from pathlib import Path

from slidehouse.export import standalone_html


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.deck = Path(self.tmp.name) / "slides_demo"
        (self.deck / "assets").mkdir(parents=True)
        (self.deck / "assets" / "pic.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        (self.deck / "app.js").write_text("window.inlined = true;")
        (self.deck / "more.css").write_text("h1 { color: #123456; }")
        (self.deck / "style.css").write_text(
            '@import url("more.css");\nbody { background: url("assets/pic.svg"); }')
        self.html = ('<!DOCTYPE html><html><head><title>Deck</title>'
                     '<link rel="stylesheet" href="style.css"></head>'
                     '<body class="reveal theme-font-montserrat"><div class="slides">'
                     '<section><img src="assets/pic.svg"><img src="https://example.org/x.png"></section>'
                     '</div><script src="app.js"></script></body></html>')

    def tearDown(self):
        self.tmp.cleanup()

    def test_css_scripts_and_media_are_inlined(self):
        result = standalone_html(self.html, self.deck)
        self.assertNotIn('href="style.css"', result)
        self.assertNotIn('src="app.js"', result)
        self.assertIn("window.inlined = true", result)
        self.assertIn("h1 { color: #123456; }", result)
        self.assertIn("data:image/svg+xml;base64,", result)

    def test_external_urls_are_left_alone(self):
        result = standalone_html(self.html, self.deck)
        self.assertIn('src="https://example.org/x.png"', result)

    def test_missing_files_do_not_break_export(self):
        html = self.html.replace('assets/pic.svg', 'assets/missing.png')
        result = standalone_html(html, self.deck)
        self.assertIn('src="assets/missing.png"', result)


if __name__ == "__main__":
    unittest.main()
