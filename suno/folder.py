"""The download folder: the audio files and danh-sach.csv, the list of songs already downloaded into it.

A song (in a format) listed in danh-sach.csv is not downloaded again, even if its file was deleted or renamed; delete
its line to download it again. Files are named after the song title as Suno shows it; two songs with the same title
(Suno makes songs in pairs) get "Title (2).wav". Titles come from Suno and are not trusted: anything Windows or Linux
would read as a path, a device name, a command option or a formula in Excel is taken out.
"""
import csv
import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path

LIST_NAME = "danh-sach.csv"
COLUMNS = ("ten_bai", "file", "dinh_dang", "link", "luc", "id")
WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {f"{p}{n}" for p in ("com", "lpt") for n in range(1, 10)}
NAME_MAX = 80


class FolderError(Exception):
    pass


def safe_cell(value):
    """Excel must not run a cell as a formula (song titles are free text)."""
    value = str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def safe_filename(title, fallback):
    """A song title -> a file name stem that is safe on Windows and Linux."""
    name = unicodedata.normalize("NFC", title or "")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip().lstrip(". =+-@")  # no hidden file, option or Excel formula
    name = name[:NAME_MAX].rstrip(". ")
    if not name:
        name = fallback
    if name.split(".")[0].strip().lower() in WINDOWS_RESERVED:
        name = "_" + name
    return name


def audio_ok(path, fmt):
    """Is the file a WAV / MP3 (not an error page saved under that name)?"""
    path = Path(path)
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return False
    if size < 1000:
        return False
    if fmt == "wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)


class Folder:
    def __init__(self, path):
        self.root = Path(path).resolve()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise FolderError(f"Không tạo được thư mục {self.root}: {e}")
        self.list_path = self.root / LIST_NAME
        self.rows = {}
        if self.list_path.exists():
            raw = self.list_path.read_bytes()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise FolderError(f"{self.list_path} không phải UTF-8. Trong Excel: File → Save As → 'CSV UTF-8'")
            first = text.splitlines()[0] if text.strip() else ""
            delimiter = max((",", ";", "\t"), key=first.count)
            for rec in csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter):
                sid, fmt = (rec.get("id") or "").strip().lower(), (rec.get("dinh_dang") or "").strip().lower()
                if sid and fmt:
                    self.rows[(sid, fmt)] = rec
        self.save()  # fails now, before any download, if Excel holds the file open

    def done(self, song_id, fmt):
        return (song_id, fmt) in self.rows

    def target(self, title, song_id, fmt):
        """A new file path for the song: its title, made unique in this folder."""
        stem = safe_filename(title, f"suno-{song_id[:8]}")
        taken = {p.name.lower() for p in self.root.iterdir()}
        taken |= {(r.get("file") or "").lower() for r in self.rows.values()}
        name, n = f"{stem}.{fmt}", 2
        while name.lower() in taken:
            name, n = f"{stem} ({n}).{fmt}", n + 1
        return self.root / name

    def part_path(self, song_id, fmt):
        return self.root / f".{song_id}.{fmt}.part"

    def add(self, song, path, fmt, title):
        self.rows[(song.id, fmt)] = {"ten_bai": title, "file": Path(path).name, "dinh_dang": fmt, "link": song.link,
                                     "luc": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "id": song.id}
        self.save()

    def save(self):
        tmp = self.list_path.with_name(self.list_path.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLUMNS)
                for rec in self.rows.values():
                    w.writerow([safe_cell(rec.get(c, "")) if c != "id" else rec.get(c, "") for c in COLUMNS])
            tmp.replace(self.list_path)
        except PermissionError:
            raise FolderError(f"Không ghi được {self.list_path}: đóng file này trong Excel rồi chạy lại")
