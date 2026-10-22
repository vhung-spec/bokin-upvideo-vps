"""Bokin Up Video: uploads videos to the company's YouTube channels and schedules them, from a VPS or any computer.

No YouTube API: a real Chrome, signed in once by hand for each channel, does what a person does in YouTube Studio
(studio.py). The schedule is a CSV file (jobs.py). Commands:

  login <kenh>            a visible Chrome: sign in to Google, open the channel in Studio, close the window
  check [<kenh>]          is each channel still signed in
  channels                the channels on this computer
  remove <kenh>           forget a channel and its Chrome profile
  upload <kenh> <video> --title T --at "2026-10-25 20:00" [--description D | --description-file F]
  run <lich.csv>          every row of a schedule file, one after another; results in <lich>.ketqua.csv
  selftest                checks that need no browser

Data (channels.json, settings.json, a Chrome profile per channel, logs) is in ./data next to the program, or in
--data / BOKIN_UPVIDEO_DATA. The profiles hold the channels' Google sign-ins: never copy or share them.
"""
import argparse
import contextlib
import json
import logging
import logging.handlers
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs  # noqa: E402
import studio  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
log = logging.getLogger("upvideo")


class UserError(Exception):
    """A problem the person can fix; printed without a traceback."""


# ---- data folder ----

class Data:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.profiles = self.root / "profiles"
        self.logs = self.root / "logs"
        for d in (self.root, self.profiles, self.logs):
            d.mkdir(parents=True, exist_ok=True)

    def _read(self, name):
        p = self.root / name
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            raise UserError(f"{p} hỏng (không phải JSON)")

    def _write(self, name, value):
        p = self.root / name
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)

    def channels(self):
        return self._read("channels.json")

    def save_channels(self, value):
        self._write("channels.json", value)

    def settings(self):
        return self._read("settings.json")

    def profile(self, name):
        return self.profiles / name


@contextlib.contextmanager
def single_run(data):
    """One run at a time per data folder: two Chromes cannot share a profile."""
    f = open(data.root / "upvideo.lock", "a+")
    f.seek(0)
    try:
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise UserError("Tool đang chạy ở cửa sổ khác. Chờ nó xong rồi chạy lại.")
        else:
            import fcntl
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise UserError("Tool đang chạy ở cửa sổ khác. Chờ nó xong rồi chạy lại.")
        yield
    finally:
        f.close()


def setup_logging(data):
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    fh = logging.handlers.RotatingFileHandler(data.logs / "upvideo.log", maxBytes=2_000_000, backupCount=5,
                                              encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    log.addHandler(fh)
    log.addHandler(ch)


def timezone_name(args, data):
    name = args.timezone or data.settings().get("timezone") or DEFAULT_TIMEZONE
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
    except Exception:
        raise UserError(f"Múi giờ '{name}' không đúng (ví dụ đúng: Asia/Ho_Chi_Minh, America/New_York)")
    return name


def now_in(tz):
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(tz)).replace(tzinfo=None)


def check_channel_name(name):
    if not jobs.CHANNEL_NAME_RE.fullmatch(name or ""):
        raise UserError(f"Tên kênh '{name}' không hợp lệ: chỉ chữ không dấu, số, - và _ (tối đa 40), ví dụ anime1")
    return name


# ---- the browser ----

@contextlib.contextmanager
def browser(args, data, name, headless, tz):
    """A Chrome with the channel's own profile, so its Google sign-in stays between runs."""
    if not headless and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        raise UserError("Máy này không có màn hình. Chạy bằng ./upvideo.sh (tự tạo màn hình ảo) hoặc thêm --headless; "
                        "riêng 'login' phải vào VPS bằng Remote Desktop (xem README)")
    from patchright.sync_api import sync_playwright
    kw = dict(user_data_dir=str(data.profile(name)), headless=headless, no_viewport=True, locale="en-US",
              timezone_id=tz, args=["--lang=en-US", "--window-size=1366,900", "--password-store=basic"])
    chrome = args.chrome or os.environ.get("BOKIN_UPVIDEO_CHROME")
    if chrome:
        kw["executable_path"] = chrome
    else:
        kw["channel"] = "chrome"
    with sync_playwright() as pw:
        try:
            context = pw.chromium.launch_persistent_context(**kw)
        except Exception as e:
            text = str(e)
            if "ProcessSingleton" in text or "already in use" in text or "SingletonLock" in text:
                raise UserError(f"Hồ sơ Chrome của kênh {name} đang mở ở cửa sổ khác. Đóng cửa sổ đó rồi chạy lại.")
            if "chrome" in text.lower() and ("not found" in text.lower() or "doesn't exist" in text.lower()
                                             or "executable" in text.lower()):
                raise UserError("Chưa cài Google Chrome. Chạy lại file cài đặt (cai-dat-windows.bat / cai-dat-linux.sh)")
            raise
        try:
            yield context
        finally:
            with contextlib.suppress(Exception):
                context.close()


