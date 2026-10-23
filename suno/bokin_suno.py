"""Bokin Suno: downloads the songs of a Suno workspace (the company's own songs) to a folder, from any computer.

No Suno API: a real Chrome, signed in once by hand for each Suno account, does what a person does on suno.com
(web.py): open the workspace, then for each song More options → Download → WAV Audio. Downloads count against the
plan's download allowance exactly as by hand; the run stops when Suno says it is used up. Commands:

  login <tai-khoan>            a visible Chrome: sign in to Suno, close the window
  check [<tai-khoan>]          is each account still signed in
  accounts                     the accounts on this computer
  remove <tai-khoan>           forget an account and its Chrome profile
  list <tai-khoan> <link>      the songs at a workspace (or playlist) link, without downloading
  download <tai-khoan> <link> [--out FOLDER] [--format wav|mp3] [--limit N]
                               every song at the link not yet in FOLDER/danh-sach.csv
  selftest                     checks that need no browser

Data (accounts.json, a Chrome profile per account, logs) is in ./data/suno next to the program, or in --data /
BOKIN_SUNO_DATA. The profiles hold the accounts' Suno sign-ins: never copy or share them.
"""
import argparse
import contextlib
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import folder  # noqa: E402
import web  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ACCOUNT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
STUCK_IN_A_ROW = 3  # songs failing one after another like this: Suno's page has most likely changed
log = logging.getLogger("suno")


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

    def accounts(self):
        p = self.root / "accounts.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            raise UserError(f"{p} hỏng (không phải JSON)")

    def save_accounts(self, value):
        p = self.root / "accounts.json"
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)

    def profile(self, name):
        return self.profiles / name


