import tempfile
import unittest
from pathlib import Path

from slidehouse.transfers import TransferError, TransferStore

DOC = """<!DOCTYPE html><html><head><title>Deck</title></head>
<body><div class="reveal"><div class="slides"><section data-id="s1">one</section></div></div></body></html>"""


def make_deck(root: Path, name: str) -> Path:
    folder = root / name
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(DOC)
    (folder / "assets" / "figure.svg").write_text("<svg id='figure'/>")
    (folder / "assets" / "font.woff").write_bytes(b"font-bytes")
    return folder


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_deck(self.root, "slides_source")
        make_deck(self.root, "slides_target")
        self.store = TransferStore(self.root)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_prepare_and_materialize(self):
        staged = self.store.prepare("slides_source", ["assets/figure.svg"])
        self.assertEqual(staged["missing"], [])
        self.assertEqual(len(staged["refs"]), 1)
        result = self.store.materialize(staged["transferId"], "slides_target")
        copied = self.root / "slides_target" / result["refs"]["assets/figure.svg"]
        self.assertTrue(copied.is_file())
        self.assertEqual(copied.read_text(), "<svg id='figure'/>")

    def test_remote_and_data_refs_are_ignored(self):
        staged = self.store.prepare("slides_source", [
            "https://example.org/image.png", "data:image/png;base64,AAAA"])
        self.assertEqual(staged["refs"], {})
        self.assertEqual(staged["missing"], [])

    def test_missing_local_ref_is_reported(self):
        staged = self.store.prepare("slides_source", ["assets/nope.png"])
        self.assertEqual(staged["missing"], ["assets/nope.png"])

    def test_traversal_is_not_copied(self):
        staged = self.store.prepare("slides_source", ["../slides_target/index.html"])
        self.assertEqual(staged["refs"], {})
        self.assertEqual(len(staged["missing"]), 1)

    def test_unknown_transfer_is_refused(self):
        with self.assertRaises(TransferError):
            self.store.materialize("deadbeef", "slides_target")

    def test_same_asset_is_deduplicated(self):
        first = self.store.prepare("slides_source", ["assets/figure.svg"])
        second = self.store.prepare("slides_source", ["assets/figure.svg"])
        one = self.store.materialize(first["transferId"], "slides_target")["refs"]["assets/figure.svg"]
        two = self.store.materialize(second["transferId"], "slides_target")["refs"]["assets/figure.svg"]
        self.assertEqual(one, two)
        self.assertEqual(len(list((self.root / "slides_target" / "slidehouse-assets").iterdir())), 1)

    def test_duplicate_refs_collapse(self):
        staged = self.store.prepare("slides_source", ["assets/figure.svg", "assets/figure.svg"])
        self.assertEqual(len(staged["refs"]), 1)


if __name__ == "__main__":
    unittest.main()