def first_page(context):
    return context.pages[0] if context.pages else context.new_page()


# ---- commands ----

def cmd_login(args, data):
    name = check_channel_name(args.kenh)
    tz = timezone_name(args, data)
    log.info("Mở Chrome cho kênh %s. Trong cửa sổ Chrome: đăng nhập Google của kênh, mở đúng kênh trong YouTube "
             "Studio, rồi ĐÓNG cửa sổ Chrome.", name)
    settle = float(os.environ.get("BOKIN_UPVIDEO_LOGIN_SETTLE") or 0) or None
    with single_run(data), browser(args, data, name, False, tz) as context:
        channel_id = studio.wait_for_login(context, log, settle_seconds=settle)
    if not channel_id:
        raise UserError("Không thấy kênh nào được mở trong YouTube Studio. Chạy lại lệnh login.")
    channels = data.channels()
    for other, rec in channels.items():
        if other != name and rec.get("channel_id") == channel_id:
            log.warning("Kênh %s cũng là %s: hai tên cùng một kênh YouTube", other, channel_id)
    channels[name] = {"channel_id": channel_id, "added": datetime.now().strftime("%Y-%m-%d %H:%M")}
    data.save_channels(channels)
    log.info("Đã lưu kênh %s (%s). Từ giờ tool tự đăng nhập bằng hồ sơ Chrome này.", name, channel_id)
    return 0


def cmd_check(args, data):
    tz = timezone_name(args, data)
    channels = data.channels()
    names = [check_channel_name(args.kenh)] if args.kenh else sorted(channels)
    if not names:
        raise UserError("Chưa có kênh nào. Chạy: upvideo login <tên kênh>")
    bad = 0
    with single_run(data):
        for name in names:
            if name not in channels:
                log.error("%s: chưa đăng nhập trên máy này", name)
                bad += 1
                continue
            want = channels[name]["channel_id"]
            with browser(args, data, name, args.headless, tz) as context:
                got = studio.signed_in_channel(first_page(context))
            if got is None:
                log.error("%s: đã bị đăng xuất. Chạy lại: upvideo login %s", name, name)
                bad += 1
            else:
                log.info("%s: đang đăng nhập (%s)", name, want)
    return 1 if bad else 0


def cmd_channels(args, data):
    channels = data.channels()
    if not channels:
        print("Chưa có kênh nào. Chạy: upvideo login <tên kênh>")
    for name in sorted(channels):
        print(f"{name}\t{channels[name]['channel_id']}\tthêm lúc {channels[name].get('added', '?')}")
    return 0


def cmd_remove(args, data):
    name = check_channel_name(args.kenh)
    channels = data.channels()
    with single_run(data):
        if name not in channels and not data.profile(name).exists():
            raise UserError(f"Không có kênh {name}")
        channels.pop(name, None)
        data.save_channels(channels)
        for _ in range(20):  # Windows keeps a just-closed Chrome's files locked for a moment
            shutil.rmtree(data.profile(name), ignore_errors=True)
            if not data.profile(name).exists():
                break
            time.sleep(0.5)
    log.info("Đã xoá kênh %s và hồ sơ Chrome của nó trên máy này", name)
    return 0


