"""Tests for the raw page store."""

import gzip
import hashlib
import json
from datetime import timezone

import pytest

from african_football.sources.raw_store import MANIFEST_NAME, RawStore, RawStoreError

URL = "https://ng.soccerway.com/match/a/b/?mid=ttkJbibi"
TZ = "Africa/Accra"
HTML = "<html><body>Asante Kotoko 3 - 1 Bofoakwa Tano é</body></html>"


@pytest.fixture
def store(tmp_path):
    return RawStore(tmp_path, "soccerway", "gh_pl", "2023/2024")


def test_folder_uses_safe_season_name(store, tmp_path):
    assert store.folder == tmp_path / "soccerway" / "gh_pl" / "2023-2024"


def test_new_store_makes_no_folder(store):
    assert not store.folder.exists()
    assert store.documents() == []


def test_save_writes_compressed_page(store):
    doc = store.save(URL, "matches/ttkJbibi.html", HTML, TZ)
    assert doc.path == "matches/ttkJbibi.html.gz"
    file = store.folder / doc.path
    assert gzip.decompress(file.read_bytes()).decode("utf-8") == HTML


def test_save_returns_correct_document(store):
    doc = store.save(URL, "matches/ttkJbibi.html", HTML, TZ)
    assert doc.source == "soccerway"
    assert doc.url == URL
    assert doc.timezone == TZ
    assert doc.sha256 == hashlib.sha256(HTML.encode("utf-8")).hexdigest()
    assert doc.fetched_at.tzinfo == timezone.utc


def test_load_returns_same_html(store):
    doc = store.save(URL, "results.html", HTML, TZ)
    assert store.load(doc) == HTML


def test_has_and_get(store):
    assert not store.has(URL, TZ)
    assert store.get(URL) is None
    doc = store.save(URL, "results.html", HTML, TZ)
    assert store.has(URL, TZ)
    assert store.get(URL) == doc


def test_has_is_false_for_other_timezone(store):
    # Soccerway shows times in the browser timezone. A page that the
    # adapter got in a different timezone has different data.
    store.save(URL, "results.html", HTML, TZ)
    assert not store.has(URL, "Africa/Lagos")


def test_manifest_is_read_again(store, tmp_path):
    # This is how resume works: a new store sees the pages of an old run.
    doc = store.save(URL, "results.html", HTML, TZ)
    again = RawStore(tmp_path, "soccerway", "gh_pl", "2023/2024")
    assert again.has(URL, TZ)
    assert again.get(URL) == doc
    assert again.load(doc) == HTML


def test_manifest_content(store):
    store.save(URL, "results.html", HTML, TZ)
    manifest = json.loads((store.folder / MANIFEST_NAME).read_text())
    [entry] = manifest["documents"]
    assert entry["url"] == URL
    assert entry["path"] == "results.html.gz"
    assert entry["timezone"] == TZ
    assert len(entry["sha256"]) == 64
    assert "fetched_at" in entry


def test_save_same_url_replaces_entry(store):
    store.save(URL, "results.html", "<html>old</html>", TZ)
    doc = store.save(URL, "results.html", HTML, TZ)
    assert store.documents() == [doc]
    assert store.load(doc) == HTML


def test_documents_keep_save_sequence(store):
    urls = [f"https://ng.soccerway.com/match/{i}" for i in range(3)]
    for i, url in enumerate(urls):
        store.save(url, f"matches/m{i}.html", HTML, TZ)
    assert [d.url for d in store.documents()] == urls


def test_same_html_gives_same_sha256(store):
    a = store.save(URL, "results.html", HTML, TZ)
    b = store.save(URL + "&x", "other.html", HTML, TZ)
    assert a.sha256 == b.sha256


@pytest.mark.parametrize(
    "name",
    ["../escape.html", "/etc/escape.html", "matches/../../escape.html", ""],
)
def test_unsafe_name_is_rejected(store, name):
    with pytest.raises(RawStoreError):
        store.save(URL, name, HTML, TZ)


def test_load_detects_damaged_file(store):
    doc = store.save(URL, "results.html", HTML, TZ)
    (store.folder / doc.path).write_bytes(gzip.compress(b"<html>changed</html>"))
    with pytest.raises(RawStoreError):
        store.load(doc)

def test_load_detects_damaged_file_that_is_not_gzip(store):
    doc = store.save(URL, "results.html", HTML, TZ)
    (store.folder / doc.path).write_bytes(b"not gzip")
    with pytest.raises(RawStoreError):
        store.load(doc)


def test_load_detects_missing_file(store):
    doc = store.save(URL, "results.html", HTML, TZ)
    (store.folder / doc.path).unlink()
    with pytest.raises(RawStoreError):
        store.load(doc)


def test_no_temporary_files_remain(store):
    store.save(URL, "results.html", HTML, TZ)
    names = sorted(p.name for p in store.folder.iterdir())
    assert names == [MANIFEST_NAME, "results.html.gz"]
