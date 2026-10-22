"""End-to-end test of Bokin Up Video against the stand-in Studio (tests/fake_studio.py), with a real Chrome.

Runs the program as a person would (python upvideo/bokin_upvideo.py ...): sign in, check, a schedule file with good
and bad rows, a second run that uploads nothing twice, UK dates with 24-hour time and an Ad suitability step, a
non-English Studio, the wrong channel, an upload that stops part way, a sign-out, removing the channel.

  python tests/test_upvideo.py [--headless] [--chrome PATH] [--keep]
On Linux without a screen: xvfb-run -a python tests/test_upvideo.py
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fake_studio import CHANNEL_ID, DEFAULT_DESCRIPTION, FakeStudio  # noqa: E402

PROG = HERE.parent / "upvideo" / "bokin_upvideo.py"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
failures = []


def check(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what, flush=True)
    if not cond:
        failures.append(what)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--chrome")
    ap.add_argument("--keep", action="store_true", help="keep the temporary folder")
    opts = ap.parse_args()

    fake = FakeStudio().start()
    tmp = Path(tempfile.mkdtemp(prefix="upvideo-test-"))
    data = tmp / "data"
    env = dict(os.environ, BOKIN_UPVIDEO_STUDIO=fake.url, BOKIN_UPVIDEO_DATA=str(data), BOKIN_UPVIDEO_LOGIN_SETTLE="2",
               PYTHONIOENCODING="utf-8")
    base = [sys.executable, str(PROG), "--stall-minutes", "0.25"]
    if opts.headless:
        base.append("--headless")
    if opts.chrome:
        base += ["--chrome", opts.chrome]

    def cli(*args, expect=0, contains=None):
        print(f"\n$ upvideo {' '.join(args)}", flush=True)
        r = subprocess.run(base + list(args), env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        out = r.stdout + r.stderr
        print(out.rstrip())
        check(r.returncode == expect, f"exit code {r.returncode} == {expect}")
        if contains:
            check(contains.lower() in out.lower(), f"output mentions '{contains}'")
        return out

    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    now = datetime.now(tz).replace(tzinfo=None, second=0, microsecond=0)
    t1, t2, t3, t4 = (now + timedelta(days=d, hours=h) for d, h in ((1, 2), (2, 5), (3, 1), (4, 3)))
    t1, t2, t3, t4 = (t.replace(minute=m) for t, m in ((t1, 0), (t2, 45), (t3, 30), (t4, 15)))

    def us(t):
        h = t.hour % 12 or 12
        return f"{MONTHS[t.month - 1]} {t.day}, {t.year}", f"{h}:{t.minute:02d} {'PM' if t.hour >= 12 else 'AM'}"

    try:
        video1, video2 = tmp / "video1.mp4", tmp / "video 2.mp4"
        video1.write_bytes(os.urandom(3 * 1024 * 1024 + 17))
        video2.write_bytes(os.urandom(24 * 1024 * 1024 + 5))
        sha = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (video1, video2)}

        print("== self-test")
        cli("selftest", contains="selftest OK")

        print("== before signing in")
        cli("upload", "kenh1", str(video1), "--title", "T", "--at", f"{t1:%Y-%m-%d %H:%M}", expect=2,
            contains="chưa đăng nhập")
        cli("login", "kênh 1", expect=2, contains="không hợp lệ")

        print("== sign in")
        cli("login", "kenh1", contains="Đã lưu kênh kenh1")
        channels = json.loads((data / "channels.json").read_text(encoding="utf-8"))
        check(channels.get("kenh1", {}).get("channel_id") == CHANNEL_ID, "channels.json has the channel ID")
        check(fake.signins == 1, "signed in once")
        cli("check", contains="đang đăng nhập")
        cli("channels", contains=CHANNEL_ID)

        print("== a schedule file (semicolons, Vietnamese headers, BOM)")
        (tmp / "mo-ta.txt").write_text("Nhạc thư giãn suốt 10 giờ.\nTheo dõi kênh nhé #lofi @bokin", encoding="utf-8")
        rows = [
            ["Kênh", "Video", "Tiêu đề", "Mô tả", "Giờ đăng"],
            ["kenh1", "video1.mp4", "Nhạc thư giãn 10 giờ #lofi", "@mo-ta.txt", f"{t1:%d/%m/%Y %H:%M}"],
            ["kenh1", str(video2), "Video 2: mưa đêm", "", f"{t2:%Y-%m-%d %H:%M}"],
            ["kenh1", "thieu.mp4", "Không có file", "", f"{t2:%Y-%m-%d %H:%M}"],
            ["kenh1", "video1.mp4", "Giờ đã qua", "", f"{now - timedelta(hours=1):%Y-%m-%d %H:%M}"],
            ["kenh9", "video1.mp4", "Kênh lạ", "", f"{t2:%Y-%m-%d %H:%M}"],
        ]
        with open(tmp / "lich.csv", "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f, delimiter=";").writerows(rows)
        cli("run", str(tmp / "lich.csv"), expect=1, contains="2 xong, 3 lỗi")
        check(len(fake.uploads) == 2, f"two videos scheduled ({len(fake.uploads)})")
        if len(fake.uploads) == 2:
            a, b = fake.uploads
            check(a["title"] == "Nhạc thư giãn 10 giờ #lofi", "title 1")
            check(a["description"] == "Nhạc thư giãn suốt 10 giờ.\nTheo dõi kênh nhé #lofi @bokin", "description 1")
            check(b["description"] == DEFAULT_DESCRIPTION, "empty description keeps the channel default")
            for rec, t, p in ((a, t1, video1), (b, t2, video2)):
                check(rec["scheduled"] and rec["button"] == "Schedule", "scheduled, not published")
                check((rec["date_text"], rec["time_text"]) == us(t), f"date and time {us(t)} == "
                                                                     f"{(rec['date_text'], rec['time_text'])}")
                check(rec["upload_complete"], "Schedule pressed only after the upload finished")
                check(rec["sha256"] == sha[p] and rec["bytes"] == p.stat().st_size, f"{p.name} arrived whole")
                check(rec["kids"] == "VIDEO_MADE_FOR_KIDS_NOT_MFK", "not made for kids")
                check(rec["channel"] == CHANNEL_ID, "right channel")
        with open(tmp / "lich.ketqua.csv", encoding="utf-8-sig", newline="") as f:
            results = list(csv.DictReader(f))
        status = {r["dong"]: r for r in results}
        check([status.get(str(n), {}).get("trang_thai") for n in range(2, 7)] == ["xong", "xong", "loi", "loi", "loi"],
              "results file statuses")
        if len(fake.uploads) == 2:
            check(status["2"]["link"].endswith(fake.uploads[0]["video_id"]), "results file has the video link")
        check("không thấy file" in status.get("4", {}).get("ghi_chu", ""), "missing file reported")
        check("đã qua" in status.get("5", {}).get("ghi_chu", ""), "past time reported")
        check("chưa đăng nhập" in status.get("6", {}).get("ghi_chu", ""), "unknown channel reported")

        print("== the same file again uploads nothing twice")
        cli("run", str(tmp / "lich.csv"), expect=1, contains="2 bỏ qua")
        check(len(fake.uploads) == 2, "no duplicate uploads")

        print("== UK dates, 24-hour time, an Ad suitability step")
        fake.config.update(date_style="dmy", time_style="24h", questionnaire=True)
        cli("upload", "kenh1", str(video1), "--title", "Bad <title>", "--at", f"{t3:%Y-%m-%d %H:%M}", expect=2,
            contains="< hoặc >")
        (tmp / "desc.txt").write_text("Mô tả từ file", encoding="utf-8")
        cli("upload", "kenh1", str(video1), "--title", "UK video", "--at", f"{t3:%Y-%m-%d %H:%M}",
            "--description-file", str(tmp / "desc.txt"), contains="Xong")
        check(len(fake.uploads) == 3, "third video scheduled")
        if len(fake.uploads) == 3:
            c = fake.uploads[2]
            check((c["date_text"], c["time_text"]) == (f"{t3.day} {MONTHS[t3.month - 1]} {t3.year}",
                                                      f"{t3.hour:02d}:{t3.minute:02d}"), "UK date, 24-hour time")
            check(c["description"] == "Mô tả từ file" and c["title"] == "UK video", "title and description")
        fake.config.update(date_style="mdy", time_style="12h", questionnaire=False)

        print("== Studio not in English")
        drafts = len(fake.drafts)
        fake.config["lang"] = "vi"
        cli("upload", "kenh1", str(video1), "--title", "T", "--at", f"{t4:%Y-%m-%d %H:%M}", expect=2,
            contains="ngôn ngữ")
        check(len(fake.drafts) == drafts, "no file sent")
        fake.config["lang"] = "en"

        print("== the wrong channel")
        saved = (data / "channels.json").read_text(encoding="utf-8")
        other = json.loads(saved)
        other["kenh1"]["channel_id"] = "UCsomeOtherChannel000002"
        (data / "channels.json").write_text(json.dumps(other), encoding="utf-8")
        cli("upload", "kenh1", str(video1), "--title", "T", "--at", f"{t4:%Y-%m-%d %H:%M}", expect=2,
            contains="kênh khác")
        (data / "channels.json").write_text(saved, encoding="utf-8")

        print("== an upload that stops part way")
        fake.config["stall_at"] = 30
        cli("upload", "kenh1", str(video2), "--title", "Stalls", "--at", f"{t4:%Y-%m-%d %H:%M}", expect=2,
            contains="đứng yên")
        check(len(fake.uploads) == 3, "nothing scheduled")
        check(any(p.suffix == ".png" for p in (data / "logs").iterdir()), "a screenshot of the failure")
        fake.config["stall_at"] = None

        print("== signed out")
        fake.sign_everyone_out()
        cli("check", "kenh1", expect=1, contains="đăng xuất")
        with open(tmp / "lich2.csv", "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows([["kenh", "video", "tieu_de", "gio_dang"],
                                     ["kenh1", "video1.mp4", "A", f"{t4:%Y-%m-%d %H:%M}"],
                                     ["kenh1", "video1.mp4", "B", f"{t4 + timedelta(hours=1):%Y-%m-%d %H:%M}"]])
        cli("run", str(tmp / "lich2.csv"), expect=1, contains="0 xong, 2 lỗi")
        with open(tmp / "lich2.ketqua.csv", encoding="utf-8-sig", newline="") as f:
            notes = [r["ghi_chu"] for r in csv.DictReader(f)]
        check(len(notes) == 2 and "đăng xuất" in notes[0] and "kênh kenh1 đã bị đăng xuất" in notes[1],
              "the second row was not tried after the sign-out")

        print("== remove the channel")
        cli("remove", "kenh1", contains="Đã xoá")
        check(not (data / "profiles" / "kenh1").exists(), "profile deleted")
        check(json.loads((data / "channels.json").read_text(encoding="utf-8")) == {}, "channel forgotten")
    finally:
        fake.stop()
        if opts.keep or failures:
            print(f"\nkept {tmp}")
            logs = data / "logs" / "upvideo.log"
            if failures and logs.exists():
                print(logs.read_text(encoding="utf-8")[-6000:])
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED: ' + '; '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
