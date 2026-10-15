"""
Photo file system: every uploaded photo is filed by shop and photo type.

    uploads/
      <shop_id>/
        general/        storefront, meal deal signs, whole-shelf shots
          storefront.jpg   the shop page banner (set from a general photo)
        main/
        snack/
        drink/

Saving normalises each photo: HEIC → JPEG, rotated upright from its EXIF
orientation, shrunk to MAX_SIDE px, and re-saved WITHOUT EXIF (so GPS location
is never stored). Filenames are a content hash, so re-uploading the same photo
is detected instead of creating a duplicate.
"""

from __future__ import annotations

import hashlib
import io
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps

try:  # iPhone photos
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:  # pragma: no cover
    HEIC_SUPPORTED = False

UPLOAD_ROOT = Path(__file__).parent / "uploads"
PHOTO_TYPES = ("main", "snack", "drink", "general")
PHOTO_TYPE_LABELS = {"main": "Main", "snack": "Snack", "drink": "Drink", "general": "General (shop)"}
UPLOAD_EXTENSIONS = ["jpg", "jpeg", "png", "webp"] + (["heic", "heif"] if HEIC_SUPPORTED else [])
MAX_SIDE = 2000          # px; Claude downsizes anything bigger anyway
JPEG_QUALITY = 88


@dataclass
class SavedPhoto:
    path: Path               # absolute path on disk
    rel_path: str            # path relative to UPLOAD_ROOT, stored as source_image
    already_existed: bool    # same photo uploaded before


def photo_dir(shop_id: str, photo_type: str) -> Path:
    if photo_type not in PHOTO_TYPES:
        raise ValueError(f"photo_type must be one of {PHOTO_TYPES}, got {photo_type!r}")
    if not shop_id or "/" in shop_id or ".." in shop_id:
        raise ValueError(f"bad shop_id {shop_id!r}")
    return UPLOAD_ROOT / shop_id / photo_type


def normalise_image(data: bytes) -> bytes:
    """Upright, RGB, at most MAX_SIDE px, JPEG with no EXIF/GPS."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)   # no exif= → metadata dropped
    return out.getvalue()


def save_photo(shop_id: str, photo_type: str, data: bytes, today: date | None = None) -> SavedPhoto:
    """File a photo under uploads/<shop_id>/<photo_type>/<date>_<hash>.jpg."""
    directory = photo_dir(shop_id, photo_type)
    digest = hashlib.sha256(data).hexdigest()[:12]

    existing = next(directory.glob(f"*_{digest}.jpg"), None) if directory.exists() else None
    if existing is not None:
        return SavedPhoto(existing, existing.relative_to(UPLOAD_ROOT).as_posix(), True)

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{(today or date.today()).isoformat()}_{digest}.jpg"
    path.write_bytes(normalise_image(data))
    return SavedPhoto(path, path.relative_to(UPLOAD_ROOT).as_posix(), False)


def strip_gps_in_place(path: Path) -> bool:
    """
    Remove GPS (and the EXIF thumbnail) from a JPEG WITHOUT re-encoding it: pixels
    and the photo-taken date are untouched. For photos committed to the inbox.
    Returns True if GPS was removed, False if there was none.
    """
    import piexif

    exif = piexif.load(str(path))
    if not exif.get("GPS") and piexif.ImageIFD.GPSTag not in exif["0th"]:
        return False
    exif["GPS"] = {}
    exif["0th"].pop(piexif.ImageIFD.GPSTag, None)
    exif.pop("thumbnail", None)
    exif["1st"] = {}
    piexif.insert(piexif.dump(exif), str(path))
    return True


def set_storefront(shop_id: str, photo: Path) -> Path:
    """Use a general photo as this shop's banner on the shop page."""
    target = photo_dir(shop_id, "general") / "storefront.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(photo, target)
    return target


def storefront_upload(shop_id: str) -> Path | None:
    path = UPLOAD_ROOT / shop_id / "general" / "storefront.jpg"
    return path if path.exists() else None
