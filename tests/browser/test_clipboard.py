"""End-to-end clipboard test in a real browser.

Run directly:      python tests/browser/test_clipboard.py
Or with unittest:  python -m unittest discover -s tests/browser -v

Playwright and a Chrome/Chromium binary are optional: the test skips cleanly
when they are unavailable.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    sync_playwright = None

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "examples" / "slides_demo"


def launch(playwright):
    for kwargs in ({"channel": "chrome"}, {}):
        try:
            return playwright.chromium.launch(headless=True, **kwargs)
        except Exception:
            continue
    return None


@unittest.skipIf(sync_playwright is None, "playwright is not installed")
class ClipboardBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.decks = Path(cls.tmp.name) / "decks"
        cls.decks.mkdir()

        cls.port = 8811
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "slidehouse", "--decks-dir", str(cls.decks), "--port", str(cls.port)],
            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                import urllib.request
                urllib.request.urlopen(cls.base + "/api/build", timeout=1).read()
                break
            except Exception:
                time.sleep(0.1)
        cls.playwright = sync_playwright().start()
        cls.browser = launch(cls.playwright)
        if cls.browser is None:
            cls.tearDownClass()
            raise unittest.SkipTest("Chrome/Chromium is not available for playwright")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "browser", None):
            cls.browser.close()
        if getattr(cls, "playwright", None):
            cls.playwright.stop()
        if getattr(cls, "server", None):
            cls.server.terminate()
            try:
                cls.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server.kill()
        if getattr(cls, "tmp", None):
            cls.tmp.cleanup()

    def setUp(self):
        # Fresh decks per test: one test deletes the source deck on purpose.
        if self.decks.exists():
            shutil.rmtree(self.decks)
        self.decks.mkdir()
        shutil.copytree(DEMO, self.decks / "slides_source")
        shutil.copytree(DEMO, self.decks / "slides_dest")
        # A different canvas and body font make fidelity/scaling observable.
        target = self.decks / "slides_dest" / "index.html"
        html = target.read_text()
        html = html.replace('"width": 1280, "height": 720', '"width": 1920, "height": 1080')
        html = html.replace("width: 1280, height: 720,", "width: 1920, height: 1080,")
        html = html.replace("theme-font-montserrat", "theme-font-lato")
        target.write_text(html)

        self.context = self.browser.new_context(viewport={"width": 1500, "height": 900})
        self.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=self.base)
        self.errors = []
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.open(self.page, "slides_source")

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.context.close()

    def open(self, page, deck):
        page.goto(f"{self.base}/?deck={deck}")
        page.wait_for_selector("#outline button", timeout=20000)
        page.wait_for_timeout(2200)  # reveal.js ready + fonts
        return page

    def slide(self, page, index):
        page.locator("#outline button").nth(index).click()
        page.wait_for_timeout(900)

    def element(self, page, index):
        page.locator("#elements button").nth(index).click()
        page.wait_for_timeout(400)

    def save(self, page):
        page.click("#save")
        page.wait_for_timeout(700)
        return page.inner_text("#status")

    def test_math_paste_scales_and_keeps_latex(self):
        self.slide(self.page, 1)
        self.element(self.page, 2)  # math
        self.page.click("#copy-element")
        self.page.wait_for_timeout(1200)
        self.assertIn("copied", self.page.inner_text("#status"))

        destination = self.open(self.context.new_page(), "slides_dest")
        self.slide(destination, 2)
        before = destination.locator("#elements button").count()
        math_before = (self.decks / "slides_dest" / "index.html").read_text().count('class="math-input"')
        destination.click("#paste-element")
        destination.wait_for_timeout(1600)
        self.assertIn("Pasted", destination.inner_text("#status"))
        self.assertEqual(destination.locator("#elements button").count(), before + 1)

        self.save(destination)
        html = (self.decks / "slides_dest" / "index.html").read_text()
        self.assertEqual(html.count('class="math-input"'), math_before + 1)
        self.assertIn("SlideHouse ", html)
        self.assertIn('data-slidehouse-font="1"', html)
        self.assertIn("@font-face", html)
        # Source canvas 1280x720, destination 1920x1080: uniform factor 1.5.
        self.assertIn("left: 150px; top: 645px", html)
        self.assertIn("font-size: 75px", html)
        self.assertIn("font-size: 60px", html)

        # Identifiers are fresh and unique inside the slide.
        import re
        ids = re.findall(r'data-block-id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))

        # Reload from disk: the pasted block is still there.
        destination.reload()
        destination.wait_for_timeout(2500)
        self.slide(destination, 2)
        self.assertEqual(destination.locator("#elements button").count(), before + 1)

    def test_image_is_portable_after_source_deck_is_removed(self):
        self.slide(self.page, 1)
        self.element(self.page, 3)  # image
        self.page.click("#copy-element")
        self.page.wait_for_timeout(1400)

        destination = self.open(self.context.new_page(), "slides_dest")
        self.slide(destination, 2)
        destination.click("#paste-element")
        destination.wait_for_timeout(1600)
        self.save(destination)

        assets = self.decks / "slides_dest" / "slidehouse-assets"
        self.assertTrue(assets.is_dir())
        self.assertTrue(any(path.suffix == ".svg" for path in assets.iterdir()))

        shutil.rmtree(self.decks / "slides_source")
        viewer = self.context.new_page()
        viewer.goto(f"{self.base}/decks/slides_dest/index.html")
        viewer.wait_for_timeout(2600)
        viewer.evaluate("Reveal.slide(2)")
        viewer.wait_for_timeout(1600)
        images = viewer.evaluate(
            "() => [...document.images].filter(i => i.closest('section.present'))"
            ".map(i => ({src: i.getAttribute('src') || i.getAttribute('data-src'), w: i.naturalWidth}))")
        self.assertTrue(images, "the pasted image is missing")
        self.assertIn("slidehouse-assets/", images[-1]["src"])
        self.assertGreater(images[-1]["w"], 0)

    def test_repeated_paste_undo_redo_and_text_fields(self):
        self.slide(self.page, 1)
        self.element(self.page, 0)  # text
        self.page.click("#copy-element")
        self.page.wait_for_timeout(1200)
        self.slide(self.page, 2)
        initial = self.page.locator("#elements button").count()
        for _ in range(2):
            self.page.click("#paste-element")
            self.page.wait_for_timeout(1200)
        self.assertEqual(self.page.locator("#elements button").count(), initial + 2)

        import re
        html_before = self.page.evaluate("() => document.getElementById('source').value")
        self.assertEqual(len(re.findall(r'data-block-id="([^"]+)"', html_before)),
                         len(set(re.findall(r'data-block-id="([^"]+)"', html_before))))

        self.page.click("#undo")
        self.page.wait_for_timeout(700)
        self.assertEqual(self.page.locator("#elements button").count(), initial + 1)
        self.page.click("#redo")
        self.page.wait_for_timeout(700)
        self.assertEqual(self.page.locator("#elements button").count(), initial + 2)

        # Pasting into a textarea must stay a normal text paste.
        stored = self.page.evaluate("() => localStorage.getItem('slidehouse.clipboard.v1')")
        destination = self.open(self.context.new_page(), "slides_dest")
        before = destination.locator("#elements button").count()
        destination.evaluate("""(text) => {
            const field = document.getElementById('source');
            const event = new ClipboardEvent('paste', {
              bubbles: true, cancelable: true, clipboardData: new DataTransfer()});
            event.clipboardData.setData('text/plain', text);
            field.dispatchEvent(event);
        }""", stored)
        destination.wait_for_timeout(400)
        self.assertEqual(destination.locator("#elements button").count(), before)

    def test_shape_paste_with_keyboard_shortcuts(self):
        self.element(self.page, 0)  # the blue stripe on slide 1
        self.page.keyboard.press("Control+c")
        self.page.wait_for_timeout(1300)
        self.assertIn("copied", self.page.inner_text("#status"))
        self.slide(self.page, 1)
        before = self.page.locator("#elements button").count()
        self.page.keyboard.press("Control+v")
        self.page.wait_for_timeout(1500)
        self.assertIn("Pasted", self.page.inner_text("#status"))
        self.assertEqual(self.page.locator("#elements button").count(), before + 1)
        html = self.page.evaluate("() => document.getElementById('source').value")
        self.assertEqual(html.count('data-shape-type="rectangle"'), 1)
        self.assertIn("#1B5E8C", html)

    def test_slide_names_come_from_text_and_can_be_renamed(self):
        page = self.open(self.context.new_page(), "slides_source")
        labels = page.eval_on_selector_all("#outline .slide", "e => e.map(x => x.firstChild.textContent)")
        self.assertTrue(labels)
        self.assertFalse(any("Untitled" in label for label in labels), labels)
        self.assertIn("Everything is an editable block", labels[1])

        self.slide(page, 1)
        page.dblclick("#outline .slide:nth-child(2)")
        page.wait_for_selector("#slide-name")
        self.assertEqual(page.evaluate("() => document.activeElement.id"), "slide-name")
        page.fill("#slide-name", "Renamed slide")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        self.assertIn("Renamed slide", page.inner_text("#outline .slide:nth-child(2)"))
        self.assertIn("Renamed slide", page.inner_text("#slide-title"))

        self.save(page)
        html = (self.decks / "slides_source" / "index.html").read_text()
        self.assertIn('data-title="Renamed slide"', html)

        page.fill("#slide-name", "")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        self.assertIn("Everything is an editable block", page.inner_text("#outline .slide:nth-child(2)"))

    def test_duplicate_deck_and_deep_link(self):
        page = self.context.new_page()
        page.goto(self.base + "/api/build")
        result = page.evaluate("""async () => (await (await fetch('/api/decks/duplicate', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sourceDeck: 'slides_source', destinationDeck: 'slides_copy'})})).json())""")
        self.assertEqual(result.get("id"), "slides_copy")
        page.goto(self.base + "/?deck=slides_copy")
        page.wait_for_selector("#outline button")
        page.wait_for_timeout(1200)
        self.assertEqual(page.locator("#decks").input_value(), "slides_copy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