def upload_one(args, data, job, tz, channel_id, results=None):
    """One video: Chrome with the channel's profile, Studio, schedule. Returns the link; raises StudioError."""
    def before_publish(link):
        if results:
            results.set(job, jobs.PUBLISHING, link, "đang bấm Schedule")

    with browser(args, data, job.channel, args.headless, tz) as context:
        page = first_page(context)
        try:
            return studio.upload_scheduled(page, channel_id, job.video, job.title, job.description, job.publish_at,
                                           log, stall_minutes=args.stall_minutes, before_publish=before_publish,
                                           now=lambda: now_in(tz))
        except Exception:
            stem = data.logs / f"loi-{datetime.now():%Y%m%d-%H%M%S}-{job.channel}"
            studio.save_failure(page, str(stem))
            log.error("Ảnh màn hình lúc lỗi: %s.png", stem)
            raise


def describe(e):
    if isinstance(e, (studio.StudioError, UserError)):
        return str(e)
    return f"lỗi không lường trước: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"


def cmd_upload(args, data):
    name = check_channel_name(args.kenh)
    tz = timezone_name(args, data)
    description = args.description or ""
    if args.description_file:
        try:
            description = Path(args.description_file).read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeDecodeError) as e:
            raise UserError(f"Không đọc được file mô tả: {e}")
    job = jobs.Job(0, name, Path(args.video).resolve(), args.title, description.replace("\r\n", "\n"),
                   jobs.parse_publish_time(args.at))
    channels = data.channels()
    if jobs.validate(job, channels, now_in(tz)):
        raise UserError("; ".join(job.errors))
    with single_run(data):
        try:
            link = upload_one(args, data, job, tz, channels[name]["channel_id"])
        except Exception as e:
            log.debug("upload failed", exc_info=True)
            raise UserError(describe(e))
    log.info("Xong: %s sẽ đăng lúc %s (%s) %s", job.video.name, job.publish_at.strftime("%Y-%m-%d %H:%M"), tz, link)
    return 0


def cmd_run(args, data):
    tz = timezone_name(args, data)
    try:
        all_jobs = jobs.read_schedule(args.lich)
    except (OSError, jobs.ScheduleFileError) as e:
        raise UserError(str(e))
    channels = data.channels()
    results = jobs.Results(jobs.results_path(args.lich))
    log.info("Lịch %s: %d video, múi giờ %s. Kết quả ghi vào %s", args.lich, len(all_jobs), tz, results.path)
    done = failed = skipped = 0
    signed_out = set()
    with single_run(data):
        for job in all_jobs:
            status = results.status(job)
            label = f"Dòng {job.row} ({job.channel}, {job.video.name})"
            if status == jobs.DONE:
                log.info("%s: đã đặt lịch từ trước, bỏ qua", label)
                skipped += 1
                continue
            if status == jobs.PUBLISHING:
                log.warning("%s: lần trước bị ngắt lúc đang bấm Schedule. Xem trong Studio; muốn đăng lại thì xoá "
                            "dòng này trong %s", label, results.path.name)
                skipped += 1
                continue
            jobs.validate(job, channels, now_in(tz))
            if job.channel in signed_out:
                job.errors.append(f"kênh {job.channel} đã bị đăng xuất (upvideo login {job.channel})")
            if job.errors:
                log.error("%s: %s", label, "; ".join(job.errors))
                results.set(job, jobs.FAILED, note="; ".join(job.errors))
                failed += 1
                continue
            log.info("%s: bắt đầu, đăng lúc %s", label, job.publish_at.strftime("%Y-%m-%d %H:%M"))
            try:
                link = upload_one(args, data, job, tz, channels[job.channel]["channel_id"], results)
            except Exception as e:
                if isinstance(e, studio.StudioError) and e.code == "not_signed_in":
                    signed_out.add(job.channel)
                log.debug("upload failed", exc_info=True)
                log.error("%s: %s", label, describe(e))
                results.set(job, jobs.FAILED, note=describe(e))
                failed += 1
                continue
            results.set(job, jobs.DONE, link)
            log.info("%s: xong %s", label, link)
            done += 1
    log.info("Tổng: %d xong, %d lỗi, %d bỏ qua. Chi tiết: %s", done, failed, skipped, results.path)
    return 1 if failed else 0


