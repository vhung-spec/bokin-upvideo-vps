"""The schedule file (CSV, one video per row) and its results file.

Columns (headers in Vietnamese, accents and case optional): kenh, video, tieu_de, mo_ta, gio_dang.
- video: a path, absolute or relative to the CSV file.
- mo_ta: the description text, or @file.txt to read it from a UTF-8 text file.
- gio_dang: "2026-10-25 20:00" or "25/10/2026 20:00" (day first), in the program's time zone.
Excel's "CSV UTF-8" with comma or semicolon both work. Results go to <name>.ketqua.csv beside it; a row already
"xong" (scheduled) or "dang_tai" (cut off while publishing: check Studio by hand) is not uploaded again.
"""
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

COLUMNS = ("kenh", "video", "tieu_de", "mo_ta", "gio_dang")
REQUIRED = ("kenh", "video", "tieu_de", "gio_dang")
RESULT_COLUMNS = ("dong", "kenh", "video", "tieu_de", "gio_dang", "trang_thai", "link", "ghi_chu", "luc")
DONE, FAILED, PUBLISHING = "xong", "loi", "dang_tai"
CHANNEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
TITLE_MAX, DESCRIPTION_MAX = 100, 5000


class ScheduleFileError(Exception):
    pass


@dataclass
class Job:
    row: int
    channel: str
    video: Path
    title: str
    description: str
    publish_at: datetime | None
    errors: list = field(default_factory=list)

    @property
    def key(self):
        when = self.publish_at.strftime("%Y-%m-%d %H:%M") if self.publish_at else ""
        return f"{self.channel}|{str(self.video).lower()}|{when}"


def header_key(text):
    """'Tiêu đề' -> 'tieu_de'."""
    text = unicodedata.normalize("NFD", (text or "").strip().lower().replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", "_", text)


def parse_publish_time(text):
    """'2026-10-25 20:00' or '25/10/2026 20:00' (seconds allowed, ignored) -> datetime, or None."""
    text = (text or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4}) +(\d{1,2}):(\d{2})(?::\d{2})?", text)
        if not m:
            return None
        d, mo, y, h, mi = (int(x) for x in m.groups())
    try:
        return datetime(y, mo, d, h, mi)
    except ValueError:
        return None


def check_text(value, what, limit):
    errors = []
    if len(value) > limit:
        errors.append(f"{what} dài {len(value)} ký tự, tối đa {limit}")
    if "<" in value or ">" in value:
        errors.append(f"{what} có ký tự < hoặc > (YouTube không cho phép)")
    return errors


def validate(job, channels, now):
    """Fills job.errors: unknown channel, missing file, empty or bad title, time not in the future."""
    if job.channel not in channels:
        job.errors.append(f"kênh '{job.channel}' chưa đăng nhập trên máy này (upvideo login {job.channel})")
    if not job.video.is_file():
        job.errors.append(f"không thấy file video {job.video}")
    if not job.title.strip():
        job.errors.append("thiếu tiêu đề")
    job.errors += check_text(job.title, "tiêu đề", TITLE_MAX)
    job.errors += check_text(job.description, "mô tả", DESCRIPTION_MAX)
    if job.publish_at is None:
        job.errors.append("giờ đăng sai dạng (viết 2026-10-25 20:00 hoặc 25/10/2026 20:00)")
    elif (job.publish_at - now).total_seconds() < 15 * 60:
        job.errors.append(f"giờ đăng {job.publish_at:%Y-%m-%d %H:%M} đã qua hoặc còn dưới 15 phút")
    return job.errors


def _decode(raw, path):
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ScheduleFileError(f"{path} không phải UTF-8. Trong Excel: File → Save As → chọn 'CSV UTF-8'")


def read_schedule(path):
    """The rows of a schedule file as Jobs (not yet validated against channels and time)."""
    path = Path(path).resolve()
    text = _decode(path.read_bytes(), path)
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = max((",", ";", "\t"), key=first.count)
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not rows:
        raise ScheduleFileError(f"{path} trống")
    headers = [header_key(h) for h in rows[0]]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise ScheduleFileError(f"{path} thiếu cột: {', '.join(missing)} (dòng đầu phải là: {', '.join(COLUMNS)})")
    jobs = []
    for n, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        rec = {h: (cells[i].strip() if i < len(cells) else "") for i, h in enumerate(headers) if h in COLUMNS}
        video = Path(rec.get("video", ""))
        if rec.get("video") and not video.is_absolute():
            video = path.parent / video
        job = Job(n, rec.get("kenh", ""), video.resolve() if rec.get("video") else video, rec.get("tieu_de", ""),
                  "", parse_publish_time(rec.get("gio_dang", "")))
        desc = rec.get("mo_ta", "")
        if desc.startswith("@"):
            desc_path = Path(desc[1:].strip())
            if not desc_path.is_absolute():
                desc_path = path.parent / desc_path
            try:
                desc = _decode(desc_path.read_bytes(), desc_path).strip()
            except OSError:
                job.errors.append(f"không đọc được file mô tả {desc_path}")
                desc = ""
            except ScheduleFileError as e:
                job.errors.append(str(e))
                desc = ""
        job.description = desc.replace("\r\n", "\n")
        jobs.append(job)
    return jobs


def results_path(schedule_path):
    p = Path(schedule_path).resolve()
    return p.with_name(p.stem + ".ketqua.csv")


def safe_cell(value):
    """Excel must not run a cell as a formula (titles and Studio messages are free text)."""
    value = str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


class Results:
    """<name>.ketqua.csv: one line per video, rewritten after every change so a crash leaves it whole."""

    def __init__(self, path):
        self.path = Path(path)
        self.rows = {}
        if self.path.exists():
            text = _decode(self.path.read_bytes(), self.path)
            for rec in csv.DictReader(io.StringIO(text, newline="")):
                key = rec.get("_key") or ""
                if key:
                    self.rows[key] = rec

    def status(self, job):
        return (self.rows.get(job.key) or {}).get("trang_thai", "")

    def set(self, job, status, link="", note=""):
        self.rows[job.key] = {
            "dong": job.row, "kenh": job.channel, "video": str(job.video), "tieu_de": job.title,
            "gio_dang": job.publish_at.strftime("%Y-%m-%d %H:%M") if job.publish_at else "",
            "trang_thai": status, "link": link, "ghi_chu": note, "luc": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "_key": job.key,
        }
        self.save()

    def save(self):
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(RESULT_COLUMNS + ("_key",))
            for rec in self.rows.values():
                w.writerow([safe_cell(rec.get(c, "")) for c in RESULT_COLUMNS] + [rec.get("_key", "")])
        tmp.replace(self.path)
