import tempfile
import unittest
from pathlib import Path

from slidehouse.decks import (DeckChanged, DeckError, check_name, duplicate_deck, list_decks,
                              read_deck, revision, save_deck)

DOC = """<!DOCTYPE html><html><head><title>{title}</title></head>
<body><div class="reveal"><div class="slides"><section data-id="s1">one</section></div></div></body></html>"""


def make_deck(root: Path, name: str, title: str = "Deck") -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "index.html").write_text(DOC.format(title=title))
    return folder


class DeckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_deck(self.root, "slides_one", "First deck")
        make_deck(self.root, "slides_two", "Second deck")

    def tearDown(self):
        self.tmp.cleanup()

    def test_names(self):
        self.assertEqual(check_name("slides_my-talk_2"), "slides_my-talk_2")
        for bad in ("my-talk", "slides_a/b", "", "../slides_a", "slides_ä"):
            with self.assertRaises(DeckError):
                check_name(bad)

    def test_list_and_read(self):
        decks = list_decks(self.root)
        self.assertEqual([deck["id"] for deck in decks], ["slides_one", "slides_two"])
        self.assertEqual(decks[0]["title"], "First deck")
        html, rev = read_deck(self.root, "slides_one")
        self.assertIn("First deck", html)
        self.assertEqual(rev, revision(html.encode()))

    def test_save_writes_backup_and_new_revision(self):
        html, rev = read_deck(self.root, "slides_one")
        new = html.replace("one", "edited")
        result = save_deck(self.root, "slides_one", new, rev)
        self.assertEqual((self.root / "slides_one/index.html").read_text(), new)
        self.assertEqual(result["revision"], revision(new.encode()))
        backup = self.root / result["backup"]
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(), html)

    def test_save_refuses_stale_revision(self):
        _, rev = read_deck(self.root, "slides_one")
        with self.assertRaises(DeckChanged):
            save_deck(self.root, "slides_one", DOC.format(title="Other"), "not-the-revision")
        self.assertIn("First deck", (self.root / "slides_one/index.html").read_text())

    def test_save_refuses_incomplete_document(self):
        _, rev = read_deck(self.root, "slides_one")
        with self.assertRaises(DeckError):
            save_deck(self.root, "slides_one", "<p>not a deck</p>", rev)

    def test_duplicate_copies_assets_and_skips_backups(self):
        source = self.root / "slides_one"
        (source / "assets").mkdir()
        (source / "assets" / "figure.svg").write_text("<svg/>")
        (self.root / ".slidehouse-backups" / "slides_one").mkdir(parents=True)
        (self.root / ".slidehouse-backups" / "slides_one" / "old.html").write_text("old")
        result = duplicate_deck(self.root, "slides_one", "slides_copy")
        target = self.root / result["id"]
        self.assertTrue((target / "index.html").is_file())
        self.assertTrue((target / "assets" / "figure.svg").is_file())
        self.assertFalse((target / ".slidehouse-backups").exists())

    def test_duplicate_refuses_collision_and_same_name(self):
        with self.assertRaises(DeckError):
            duplicate_deck(self.root, "slides_one", "slides_two")
        with self.assertRaises(DeckError):
            duplicate_deck(self.root, "slides_one", "slides_one")

    def test_missing_deck(self):
        with self.assertRaises(DeckError):
            read_deck(self.root, "slides_missing")


if __name__ == "__main__":
    unittest.main()