# ---- self-test (no browser) ----

def cmd_selftest(args, data):
    errors = []

    def check(cond, what):
        if not cond:
            errors.append(what)

    from datetime import date
    check(studio.parse_studio_date("Oct 25, 2026") == (date(2026, 10, 25), "mdy"), "date US")
    check(studio.parse_studio_date("25 Oct 2026") == (date(2026, 10, 25), "dmy"), "date UK")
    check(studio.parse_studio_date("5 Sept 2026") == (date(2026, 9, 5), "dmy"), "date UK Sept")
    check(studio.parse_studio_date("25 thg 10, 2026") is None, "date Vietnamese refused")
    check(studio.parse_studio_date("Date Oct 25, 2026") == (date(2026, 10, 25), "mdy"), "date with a label")
    check(studio.format_studio_date(date(2026, 3, 7), "mdy") == "Mar 7, 2026", "format US")
    check(studio.format_studio_date(date(2026, 3, 7), "dmy") == "7 Mar 2026", "format UK")
    check(studio.parse_studio_time("8:05 PM") == ((20, 5), "12h"), "time 12h nnbsp")
    check(studio.parse_studio_time("12:00 AM") == ((0, 0), "12h"), "time midnight")
    check(studio.parse_studio_time("12:30 PM") == ((12, 30), "12h"), "time noon")
    check(studio.parse_studio_time("20:05") == ((20, 5), "24h"), "time 24h")
    check(studio.parse_studio_time("25:00") is None, "time bad")
    check(studio.format_studio_time(0, 15, "12h") == "12:15 AM", "format 12h midnight")
    check(studio.format_studio_time(13, 0, "12h") == "1:00 PM", "format 12h pm")
    check(studio.format_studio_time(7, 5, "24h") == "07:05", "format 24h")
    check(studio.upload_state("Uploading 45% ... 3 minutes left") == ("uploading", 45), "progress uploading")
    check(studio.upload_state("Upload complete ... Processing will begin shortly")[0] == "done", "progress done")
    check(studio.upload_state("Checks complete. No issues found.")[0] == "done", "progress checks")
    check(studio.upload_state("Upload failed")[0] == "failed", "progress failed")
    check(studio.upload_state("")[0] == "uploading", "progress empty")
    check(jobs.parse_publish_time("2026-10-25 20:00") == datetime(2026, 10, 25, 20, 0), "gio_dang iso")
    check(jobs.parse_publish_time("25/10/2026 20:00:00") == datetime(2026, 10, 25, 20, 0), "gio_dang vn")
    check(jobs.parse_publish_time("10/25/2026 20:00") is None, "gio_dang month-first refused")
    check(jobs.parse_publish_time("2026-10-25") is None, "gio_dang no time")
    check(jobs.header_key(" Tiêu đề ") == "tieu_de" and jobs.header_key("Giờ đăng") == "gio_dang", "headers")
    check(jobs.safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and jobs.safe_cell("ok") == "ok", "csv formula")
    check(jobs.CHANNEL_NAME_RE.fullmatch("anime-1") and not jobs.CHANNEL_NAME_RE.fullmatch("-x")
          and not jobs.CHANNEL_NAME_RE.fullmatch("kênh"), "channel names")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a.mp4").write_bytes(b"x")
        (tmp / "mo ta.txt").write_text("Dòng 1\nDòng 2 #nhac", encoding="utf-8")
        (tmp / "lich.csv").write_bytes(
            "Kênh;Video;Tiêu đề;Mô tả;Giờ đăng\r\nkenh1;a.mp4;Nhạc thư giãn 10 giờ;@mo ta.txt;25/10/2099 20:00\r\n"
            "kenh1;thieu.mp4;Bad <title>;;2001-01-01 00:00\r\n;;;;\r\n".encode("utf-8-sig"))
        rows = jobs.read_schedule(tmp / "lich.csv")
        check(len(rows) == 2, "schedule rows")
        if len(rows) == 2:
            a, b = rows
            check(a.title == "Nhạc thư giãn 10 giờ" and a.description == "Dòng 1\nDòng 2 #nhac", "schedule row 1")
            check(a.video == (tmp / "a.mp4").resolve() and a.publish_at == datetime(2099, 10, 25, 20, 0), "row 1 video")
            check(not jobs.validate(a, {"kenh1": {}}, datetime(2026, 1, 1)), f"row 1 valid {a.errors}")
            errs = " | ".join(jobs.validate(b, {"kenh1": {}}, datetime(2026, 1, 1)))
            check("không thấy file" in errs and "< hoặc >" in errs and "đã qua" in errs, f"row 2 errors {errs}")
            res = jobs.Results(jobs.results_path(tmp / "lich.csv"))
            res.set(a, jobs.DONE, "https://youtu.be/abcdefghijk")
            b.title = "=cmd"
            res.set(b, jobs.FAILED, note="-oops")
            again = jobs.Results(res.path)
            check(again.status(a) == jobs.DONE and again.status(b) == jobs.FAILED, "results reread")
            raw = res.path.read_text(encoding="utf-8-sig")
            check("'=cmd" in raw and "'-oops" in raw, "results formula guard")
        (tmp / "bad.csv").write_bytes("kenh,video\r\nk,v\r\n".encode("utf-8"))
        try:
            jobs.read_schedule(tmp / "bad.csv")
            check(False, "missing columns refused")
        except jobs.ScheduleFileError:
            pass
        (tmp / "ansi.csv").write_bytes("kenh,video,tieu_de,gio_dang\r\nk,v,Nh\xe1c,x\r\n".encode("latin-1"))
        try:
            jobs.read_schedule(tmp / "ansi.csv")
            check(False, "non-UTF-8 refused")
        except jobs.ScheduleFileError:
            pass
    import importlib.util
    if importlib.util.find_spec("patchright") is None:
        errors.append("patchright is not installed")
    for e in errors:
        print("FAIL", e)
    print("selftest", "OK" if not errors else f"{len(errors)} FAILED")
    return 1 if errors else 0


