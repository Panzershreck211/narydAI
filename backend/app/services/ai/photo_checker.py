"""Базовая проверка фото: метаданные EXIF, качество снимка и сравнение «до/после».

Без тяжёлых ML-зависимостей: перцептивный хэш (dHash), резкость по дисперсии
градиента и средняя яркость считаются средствами Pillow.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import ExifTags, Image, ImageFilter, ImageStat

HASH_SIZE = 8  # 64-битный dHash

_TAGS = {v: k for k, v in ExifTags.TAGS.items()}


def analyze_photo(path: Path) -> dict:
    """Метаданные одного фото — сохраняются в OrderPhoto.meta при загрузке."""
    with Image.open(path) as img:
        exif = img.getexif()
        ifd = exif.get_ifd(ExifTags.IFD.Exif) if exif else {}
        taken_raw = ifd.get(_TAGS["DateTimeOriginal"]) or exif.get(_TAGS["DateTime"])
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo) if exif else {}

        gray = img.convert("L")
        gray.thumbnail((512, 512))
        sharpness = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]
        brightness = ImageStat.Stat(gray).mean[0]

        return {
            "width": img.width,
            "height": img.height,
            "has_exif": bool(exif),
            "camera": " ".join(filter(None, [exif.get(_TAGS["Make"]), exif.get(_TAGS["Model"])])) or None,
            "taken_at": _parse_exif_dt(taken_raw),
            "has_gps": bool(gps),
            "sharpness": round(sharpness, 1),
            "brightness": round(brightness, 1),
            "dhash": _dhash(img),
        }


def _parse_exif_dt(raw) -> str | None:
    if not raw:
        return None
    try:
        # В EXIF нет часового пояса — считаем UTC, для сравнения в пределах смены достаточно
        return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


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
