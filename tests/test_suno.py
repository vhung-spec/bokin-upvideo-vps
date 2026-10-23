"""End-to-end test of Bokin Suno against the stand-in Suno (tests/fake_suno.py), with a real Chrome.

Runs the program as a person would (python suno/bokin_suno.py ...): sign in, check, a workspace whose list loads as
it scrolls, a few songs first (--limit), then the rest with a song still being made, a second run that downloads
only new songs, MP3 through a "uses 1 download" box opening in a new tab, one song by its link, a Load more button,
the plan's downloads used up (nothing bought), a changed Suno page, the wrong account, a sign-out, removing the
account.

  python tests/test_suno.py [--headless] [--chrome PATH] [--keep]
On Linux without a screen: xvfb-run -a python tests/test_suno.py
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fake_suno import USER_ID, WORKSPACE, FakeSuno, audio_bytes  # noqa: E402

PROG = HERE.parent / "suno" / "bokin_suno.py"
failures = []


def check(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what, flush=True)
    if not cond:
        failures.append(what)


def read_list(folder):
    with open(folder / "danh-sach.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--chrome")
    ap.add_argument("--keep", action="store_true", help="keep the temporary folder")
    opts = ap.parse_args()

    fake = FakeSuno()
    titles = ["Mưa đêm", "Mưa đêm", "../../thoát ra", "CON", '=cmd|" /C calc"!A0', "<b>Đậm</b> & \"nháy\"",
              unicodedata.normalize("NFD", "Phố cũ")] + [f"Lofi số {n}" for n in range(1, 15)]
    ids = [fake.add_song(t) for t in titles[:10]]
    making = fake.add_song("Đang tạo", status="streaming")  # in the middle of the list
    ids += [fake.add_song(t) for t in titles[10:]]
    fake.start()
    # Linux: Chrome refuses a --user-data-dir with a long path, so the temporary folder stays short
    tmp = Path(tempfile.mkdtemp(prefix="sn-", dir=None if sys.platform == "win32" else "/tmp"))
    data = tmp / "data"
    env = dict(os.environ, BOKIN_SUNO_URL=fake.url, BOKIN_SUNO_DATA=str(data), BOKIN_SUNO_LOGIN_SETTLE="2",
               PYTHONIOENCODING="utf-8")
    base = [sys.executable, str(PROG)]
    if opts.headless:
        base.append("--headless")
    if opts.chrome:
        base += ["--chrome", opts.chrome]
    link = f"{fake.url}/create?wid={WORKSPACE}"

    def cli(*args, expect=0, contains=None):
        print(f"\n$ suno {' '.join(args)}", flush=True)
        r = subprocess.run(base + list(args), env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        out = r.stdout + r.stderr
        print(out.rstrip())
        check(r.returncode == expect, f"exit code {r.returncode} == {expect}")
        if contains:
            check(contains.lower() in out.lower(), f"output mentions '{contains}'")
        return out

    def files(folder, fmt):
        return sorted(p for p in folder.glob(f"*.{fmt}"))

    try:
        nhac = tmp / "nhac"
        print("== self-test")
        cli("selftest", contains="selftest OK")

        print("== before signing in")
        cli("download", "suno1", link, "--out", str(nhac), expect=2, contains="chưa đăng nhập")
        cli("login", "tài khoản", expect=2, contains="không hợp lệ")

        print("== sign in")
        cli("login", "suno1", contains="Đã lưu tài khoản suno1")
        accounts = json.loads((data / "accounts.json").read_text(encoding="utf-8"))
        check(accounts.get("suno1", {}).get("user_id") == USER_ID, "accounts.json has the Suno user ID")
        check(fake.signins == 1, "signed in once")
        fake.config["auto_signin"] = False
        cli("check", contains="đang đăng nhập")
        cli("accounts", contains="suno1")

        print("== links that are not a Suno workspace")
        cli("download", "suno1", "https://evil.example/create?wid=1", "--out", str(nhac), expect=2,
            contains="không phải link của Suno")
        cli("download", "suno1", f"{fake.url}/create?wid=nothing", "--out", str(nhac), expect=2,
            contains="Không thấy bài nào")

        print("== a few songs first")
        cli("download", "suno1", link, "--out", str(nhac), "--limit", "2", contains="2 bài tải xong")
        check(len(files(nhac, "wav")) == 2, "two WAV files")

        print("== the rest of the workspace; one song is still being made")
        cli("download", "suno1", link, "--out", str(nhac), expect=1, contains="19 bài tải xong, 1 bài lỗi")
        got = {p.name: p.read_bytes() for p in files(nhac, "wav")}
        check(len(got) == len(titles), f"{len(titles)} WAV files ({len(got)})")
        rows = read_list(nhac)
        by_id = {r["id"]: r for r in rows}
        check(set(by_id) == set(ids), "danh-sach.csv lists every downloaded song once")
        for sid in ids:
            rec = by_id.get(sid, {})
            check(got.get(rec.get("file")) == audio_bytes(sid, "wav"), f"{rec.get('file')} is that song's WAV")
        names = set(got)
        for name in ("Mưa đêm.wav", "Mưa đêm (2).wav", "thoát ra.wav", "_CON.wav", "Phố cũ.wav", "cmd C calc !A0.wav"):
            check(name in names, f"file name {name}")
        check(all(p.parent == nhac for p in nhac.rglob("*.wav")), "no file outside the folder")
        check(fake.stray not in by_id and making not in by_id, "the player's song and the unfinished song skipped")
        raw = (nhac / "danh-sach.csv").read_text(encoding="utf-8-sig")
        check("'=cmd" in raw, "a title starting with = is not a formula in Excel")
        check(sorted(fake.counted) == sorted(ids), "Suno counted each downloaded song once")
        check(not list(nhac.glob("*.part")) and not list(nhac.glob(".*.part")), "no half-downloaded files left")

        print("== again, with the song finished and two new songs: only those three")
        fake.songs[making]["status"] = "complete"
        new = [fake.add_song("Bài mới 1"), fake.add_song("Bài mới 2")]
        picked = len(fake.picked)
        cli("download", "suno1", link, "--out", str(nhac), contains="3 bài tải xong, 0 bài lỗi")
        check(sorted(s for s, _ in fake.picked[picked:]) == sorted(new + [making]), "only the three were downloaded")
        picked = len(fake.picked)
        cli("download", "suno1", link, "--out", str(nhac), contains="0 bài cần tải")
        check(len(fake.picked) == picked, "nothing downloaded twice")

        print("== MP3, a 'uses 1 download' box, the file opening in a new tab")
        fake.config.update(confirm=True, delivery="newtab")
        mp3 = tmp / "mp3"
        counted = len(fake.counted)
        cli("download", "suno1", link, "--out", str(mp3), "--format", "mp3", "--limit", "3", contains="3 bài tải xong")
        got = files(mp3, "mp3")
        check(len(got) == 3, "three MP3 files")
        check(all(p.read_bytes()[:3] == b"ID3" for p in got), "they are MP3")
        check(len(fake.counted) == counted, "songs already downloaded as WAV count no more")
        fake.config.update(confirm=False, delivery="attach")

        print("== one song by its link")
        one = tmp / "mot-bai"
        cli("download", "suno1", f"{fake.url}/song/{ids[6]}?sh=abc", "--out", str(one), contains="1 bài tải xong")
        check([p.name for p in files(one, "wav")] == ["Phố cũ.wav"], "named after the song page's title")
        fake.config["delivery"] = "blob"

        print("== a Load more button instead of scrolling")
        fake.config["paging"] = "button"
        out = cli("list", "suno1", link, contains=f"Có {len(fake.workspace)} bài")
        check(fake.stray not in out, "the player's song is not listed")
        fake.config["paging"] = "scroll"

        print("== the plan's downloads used up")
        fake.config["downloads_left"] = 1
        later = [fake.add_song("Hết lượt 1"), fake.add_song("Hết lượt 2")]
        cli("download", "suno1", link, "--out", str(nhac), expect=1, contains="hết lượt tải")
        rows = {r["id"] for r in read_list(nhac)}
        check(later[1] in rows and later[0] not in rows, "the one allowed download made, then stopped")
        check(fake.buy_clicks == 0, "nothing bought")
        fake.config["downloads_left"] = None

        print("== Suno's page changed")
        fake.config["more_label"] = "Song actions"
        for n in range(3):
            fake.add_song(f"Giao diện mới {n}")
        cli("download", "suno1", link, "--out", str(nhac), expect=1, contains="đổi giao diện")
        check(any(p.suffix == ".png" for p in (data / "logs").iterdir()), "a screenshot of the failure")
        check(any(p.suffix == ".html" for p in (data / "logs").iterdir()), "the page's buttons for fixing the tool")
        fake.config["more_label"] = "More Options"

        print("== the wrong account")
        saved = (data / "accounts.json").read_text(encoding="utf-8")
        other = json.loads(saved)
        other["suno1"]["user_id"] = "user_someoneElse"
        (data / "accounts.json").write_text(json.dumps(other), encoding="utf-8")
        cli("download", "suno1", link, "--out", str(nhac), expect=2, contains="tài khoản Suno khác")
        (data / "accounts.json").write_text(saved, encoding="utf-8")

        print("== signed out")
        fake.sign_everyone_out()
        cli("check", "suno1", expect=1, contains="đăng xuất")
        cli("download", "suno1", link, "--out", str(nhac), expect=2, contains="đăng xuất")

        print("== remove the account")
        cli("remove", "suno1", contains="Đã xoá")
        check(not (data / "profiles" / "suno1").exists(), "profile deleted")
        check(json.loads((data / "accounts.json").read_text(encoding="utf-8")) == {}, "account forgotten")
    finally:
        fake.stop()
        if opts.keep or failures:
            print(f"\nkept {tmp}")
            logs = data / "logs" / "suno.log"
            if failures and logs.exists():
                print(logs.read_text(encoding="utf-8")[-6000:])
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED: ' + '; '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
