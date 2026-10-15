"""
Inbox importer: drag-and-drop alternative to the upload screen.

    seed/inbox/<shop_id>/<general|main|snack|drink>/*.jpg|png|webp|heic

For each photo: file it through photo_store (upright, shrunk, EXIF/GPS removed,
duplicates skipped), read every product and meal deal sign with Claude, and queue
them as PENDING (submitted_via="seed") for the team to check in the Review queue.
Nothing is auto-approved. Imported originals are MOVED (never deleted) to
seed/inbox_done/ with the same folder layout; photos that fail stay in the inbox so
a re-run retries them.
"""

from __future__ import annotations

import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from PIL import Image

import approval
from extract import build_deal, build_item, extract_photo, is_usable
from nutrition_fill import fill_missing
from photo_store import PHOTO_TYPES, UPLOAD_EXTENSIONS, save_photo, set_storefront, storefront_upload

DEFAULT_INBOX = Path(__file__).parent / "seed" / "inbox"
DONE_DIRNAME = "inbox_done"   # sibling of the inbox
WORKERS = 4
_EXIF_DATETIME_ORIGINAL = 0x9003
_EXIF_DATETIME = 0x0132


@dataclass
class ImportReport:
    photos: int = 0
    items: int = 0
    deals: int = 0
    duplicates: int = 0
    banners: int = 0
    unpriced: list[str] = field(default_factory=list)    # "shop/type/file: product"
    failed: list[str] = field(default_factory=list)      # "shop/type/file: error"
    skipped_folders: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Imported {self.photos} photo(s): {self.items} product(s), {self.deals} deal sign(s) "
            f"queued for review; {self.duplicates} duplicate(s) skipped; {self.banners} shop banner(s) set.",
        ]
        if self.unpriced:
            lines.append(f"{len(self.unpriced)} product(s) had no readable price and no meal deal marking, so were NOT queued "
                         "(retake, or add them in the app):")
            lines += [f"  - {u}" for u in self.unpriced]
        if self.failed:
            lines.append(f"{len(self.failed)} photo(s) failed and were left in the inbox:")
            lines += [f"  - {f}" for f in self.failed]
        if self.skipped_folders:
            lines.append("Ignored folders (not a known shop / photo type):")
            lines += [f"  - {s}" for s in self.skipped_folders]
        return "\n".join(lines)


def ensure_inbox(inbox: Path, shop_ids: list[str]) -> None:
    """Create the empty folder skeleton so people know where to drop photos."""
    for shop_id in shop_ids:
        for photo_type in PHOTO_TYPES:
            (inbox / shop_id / photo_type).mkdir(parents=True, exist_ok=True)


def photo_taken_date(data: bytes) -> date | None:
    """Date the photo was taken, from EXIF (read before photo_store strips it)."""
    try:
        exif = Image.open(io.BytesIO(data)).getexif()
        raw = exif.get_ifd(0x8769).get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").date() if raw else None
    except Exception:
        return None


def _find_photos(inbox: Path, shop_ids: set[str], report: ImportReport) -> list[tuple[str, str, Path]]:
    found = []
    extensions = {f".{e}" for e in UPLOAD_EXTENSIONS}
    for shop_dir in sorted(p for p in inbox.iterdir() if p.is_dir()) if inbox.exists() else []:
        for type_dir in sorted(p for p in shop_dir.iterdir() if p.is_dir()):
            if shop_dir.name not in shop_ids or type_dir.name not in PHOTO_TYPES:
                if any(type_dir.iterdir()):
                    report.skipped_folders.append(f"{shop_dir.name}/{type_dir.name}")
                continue
            for photo in sorted(type_dir.iterdir()):
                if photo.is_file() and photo.suffix.lower() in extensions:
                    found.append((shop_dir.name, type_dir.name, photo))
    return found


def _move_done(src: Path, inbox: Path) -> None:
    """Keep the full-resolution original, out of the inbox."""
    target = inbox.parent / DONE_DIRNAME / src.relative_to(inbox)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem}_{datetime.now():%H%M%S%f}{target.suffix}")
    src.replace(target)


def _in_db(conn: sqlite3.Connection, rel_path: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM items WHERE source_image = ? UNION SELECT 1 FROM deals WHERE source_image = ?",
        (rel_path, rel_path),
    ).fetchone() is not None


def import_inbox(
    conn: sqlite3.Connection,
    inbox: Path = DEFAULT_INBOX,
    workers: int = WORKERS,
    log: Callable[[str], None] = print,
) -> ImportReport:
    report = ImportReport()
    shop_ids = {r["shop_id"] for r in conn.execute("SELECT shop_id FROM shops")}
    photos = _find_photos(inbox, shop_ids, report)
    if not photos:
        log(f"No photos in {inbox}. Drop them into <shop_id>/<{'|'.join(PHOTO_TYPES)}>/ and re-run.")
        return report

    # 1. File every photo (fast, local) and drop duplicates already in the DB
    todo = []
    for shop_id, photo_type, src in photos:
        label = f"{shop_id}/{photo_type}/{src.name}"
        try:
            data = src.read_bytes()
            taken = photo_taken_date(data) or date.today()
            saved = save_photo(shop_id, photo_type, data, today=taken)
        except Exception as exc:
            report.failed.append(f"{label}: couldn't open image ({exc})")
            continue
        if saved.already_existed and _in_db(conn, saved.rel_path):
            report.duplicates += 1
            _move_done(src, inbox)
            continue
        todo.append((shop_id, photo_type, src, saved, taken, label))

    # 2. Read photos with Claude in parallel; write to SQLite on this thread only
    log(f"Reading {len(todo)} photo(s) with Claude ({workers} at a time)…")

    def _read(job):
        shop_id, photo_type, _, saved, _, _ = job
        return extract_photo(saved.path, shop_id, photo_type)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [(job, pool.submit(_read, job)) for job in todo]
        for n, (job, future) in enumerate(futures, start=1):
            shop_id, photo_type, src, saved, taken, label = job
            try:
                result = future.result()
            except Exception as exc:
                report.failed.append(f"{label}: {exc}")
                log(f"  [{n}/{len(todo)}] FAIL {label}")
                continue

            queued = 0
            for fields in result.items:
                fields = fill_missing(conn, fields)   # barcode: our data, then Open Food Facts
                if not is_usable(fields):           # no own price and not in the meal deal
                    report.unpriced.append(f"{label}: {fields.get('name')}")
                    continue
                try:
                    item = build_item(fields, shop_id, saved.rel_path, taken, None, submitted_via="seed")
                except Exception as exc:
                    report.unpriced.append(f"{label}: {fields.get('name')} (invalid: {exc})")
                    continue
                data = item.model_dump()
                data["last_seen"] = item.last_seen.isoformat()
                approval.queue_item(conn, data)
                queued += 1
            for fields in result.deals:
                deal = build_deal(fields, shop_id, saved.rel_path, taken, None)
                data = deal.model_dump()
                data["last_seen"] = deal.last_seen.isoformat()
                approval.queue_deal(conn, data)
                report.deals += 1
            if photo_type == "general" and result.kind == "storefront" and storefront_upload(shop_id) is None:
                set_storefront(shop_id, saved.path)
                report.banners += 1

            report.items += queued
            report.photos += 1
            _move_done(src, inbox)
            log(f"  [{n}/{len(todo)}] OK   {label}: {queued} product(s), {len(result.deals)} deal(s)"
                + (f" · {result.notes}" if result.notes else ""))

    return report