def main(argv=None):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="upvideo", description="Bokin Up Video: tải video lên YouTube và hẹn giờ đăng")
    p.add_argument("--data", help="thư mục dữ liệu (mặc định ./data)")
    p.add_argument("--headless", action="store_true", help="chạy Chrome không hiện cửa sổ")
    p.add_argument("--chrome", help="đường dẫn chrome.exe nếu không ở chỗ mặc định")
    p.add_argument("--timezone", help=f"múi giờ của giờ đăng (mặc định {DEFAULT_TIMEZONE})")
    p.add_argument("--stall-minutes", type=float, default=30, help="báo lỗi nếu tải lên đứng yên chừng này phút")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("login", help="đăng nhập một kênh (mở Chrome)")
    s.add_argument("kenh")
    s = sub.add_parser("check", help="kiểm tra các kênh còn đăng nhập")
    s.add_argument("kenh", nargs="?")
    sub.add_parser("channels", help="các kênh trên máy này")
    s = sub.add_parser("remove", help="xoá một kênh khỏi máy này")
    s.add_argument("kenh")
    s = sub.add_parser("upload", help="tải một video lên và hẹn giờ")
    s.add_argument("kenh")
    s.add_argument("video")
    s.add_argument("--title", required=True)
    s.add_argument("--at", required=True, help='giờ đăng, ví dụ "2026-10-25 20:00"')
    s.add_argument("--description")
    s.add_argument("--description-file")
    s = sub.add_parser("run", help="tải lên mọi video trong file lịch CSV")
    s.add_argument("lich")
    sub.add_parser("selftest", help="tự kiểm tra")
    args = p.parse_args(argv)

    data = Data(args.data or os.environ.get("BOKIN_UPVIDEO_DATA") or ROOT / "data")
    setup_logging(data)
    commands = {"login": cmd_login, "check": cmd_check, "channels": cmd_channels, "remove": cmd_remove,
                "upload": cmd_upload, "run": cmd_run, "selftest": cmd_selftest}
    try:
        return commands[args.cmd](args, data)
    except UserError as e:
        log.error("%s", e)
        return 2
    except KeyboardInterrupt:
        log.error("Đã dừng (Ctrl+C)")
        return 130


if __name__ == "__main__":
    sys.exit(main())
