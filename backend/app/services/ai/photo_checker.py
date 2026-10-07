"""Базовая проверка фото: метаданные EXIF, качество снимка и сравнение «до/после».

Без тяжёлых ML-зависимостей: перцептивный хэш (dHash), резкость по дисперсии
градиента и средняя яркость считаются средствами Pillow.
"""

import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import ExifTags, Image, ImageFilter, ImageStat

from app.core.config import settings

HASH_SIZE = 8  # 64-битный dHash
# 64 Мп — с запасом для камер телефонов (50 Мп). Больше — почти наверняка «бомба»:
# маленький файл, который при распаковке занимает гигабайты памяти.
MAX_PIXELS = 64_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # свыше 2× Pillow сам бросит DecompressionBombError
# между 1× и 2× Pillow только предупреждает — размер проверяем сами в validate_image
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

_TAGS = {v: k for k, v in ExifTags.TAGS.items()}


class ImageTooLarge(ValueError):
    pass


def validate_image(path: Path) -> None:
    """Проверка до декодирования: файл — картинка разумного размера (читается только заголовок)."""
    with Image.open(path) as img:
        if img.width * img.height > MAX_PIXELS:
            raise ImageTooLarge(f"{img.width}×{img.height}")
        img.verify()


def analyze_photo(path: Path) -> dict:
    """Метаданные одного фото — сохраняются в OrderPhoto.meta при загрузке."""
    with Image.open(path) as img:
        width, height = img.size
        exif = img.getexif()
        ifd = exif.get_ifd(ExifTags.IFD.Exif) if exif else {}
        taken_raw = ifd.get(_TAGS["DateTimeOriginal"]) or exif.get(_TAGS["DateTime"])
        offset_raw = ifd.get(_TAGS["OffsetTimeOriginal"]) or ifd.get(_TAGS["OffsetTime"])
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo) if exif else {}

        # JPEG декодируется сразу в уменьшенном виде — память не растёт с разрешением камеры
        img.draft("L", (1024, 1024))
        gray = img.convert("L")
        gray.thumbnail((512, 512))
        sharpness = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]
        brightness = ImageStat.Stat(gray).mean[0]

        return {
            "width": width,
            "height": height,
            "has_exif": bool(exif),
            "camera": " ".join(filter(None, [exif.get(_TAGS["Make"]), exif.get(_TAGS["Model"])])) or None,
            "taken_at": _parse_exif_dt(taken_raw, offset_raw),
            "has_gps": bool(gps),
            "sharpness": round(sharpness, 1),
            "brightness": round(brightness, 1),
            "dhash": _dhash(gray),
        }


def _parse_exif_dt(raw, offset_raw=None) -> str | None:
    """Время съёмки. Камера пишет местное время; пояс берём из OffsetTimeOriginal, иначе — пояс предприятия."""
    if not raw:
        return None
    try:
        taken = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    tz = timezone(timedelta(hours=settings.plant_utc_offset_hours))
    if offset_raw:
        try:
            tz = datetime.strptime(str(offset_raw).strip(), "%z").tzinfo or tz
        except ValueError:
            pass
    return taken.replace(tzinfo=tz).isoformat()


def _dhash(img: Image.Image) -> str:
    small = img.convert("L").resize((HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS)
    px = list(small.getdata())
    bits = 0
    for row in range(HASH_SIZE):
        for col in range(HASH_SIZE):
            left = px[row * (HASH_SIZE + 1) + col]
            right = px[row * (HASH_SIZE + 1) + col + 1]
            bits = (bits << 1) | (left > right)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


@dataclass
class PhotoCheck:
    score: float  # 1–5
    issues: list[str]
    notes: list[str]


def assess_photos(before: list[dict], after: list[dict], order_created_at: datetime) -> PhotoCheck:
    """Оценка качества фотофиксации наряда от 1 до 5."""
    if not after:
        return PhotoCheck(1.0, ["Нет фото «после»"], [])

    score = 5.0
    issues: list[str] = []
    notes: list[str] = []

    if not any(m.get("has_exif") for m in after):
        score -= 1.0
        issues.append("У фото «после» нет EXIF-метаданных (возможно, снимок не с камеры или переслан)")
    for m in after:
        taken = m.get("taken_at")
        if taken and datetime.fromisoformat(taken) < order_created_at.replace(microsecond=0):
            score -= 1.5
            issues.append("Фото «после» сделано раньше выдачи наряда")
            break

    if all(m.get("sharpness", 0) < 60 for m in after):
        score -= 1.0
        issues.append("Фото «после» размыто или слишком мелкое")
    if all(m.get("brightness", 128) < 25 or m.get("brightness", 128) > 245 for m in after):
        score -= 0.5
        issues.append("Фото «после» пересвечено или слишком тёмное")

    if before:
        dists = [
            hamming(b["dhash"], a["dhash"])
            for b in before
            for a in after
            if b.get("dhash") and a.get("dhash")
        ]
        if dists:
            closest = min(dists)
            if closest <= 2:
                score -= 2.0
                issues.append("Фото «после» практически идентично фото «до» — изменения не видны")
            elif closest >= 40:
                score -= 0.5
                notes.append("Фото «до» и «после» сильно различаются — проверьте, что это тот же узел")
            else:
                notes.append(f"Фото «до/после» сопоставимы (расстояние dHash {closest}/64)")
    else:
        notes.append("Нет фото «до» — сравнение не выполнялось")

    return PhotoCheck(max(1.0, round(score, 1)), issues, notes)