@contextlib.contextmanager
def single_run(data):
    """One run at a time per data folder: two Chromes cannot share a profile."""
    f = open(data.root / "suno.lock", "a+")
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
    fh = logging.handlers.RotatingFileHandler(data.logs / "suno.log", maxBytes=2_000_000, backupCount=5,
                                              encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    log.addHandler(fh)
    log.addHandler(ch)


def check_account_name(name):
    if not ACCOUNT_NAME_RE.fullmatch(name or ""):
        raise UserError(f"Tên tài khoản '{name}' không hợp lệ: chỉ chữ không dấu, số, - và _ (tối đa 40), ví dụ suno1")
    return name


def known_account(data, name):
    accounts = data.accounts()
    if check_account_name(name) not in accounts:
        raise UserError(f"Tài khoản {name} chưa đăng nhập trên máy này. Chạy: suno login {name}")
    return accounts[name]


# ---- the browser ----

@contextlib.contextmanager
def browser(args, data, name, headless):
    """A Chrome with the account's own profile, so its Suno sign-in stays between runs."""
    if not headless and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        raise UserError("Máy này không có màn hình. Chạy bằng ./suno.sh (tự tạo màn hình ảo) hoặc thêm --headless; "
                        "riêng 'login' phải vào VPS bằng Remote Desktop (xem SUNO.md)")
    from patchright.sync_api import sync_playwright
    kw = dict(user_data_dir=str(data.profile(name)), headless=headless, no_viewport=True, locale="en-US",
              accept_downloads=True, args=["--lang=en-US", "--window-size=1366,900", "--password-store=basic"])
    chrome = args.chrome or os.environ.get("BOKIN_SUNO_CHROME")
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
                raise UserError(f"Hồ sơ Chrome của tài khoản {name} đang mở ở cửa sổ khác. Đóng cửa sổ đó rồi chạy lại.")
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


def describe(e):
    if isinstance(e, (web.SunoError, UserError, folder.FolderError)):
        return str(e)
    return f"lỗi không lường trước: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"


def keep_failure(data, page, name):
    stem = data.logs / f"loi-{datetime.now():%Y%m%d-%H%M%S}-{name}"
    web.save_failure(page, str(stem))
    log.error("Ảnh màn hình lúc lỗi: %s.png (che tên tài khoản trước khi gửi cho ai)", stem)


# ---- commands ----

def cmd_login(args, data):
    name = check_account_name(args.tai_khoan)
    log.info("Mở Chrome cho tài khoản %s. Trong cửa sổ Chrome: đăng nhập Suno (Sign in), rồi ĐÓNG cửa sổ Chrome.", name)
    settle = float(os.environ.get("BOKIN_SUNO_LOGIN_SETTLE") or 0) or None
    with single_run(data), browser(args, data, name, False) as context:
        signed_in, user_id = web.wait_for_login(context, log, settle_seconds=settle)
    if not signed_in:
        raise UserError("Chưa thấy đăng nhập Suno. Chạy lại lệnh login, đăng nhập xong rồi mới đóng Chrome.")
    accounts = data.accounts()
    for other, rec in accounts.items():
        if other != name and user_id and rec.get("user_id") == user_id:
            log.warning("Tài khoản %s cũng là tài khoản Suno này: hai tên cùng một tài khoản", other)
    accounts[name] = {"user_id": user_id or "", "added": datetime.now().strftime("%Y-%m-%d %H:%M")}
    data.save_accounts(accounts)
    log.info("Đã lưu tài khoản %s. Từ giờ tool tự đăng nhập Suno bằng hồ sơ Chrome này.", name)
    return 0


def cmd_check(args, data):
    accounts = data.accounts()
    names = [check_account_name(args.tai_khoan)] if args.tai_khoan else sorted(accounts)
    if not names:
        raise UserError("Chưa có tài khoản nào. Chạy: suno login <tên>")
    bad = 0
    with single_run(data):
        for name in names:
            if name not in accounts:
                log.error("%s: chưa đăng nhập trên máy này", name)
                bad += 1
                continue
            with browser(args, data, name, args.headless) as context:
                state, user_id = web.signed_in_user(first_page(context))
            want = accounts[name].get("user_id")
            if state != "in":
                log.error("%s: đã bị đăng xuất. Chạy lại: suno login %s", name, name)
                bad += 1
            elif want and user_id and user_id != want:
                log.error("%s: Chrome đang đăng nhập tài khoản Suno khác. Chạy lại: suno login %s", name, name)
                bad += 1
            else:
                log.info("%s: đang đăng nhập", name)
    return 1 if bad else 0


def cmd_accounts(args, data):
    accounts = data.accounts()
    if not accounts:
        print("Chưa có tài khoản nào. Chạy: suno login <tên>")
    for name in sorted(accounts):
        print(f"{name}\tthêm lúc {accounts[name].get('added', '?')}")
    return 0


def cmd_remove(args, data):
    name = check_account_name(args.tai_khoan)
    accounts = data.accounts()
    with single_run(data):
        if name not in accounts and not data.profile(name).exists():
            raise UserError(f"Không có tài khoản {name}")
        accounts.pop(name, None)
        data.save_accounts(accounts)
        for _ in range(20):  # Windows keeps a just-closed Chrome's files locked for a moment
            shutil.rmtree(data.profile(name), ignore_errors=True)
            if not data.profile(name).exists():
                break
            time.sleep(0.5)
    log.info("Đã xoá tài khoản %s và hồ sơ Chrome của nó trên máy này", name)
    return 0


def read_link(text):
    try:
        return web.check_link(text)
    except ValueError as e:
        raise UserError(str(e))


def songs_at(args, data, context, name, account, url):
    page = first_page(context)
    try:
        web.ensure_account(page, account.get("user_id"))
        songs = web.list_songs(page, url, log)
    except Exception as e:
        log.debug("listing failed", exc_info=True)
        if not isinstance(e, web.SunoError) or e.code == "no_songs":
            keep_failure(data, page, name)
        raise UserError(describe(e))
    return page, songs


def cmd_list(args, data):
    name = args.tai_khoan
    account = known_account(data, name)
    url = read_link(args.link)
    with single_run(data), browser(args, data, name, args.headless) as context:
        _, songs = songs_at(args, data, context, name, account, url)
    for n, s in enumerate(songs, 1):
        print(f"{n}\t{s.title or '(không tên)'}\t{s.link}")
    log.info("Có %d bài ở link này", len(songs))
    return 0


def cmd_download(args, data):
    name = args.tai_khoan
    account = known_account(data, name)
    url = read_link(args.link)
    fmt = args.format
    try:
        out = folder.Folder(args.out or ROOT / "nhac-suno")
    except folder.FolderError as e:
        raise UserError(str(e))
    done = failed = 0
    stopped = ""
    with single_run(data), browser(args, data, name, args.headless) as context:
        page, songs = songs_at(args, data, context, name, account, url)
        todo = [s for s in songs if not out.done(s.id, fmt)]
        log.info("Có %d bài: %d bài đã tải từ trước, %d bài cần tải %s vào %s", len(songs), len(songs) - len(todo),
                 len(todo), fmt.upper(), out.root)
        if args.limit is not None and len(todo) > args.limit:
            todo = todo[:args.limit]
            log.info("Lần này chỉ tải %d bài (--limit)", len(todo))
        catcher = web.Catcher(context)
        stuck = 0
        for n, song in enumerate(todo, 1):
            label = f"[{n}/{len(todo)}] {song.title or song.id}"
            part = out.part_path(song.id, fmt)
            try:
                shown = web.download_song(page, catcher, song, fmt, part, log)
                if not folder.audio_ok(part, fmt):
                    raise web.SunoError("stuck", f"File nhận được không phải {fmt.upper()}")
                title = song.title or shown
                path = out.target(title, song.id, fmt)
                part.replace(path)
                out.add(song, path, fmt, title)
            except Exception as e:
                log.debug("download failed", exc_info=True)
                log.error("%s: %s", label, describe(e))
                failed += 1
                code = getattr(e, "code", "")
                if isinstance(e, folder.FolderError):
                    stopped = str(e)
                    break
                if code in ("limit", "not_signed_in", "wrong_account"):
                    stopped = str(e)
                    break
                if code != "not_ready":
                    keep_failure(data, page, name)
                    stuck += 1
                    if stuck >= STUCK_IN_A_ROW:
                        stopped = (f"{STUCK_IN_A_ROW} bài liền nhau không tải được: có thể Suno đã đổi giao diện. "
                                   f"Gửi các file loi-*.png và loi-*.html trong {data.logs} cho người sửa tool")
                        break
                continue
            finally:
                with contextlib.suppress(OSError):
                    part.unlink()
            stuck = 0
            done += 1
            log.info("%s: xong → %s", label, path.name)
            page.wait_for_timeout(1500)  # a person's pace, not a burst
    if stopped:
        log.error("Đã dừng: %s", stopped)
    log.info("Tổng: %d bài tải xong, %d bài lỗi. Danh sách: %s", done, failed, out.list_path)
    return 1 if failed or stopped else 0


# ---- self-test (no browser) ----

def cmd_selftest(args, data):
    errors = []

    def check(cond, what):
        if not cond:
            errors.append(what)

    sid = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
    check(web.song_id_of(f"https://suno.com/song/{sid.upper()}?sh=x") == sid, "song id from a link")
    check(web.song_id_of("https://suno.com/create?wid=abc") is None, "not a song link")
    base = web.BASE
    try:
        web.BASE = "https://suno.com"
        check(web.check_link(" suno.com/create?wid=abc ") == "https://suno.com/create?wid=abc", "link without https")
        check(web.check_link("https://www.suno.com/playlist/x") == "https://www.suno.com/playlist/x", "www link")
        for bad in ("https://evil.example/create", "https://suno.com.evil.example/x", "javascript:alert(1)",
                    "https://suno.com/", "file:///C:/x", ""):
            try:
                web.check_link(bad)
                check(False, f"link refused: {bad}")
            except ValueError:
                pass
    finally:
        web.BASE = base
    sel = web.SEL
    check(sel["text_format"]["wav"].search("WAV Audio") and not sel["text_format"]["wav"].search("MP3 Audio"), "wav")
    check(sel["text_format"]["mp3"].search("MP3 Audio") and not sel["text_format"]["mp3"].search("Video"), "mp3")
    check(sel["text_download"].search("Download") and not sel["text_download"].search("Downloads left"), "download")
    check(all(sel["text_go"].search(t) for t in ("Download File", "Download", "continue")), "go buttons")
    check(not any(sel["text_go"].search(t) for t in ("Buy more downloads", "Download Video", "Cancel")), "not go")
    check(all(sel["text_buy"].search(t) for t in ("Buy more downloads", "Upgrade to Premier", "only $4.99")), "buy")
    check(not sel["text_buy"].search("Download WAV Audio. Preparing your file"), "not buy")
    check(sel["text_limit"].search("You've reached your download limit"), "limit")

    sf = folder.safe_filename
    check(sf("Mưa đêm", "x") == "Mưa đêm", "title kept")
    tricky = sf("../..\\a<b>:c|d?*", "x")
    check(tricky == "a b c d", f"title path parts {tricky!r}")
    check(sf("CON", "x") == "_CON" and sf("nul.txt", "x") == "_nul.txt", "Windows device names")
    check(sf("   ...  ", "suno-1") == "suno-1" and sf("", "suno-1") == "suno-1", "empty title")
    check(sf("a" * 200 + ".", "x") == "a" * folder.NAME_MAX, "long title")
    check(sf("end. ", "x") == "end", "trailing dot")
    check(sf("=SUM(A1)", "x") == "SUM(A1)" and sf("-rf x", "x") == "rf x", "no formula or option file names")
    check(folder.safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and folder.safe_cell("ok") == "ok", "csv formula")
    check(ACCOUNT_NAME_RE.fullmatch("suno-1") and not ACCOUNT_NAME_RE.fullmatch("-x")
          and not ACCOUNT_NAME_RE.fullmatch("tài khoản"), "account names")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a.wav").write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt " + bytes(2000))
        (tmp / "b.mp3").write_bytes(b"ID3\x04" + bytes(2000))
        (tmp / "c.wav").write_bytes(b"<html>error</html>" + bytes(2000))
        check(folder.audio_ok(tmp / "a.wav", "wav") and folder.audio_ok(tmp / "b.mp3", "mp3"), "audio files")
        check(not folder.audio_ok(tmp / "c.wav", "wav") and not folder.audio_ok(tmp / "b.mp3", "wav"), "not audio")
        out = folder.Folder(tmp / "nhac")
        song = web.Song(sid, "=Mưa đêm")
        p1 = out.target(song.title, sid, "wav")
        p1.write_bytes(b"x")
        out.add(song, p1, "wav", song.title)
        p2 = out.target(song.title, "11111111-2222-3333-4444-555555555555", "wav")
        check(p1.name == "Mưa đêm.wav" and p2.name == "Mưa đêm (2).wav", f"unique names {p1.name} {p2.name}")
        again = folder.Folder(tmp / "nhac")
        check(again.done(sid, "wav") and not again.done(sid, "mp3"), "the list read back")
        raw = again.list_path.read_text(encoding="utf-8-sig")
        check("'=Mưa đêm" in raw, "list formula guard")
        (tmp / "nhac" / folder.LIST_NAME).write_bytes(
            f"ten_bai;file;dinh_dang;link;luc;id\r\nA;A.wav;wav;;;{sid}\r\n".encode("utf-8-sig"))
        check(folder.Folder(tmp / "nhac").done(sid, "wav"), "a list saved by Excel with semicolons")
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
    p = argparse.ArgumentParser(prog="suno", description="Bokin Suno: tải các bài nhạc của một workspace Suno về máy")
    p.add_argument("--data", help="thư mục dữ liệu (mặc định ./data/suno)")
    p.add_argument("--headless", action="store_true", help="chạy Chrome không hiện cửa sổ")
    p.add_argument("--chrome", help="đường dẫn chrome.exe nếu không ở chỗ mặc định")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("login", help="đăng nhập một tài khoản Suno (mở Chrome)")
    s.add_argument("tai_khoan")
    s = sub.add_parser("check", help="kiểm tra các tài khoản còn đăng nhập")
    s.add_argument("tai_khoan", nargs="?")
    sub.add_parser("accounts", help="các tài khoản trên máy này")
    s = sub.add_parser("remove", help="xoá một tài khoản khỏi máy này")
    s.add_argument("tai_khoan")
    s = sub.add_parser("list", help="xem các bài ở link workspace, không tải")
    s.add_argument("tai_khoan")
    s.add_argument("link")
    s = sub.add_parser("download", help="tải các bài ở link workspace về thư mục")
    s.add_argument("tai_khoan")
    s.add_argument("link")
    s.add_argument("--out", help="thư mục lưu nhạc (mặc định ./nhac-suno)")
    s.add_argument("--format", choices=("wav", "mp3"), default="wav", help="wav (mặc định) hoặc mp3")
    s.add_argument("--limit", type=int, help="lần này chỉ tải tối đa chừng này bài")
    sub.add_parser("selftest", help="tự kiểm tra")
    args = p.parse_args(argv)
    if getattr(args, "limit", None) is not None and args.limit < 1:
        p.error("--limit phải từ 1 trở lên")

    data = Data(args.data or os.environ.get("BOKIN_SUNO_DATA") or ROOT / "data" / "suno")
    setup_logging(data)
    commands = {"login": cmd_login, "check": cmd_check, "accounts": cmd_accounts, "remove": cmd_remove,
                "list": cmd_list, "download": cmd_download, "selftest": cmd_selftest}
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
