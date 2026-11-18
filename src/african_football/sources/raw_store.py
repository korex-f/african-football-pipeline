"""
raw_store.py — Keep the pages that the source adapters get.

The store keeps the pages of one season of one league from one source
in one folder:

    data/sources/soccerway/gh_pl/2023-2024/
        manifest.json
        results.html.gz
        matches/h4zYGtCC.html.gz

The manifest has one entry for each page: the URL, the file path,
the fetch time, the sha256 value and the timezone.
"""

import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Optional

from african_football.sources.base import RawDocument

MANIFEST_NAME = "manifest.json"


class RawStoreError(Exception):
    """A stored page is missing, damaged, or has an unsafe name."""


class RawStore:
    """
    The stored pages of one season of one league from one source.

    Usage:
        store = RawStore(Path("data/sources"), "soccerway", "gh_pl", "2023/2024")
        if not store.has(url, "Africa/Accra"):
            store.save(url, "results.html", html, "Africa/Accra")
        html = store.load(store.get(url))
    """

    def __init__(self, root: Path, source: str, league_code: str, season: str):
        """Open the store folder. Read the manifest if it exists.

        The folder is root/source/league_code/season. Change each '/'
        in the season label to '-', for example '2023/2024' to '2023-2024'.
        Do not make the folder here. Make it in save().
        """
        self._source = source
        self._folder = root / source / league_code / season.replace("/", "-")
        # Key: URL. A dict keeps the insertion sequence.
        self._documents: dict[str, RawDocument] = {}

        manifest = self._folder / MANIFEST_NAME
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for entry in data["documents"]:
                doc = RawDocument(
                    source=self._source,
                    url=entry["url"],
                    path=entry["path"],
                    fetched_at=datetime.fromisoformat(entry["fetched_at"]),
                    sha256=entry["sha256"],
                    timezone=entry["timezone"],
                )
                self._documents[doc.url] = doc

    @property
    def folder(self) -> Path:
        """The season folder."""
        return self._folder

    def has(self, url: str, timezone: str) -> bool:
        """Return True if the store has the page for this URL and timezone."""
        doc = self._documents.get(url)
        return doc is not None and doc.timezone == timezone

    def get(self, url: str) -> Optional[RawDocument]:
        """Return the stored document for this URL, or None."""
        return self._documents.get(url)

    def documents(self) -> list[RawDocument]:
        """Return all stored documents, in the sequence of save()."""
        return list(self._documents.values())

    def save(self, url: str, name: str, html: str, timezone: str) -> RawDocument:
        """Keep a page and add it to the manifest. Return its document.

        Rules:
          - `name` is the file path in the season folder, for example
            'matches/h4zYGtCC.html'. Add '.gz' to it.
          - Raise RawStoreError if `name` is not safe.
          - Calculate sha256 from the HTML text (UTF-8), not from the
            compressed file.
          - Write the page file first. Then write the manifest.
          - Write the manifest atomically.
          - If the URL is in the manifest, replace its entry.
        """
        p = PurePosixPath(name)
        if not name or p.is_absolute() or ".." in p.parts:
            raise RawStoreError(f"Invalid rawstore path: {name!r}")

        path = name + ".gz"
        file = self._folder / path
        file.parent.mkdir(parents=True, exist_ok=True)

        data = html.encode("utf-8")
        sha256 = hashlib.sha256(data).hexdigest()
        file.write_bytes(gzip.compress(data))

        doc = RawDocument(
            source=self._source,
            url=url,
            path=path,
            fetched_at=datetime.now(UTC),
            sha256=sha256,
            timezone=timezone,
        )

        self._documents[url] = doc

        self._write_manifest()

        return doc

    def _write_manifest(self) -> None:
        """Write all documents to the manifest. Replace the old manifest atomically."""
        entries = []
        for doc in self._documents.values():
            entries.append(
                {
                    "url": doc.url,
                    "path": doc.path,
                    "fetched_at": doc.fetched_at.isoformat(),
                    "sha256": doc.sha256,
                    "timezone": doc.timezone,
                }
            )
        tmp = self._folder / (MANIFEST_NAME + ".tmp")
        tmp.write_text(json.dumps({"documents": entries}, indent=2), encoding="utf-8")
        tmp.replace(self._folder / MANIFEST_NAME)

    def load(self, document: RawDocument) -> str:
        """Return the HTML text of a stored page.

        Raise RawStoreError if the file is missing, or if its sha256
        value is not the value in the document.
        """
        file = self._folder / document.path
        if not file.exists():
            raise RawStoreError(f"File does not exist: {file}")

        try:
            data = gzip.decompress(file.read_bytes())
        except gzip.BadGzipFile as error:
            raise RawStoreError(f"The file is not a valid gzip: {file}") from error

        if hashlib.sha256(data).hexdigest() != document.sha256:
            raise RawStoreError(f"The sha256 value is not correct: {file}")

        return data.decode("utf-8")
