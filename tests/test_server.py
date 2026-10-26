import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from slidehouse.server import App, Handler, SlideCounter

DOC = """<!DOCTYPE html><html><head><title>{title}</title></head>
<body><div class="reveal"><div class="slides"><section data-id="s1">one</section>
<section data-id="s2"><section data-id="s2a">nested</section></section></div></div></body></html>"""


def request(url, data=None, headers=None):
    body = None if data is None else json.dumps(data).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(req, timeout=10) as reply:
            return reply.status, reply.read(), reply.headers
    except HTTPError as error:
        return error.code, error.read(), error.headers


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.decks = self.root / "decks"
        for name, title in (("slides_a", "Alpha"), ("slides_b", "Beta")):
            folder = self.decks / name
            (folder / "assets").mkdir(parents=True)
            (folder / "index.html").write_text(DOC.format(title=title))
            (folder / "assets" / "pic.svg").write_text("<svg/>")

        app_dir = Path(__file__).resolve().parents[1] / "slidehouse"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.app = App(app_dir, self.decks)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.app.transfers.close()
        self.tmp.cleanup()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def test_editor_shell_and_app_assets(self):
        status, body, _ = request(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"SlideHouse", body)
        status, body, _ = request(self.base + "/app/js/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"pasteFromStorage", body)

    def test_decks_list_and_read(self):
        status, body, _ = request(self.base + "/api/decks")
        self.assertEqual(status, 200)
        self.assertEqual([deck["id"] for deck in json.loads(body)], ["slides_a", "slides_b"])
        status, body, _ = request(self.base + "/api/deck/slides_a")
        self.assertEqual(status, 200)
        self.assertIn("Alpha", json.loads(body)["html"])

    def test_static_roots_are_separate_and_contained(self):
        self.assertEqual(request(self.base + "/decks/slides_a/index.html")[0], 200)
        self.assertEqual(request(self.base + "/decks/slides_a/assets/pic.svg")[0], 200)
        self.assertEqual(request(self.base + "/app/%2e%2e/decks/slides_a/index.html")[0], 404)
        self.assertEqual(request(self.base + "/decks/../README.md")[0], 404)
        self.assertEqual(request(self.base + "/decks/slides_a/.hidden")[0], 403)

    def test_cross_origin_writes_are_refused(self):
        status, body, _ = request(self.base + "/api/transfers/prepare",
                                  {"deck": "slides_a", "refs": []},
                                  {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

    def test_save_and_revision_conflict(self):
        status, body, _ = request(self.base + "/api/deck/slides_a")
        payload = json.loads(body)
        status, body, _ = request(self.base + "/api/save",
                                  {"deck": "slides_a", "revision": payload["revision"],
                                   "html": payload["html"].replace("one", "edited")})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["backup"].endswith(".html"))
        status, body, _ = request(self.base + "/api/save",
                                  {"deck": "slides_a", "revision": "stale", "html": payload["html"]})
        self.assertEqual(status, 409)

    def test_prepare_and_materialize_assets(self):
        status, body, _ = request(self.base + "/api/transfers/prepare",
                                  {"deck": "slides_a", "refs": ["assets/pic.svg"]})
        self.assertEqual(status, 200)
        staged = json.loads(body)
        status, body, _ = request(self.base + "/api/transfers/materialize",
                                  {"transferId": staged["transferId"], "deck": "slides_b"})
        self.assertEqual(status, 200)
        copied = json.loads(body)["refs"]["assets/pic.svg"]
        self.assertTrue((self.decks / "slides_b" / copied).is_file())

    def test_duplicate_deck(self):
        status, body, _ = request(self.base + "/api/decks/duplicate",
                                  {"sourceDeck": "slides_a", "destinationDeck": "slides_copy"})
        self.assertEqual(status, 200)
        self.assertTrue((self.decks / "slides_copy" / "assets" / "pic.svg").is_file())
        status, _, _ = request(self.base + "/api/decks/duplicate",
                               {"sourceDeck": "slides_a", "destinationDeck": "slides_copy"})
        self.assertEqual(status, 400)

    def test_page_counter(self):
        self.assertEqual(SlideCounter(DOC.format(title="x")).pages, 2)
        self.assertEqual(SlideCounter("<section><section>a</section></section>").pages, 1)
        self.assertEqual(SlideCounter("<p>empty</p>").pages, 1)


if __name__ == "__main__":
    unittest.main()
