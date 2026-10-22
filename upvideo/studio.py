"""YouTube Studio, driven in a real Chrome: sign in once, then upload a video and schedule it.

No YouTube API: the program does what a person does in Studio (choose the file, type the title and description,
open "Schedule", type the date and time, press Schedule). Every Studio selector is in SEL, so a change in Studio's
page is fixed in one place. BOKIN_UPVIDEO_STUDIO points the program at a stand-in Studio (tests/fake_studio.py).

Safety: the video is only ever scheduled. If any step fails before the Schedule button is pressed, the video stays a
private draft in Studio; nothing is made public at a wrong time.
"""
import os
import re
import time
from datetime import date

STUDIO = os.environ.get("BOKIN_UPVIDEO_STUDIO", "https://studio.youtube.com").rstrip("/")

SEL = {
    "file_input": 'ytcp-uploads-file-picker input[type="file"], input[type="file"][name="Filedata"], input[type="file"]',
    "title": "#title-textarea #textbox",
    "description": "#description-textarea #textbox",
    "not_for_kids": 'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
    "next": "#next-button",
    "done": "#done-button",
    "privacy_radios": "#privacy-radios",
    "schedule_open": "#second-container-expand-button, #schedule-radio-button",
    "date_trigger": "#datepicker-trigger",
    "date_input": "ytcp-date-picker tp-yt-paper-input input, ytcp-date-picker input",
    "time_input": "#time-of-day-container input, ytcp-datetime-picker tp-yt-paper-input input",
    "progress": "ytcp-video-upload-progress .progress-label, ytcp-video-upload-progress span, .progress-label",
    "video_link": 'ytcp-video-info a[href*="youtu"], .video-url-fadeable a[href*="youtu"], a[href^="https://youtu.be/"]',
    "error": "#error-message, .error-short",
    "monetization": "#child-input ytcp-video-monetization",
    "monetization_on": "ytcp-video-monetization-edit-dialog #radioContainer #onRadio",
    "monetization_save": "ytcp-video-monetization-edit-dialog #save-button",
    "questionnaire": ".ytpp-self-certification-questionnaire",
    "questionnaire_none": ".ytpp-self-certification-questionnaire #checkbox-container",
    "questionnaire_submit": ".ytpp-self-certification-questionnaire #submit-questionnaire-button",
    "prechecks_continue": "#dialog-buttons #secondary-action-button",
    "published": "ytcp-video-share-dialog, ytcp-uploads-still-processing-dialog",
    "upload_dialog": "ytcp-uploads-dialog",
}

CHANNEL_RE = re.compile(r"/channel/(UC[A-Za-z0-9_-]{22})")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class StudioError(Exception):
    """A step in Studio failed. code: not_signed_in, wrong_channel, language, stuck, upload_failed, stalled,
    schedule, publish."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---- dates and times as Studio shows them (English UI only) ----

def _clean(text):
    return re.sub(r"[\s  ]+", " ", text or "").strip()


def parse_studio_date(text):
    """'Oct 25, 2026' (English US) or '25 Oct 2026' (English UK) -> (date, style); style is 'mdy' or 'dmy'."""
    text = _clean(text)  # searched, not matched whole: the trigger may carry a label beside the date
    m = re.search(r"\b([A-Za-z]{3,9})\.? (\d{1,2}),? (\d{4})\b", text)
    if m:
        mon, day, year, style = m.group(1), m.group(2), m.group(3), "mdy"
    else:
        m = re.search(r"\b(\d{1,2}) ([A-Za-z]{3,9})\.?,? (\d{4})\b", text)
        if not m:
            return None
        day, mon, year, style = m.group(1), m.group(2), m.group(3), "dmy"
    months = [x.lower() for x in MONTHS]
    if mon[:3].lower() not in months:
        return None
    try:
        return date(int(year), months.index(mon[:3].lower()) + 1, int(day)), style
    except ValueError:
        return None


def format_studio_date(d, style):
    if style == "dmy":
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def parse_studio_time(text):
    """'8:00 PM' -> ((20, 0), '12h'); '20:00' -> ((20, 0), '24h')."""
    text = _clean(text)
    m = re.fullmatch(r"(\d{1,2}):(\d{2}) ?([AaPp])\.? ?[Mm]\.?", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if not (1 <= h <= 12 and mi < 60):
            return None
        h = h % 12 + (12 if m.group(3).lower() == "p" else 0)
        return (h, mi), "12h"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        return (int(m.group(1)), int(m.group(2))), "24h"
    return None


def format_studio_time(h, mi, style):
    if style == "24h":
        return f"{h:02d}:{mi:02d}"
    return f"{(h % 12) or 12}:{mi:02d} {'PM' if h >= 12 else 'AM'}"


def upload_state(text):
    """The upload progress line -> ('uploading', percent or None) | ('done', None) | ('failed', None)."""
    low = _clean(text).lower()
    if any(w in low for w in ("failed", "canceled", "cancelled", "abandoned")):
        return "failed", None
    if not low or "uploading" in low:
        m = re.search(r"(\d{1,3})\s*%", low)
        return "uploading", int(m.group(1)) if m else None
    return "done", None


# ---- small page helpers ----

def _visible(page, selector):
    try:
        return page.locator(selector).first.is_visible()
    except Exception:
        return False


def _enabled(locator):
    try:
        return (locator.is_visible() and locator.get_attribute("aria-disabled") != "true"
                and locator.get_attribute("disabled") is None)
    except Exception:
        return False


def _wait_visible(page, selector, timeout_ms):
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False


def _blur(page):
    page.evaluate("() => { const a = document.activeElement; if (a && a.blur) a.blur(); }")


def _signed_out(url):
    low = url.lower()
    return "accounts.google.com" in low or "/signin" in low or "servicelogin" in low


# ---- sign-in ----

def signed_in_channel(page):
    """Opens Studio; the channel ID it lands on, or None when the profile is signed out."""
    page.goto(STUDIO + "/", wait_until="domcontentloaded", timeout=90_000)
    for _ in range(60):
        if _signed_out(page.url):
            return None
        m = CHANNEL_RE.search(page.url)
        if m:
            return m.group(1)
        page.wait_for_timeout(500)
    return None


def wait_for_login(context, log, settle_seconds=None, limit_minutes=30):
    """Opens Studio in a visible window and waits while the person signs in, opens the right channel and closes the
    window. Returns the channel ID last seen in Studio (None if none). settle_seconds (tests) stops on its own once a
    channel has been open that long."""
    closed = []
    context.on("close", lambda *_: closed.append(True))
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(STUDIO + "/", wait_until="domcontentloaded", timeout=90_000)
    last, seen_at = None, 0.0
    deadline = time.monotonic() + limit_minutes * 60
    while not closed and time.monotonic() < deadline:
        try:
            pages = list(context.pages)
        except Exception:
            break
        if not pages:
            break
        for p in pages:
            m = CHANNEL_RE.search(p.url)
            if m and m.group(1) != last:
                last, seen_at = m.group(1), time.monotonic()
                log.info("Studio đang mở kênh %s", last)
        if settle_seconds and last and time.monotonic() - seen_at >= settle_seconds:
            break
        try:
            context.wait_for_event("close", timeout=1000)
        except Exception:
            pass
    return last


# ---- one upload ----

def _open_upload(page, channel_id):
    page.goto(f"{STUDIO}/channel/{channel_id}/videos/upload?d=ud", wait_until="domcontentloaded", timeout=90_000)
    file_input = page.locator(SEL["file_input"]).first
    for _ in range(120):
        if _signed_out(page.url):
            raise StudioError("not_signed_in", "Kênh chưa đăng nhập hoặc đã bị đăng xuất. Chạy lại: upvideo login <kênh>")
        if file_input.count():
            break
        page.wait_for_timeout(500)
    else:
        raise StudioError("stuck", "Không mở được hộp tải video lên của YouTube Studio")
    if f"/channel/{channel_id}" not in page.url:
        raise StudioError("wrong_channel", f"Tài khoản đang đăng nhập không mở được kênh {channel_id} "
                                           "(Studio chuyển sang kênh khác). Chạy lại: upvideo login <kênh>")
    lang = (page.evaluate("document.documentElement.lang || ''") or "").lower()
    if not lang.startswith("en"):
        raise StudioError("language", f"YouTube Studio đang dùng ngôn ngữ '{lang or '?'}'. Tool chỉ đọc được giao diện "
                                      "tiếng Anh: vào Studio → ảnh đại diện → Language → English (US), rồi chạy lại")
    return file_input


def _fill_box(page, selector, text, what):
    box = page.locator(selector).first
    if not _wait_visible(page, selector, 120_000):
        raise StudioError("stuck", f"Không thấy ô {what} trong Studio")
    box.click()
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.press("Delete")
    if text:
        box.fill(text)  # one insert: typing letter by letter opens the #hashtag / @mention pop-ups
    page.wait_for_timeout(300)
    _blur(page)
    got = _clean(box.inner_text())
    if got != _clean(text):
        raise StudioError("stuck", f"Ô {what} trong Studio không nhận đúng nội dung")


def _answer_questionnaire(page, log):
    try:
        page.locator(SEL["questionnaire_none"]).first.click()
        page.wait_for_timeout(800)
        page.locator(SEL["questionnaire_submit"]).first.click()
        page.wait_for_timeout(1500)
        log.info("Đã trả lời mục Ad suitability: None of the above")
    except Exception as e:
        log.warning("Không trả lời được mục Ad suitability: %s", e)


def _turn_on_monetization(page, log):
    try:
        page.locator(SEL["monetization"]).first.click()
        page.locator(SEL["monetization_on"]).first.click()
        page.wait_for_timeout(800)
        page.locator(SEL["monetization_save"]).first.click()
        page.wait_for_timeout(1500)
        log.info("Đã bật kiếm tiền cho video")
    except Exception as e:
        log.warning("Không bật được kiếm tiền cho video: %s", e)


def _go_to_visibility(page, log):
    nxt = page.locator(SEL["next"]).first
    for _ in range(15):
        if _visible(page, SEL["privacy_radios"]):
            return
        if _visible(page, SEL["questionnaire"]):
            _answer_questionnaire(page, log)
        if _enabled(nxt):
            nxt.click()
        elif _visible(page, SEL["monetization"]):
            _turn_on_monetization(page, log)
        page.wait_for_timeout(1500)
    raise StudioError("stuck", "Không qua được các bước tới mục Visibility (nút Next bị khoá)")


def _set_schedule(page, when, log):
    page.locator(SEL["schedule_open"]).first.click()
    trigger = page.locator(SEL["date_trigger"]).first
    time_box = page.locator(SEL["time_input"]).first
    if not _wait_visible(page, SEL["date_trigger"], 15_000) or not _wait_visible(page, SEL["time_input"], 15_000):
        raise StudioError("schedule", "Không thấy ô ngày/giờ của mục Schedule")
    shown_date = parse_studio_date(trigger.inner_text())
    shown_time = parse_studio_time(time_box.input_value())
    if not shown_date or not shown_time:
        raise StudioError("schedule", f"Không đọc được ngày/giờ Studio hiện: '{_clean(trigger.inner_text())}' "
                                      f"'{_clean(time_box.input_value())}'")
    want_date = format_studio_date(when.date(), shown_date[1])
    want_time = format_studio_time(when.hour, when.minute, shown_time[1])

    trigger.click()
    if not _wait_visible(page, SEL["date_input"], 10_000):
        raise StudioError("schedule", "Không mở được lịch chọn ngày")
    date_box = page.locator(SEL["date_input"]).first
    date_box.fill(want_date)
    date_box.press("Enter")
    page.wait_for_timeout(800)

    time_box.click()
    time_box.fill(want_time)
    time_box.press("Enter")
    page.wait_for_timeout(800)
    _blur(page)
    page.wait_for_timeout(500)

    got_date = parse_studio_date(trigger.inner_text())
    got_time = parse_studio_time(time_box.input_value())
    if not got_date or got_date[0] != when.date() or not got_time or got_time[0] != (when.hour, when.minute):
        raise StudioError("schedule", f"Studio không nhận giờ đăng {want_date} {want_time} (đang hiện "
                                      f"'{_clean(trigger.inner_text())}' '{_clean(time_box.input_value())}')")
    log.info("Đã đặt lịch đăng: %s %s", want_date, want_time)


def _wait_uploaded(page, log, stall_minutes):
    last_pct, last_change, last_logged = None, time.monotonic(), -10
    while True:
        text = ""
        for loc in page.locator(SEL["progress"]).all():
            try:
                text = _clean(loc.inner_text())
            except Exception:
                continue
            if text:
                break
        state, pct = upload_state(text)
        if state == "failed":
            raise StudioError("upload_failed", f"YouTube báo tải lên lỗi: {text}")
        if state == "done":
            log.info("Tải lên xong: %s", text[:80])
            return
        if pct != last_pct:
            last_pct, last_change = pct, time.monotonic()
            if pct is not None and pct >= last_logged + 10:
                last_logged = pct - pct % 10
                log.info("Đang tải lên: %s%%", pct)
        elif time.monotonic() - last_change > stall_minutes * 60:
            raise StudioError("stalled", f"Tải lên đứng yên quá {stall_minutes:g} phút ({text or 'không có tiến độ'})")
        page.wait_for_timeout(3000)


def _video_link(page):
    for _ in range(240):
        for loc in page.locator(SEL["video_link"]).all():
            try:
                href = loc.get_attribute("href") or ""
            except Exception:
                continue
            if re.search(r"(youtu\.be/|watch\?v=|/shorts/)[A-Za-z0-9_-]{6,}", href):
                return href
        page.wait_for_timeout(500)
    return ""


def _publish(page, log):
    done = page.locator(SEL["done"]).first
    if not _enabled(done):
        err = ""
        for loc in page.locator(SEL["error"]).all():
            try:
                err = err or _clean(loc.inner_text())
            except Exception:
                pass
        raise StudioError("publish", "Nút Schedule bị khoá" + (f": {err}" if err else ""))
    done.click()
    for _ in range(180):
        if _visible(page, SEL["published"]) or not _visible(page, SEL["done"]):
            return
        if _visible(page, SEL["prechecks_continue"]):
            page.locator(SEL["prechecks_continue"]).first.click()
            log.info("Đã bỏ qua hộp kiểm tra trước khi đăng")
        page.wait_for_timeout(500)
    raise StudioError("publish", "Bấm Schedule nhưng Studio không xác nhận")


def upload_scheduled(page, channel_id, video_path, title, description, when, log, *, stall_minutes=30,
                     before_publish=None, now=None):
    """Uploads video_path to channel_id and schedules it for `when` (a naive datetime in the browser's time zone).
    before_publish(link) is called just before the Schedule button is pressed; now() (same time zone) stops a
    schedule that a long upload has overtaken. Returns the video link."""
    file_input = _open_upload(page, channel_id)
    log.info("Chọn file %s", video_path)
    file_input.set_input_files(str(video_path))
    _fill_box(page, SEL["title"], title, "tiêu đề")
    if description:  # empty: keep the channel's default description (Studio → Settings → Upload defaults)
        _fill_box(page, SEL["description"], description, "mô tả")
    if _wait_visible(page, SEL["not_for_kids"], 15_000):
        page.locator(SEL["not_for_kids"]).first.click()
    else:
        log.warning("Không thấy câu hỏi 'Made for kids'; dùng mặc định của kênh")
    _go_to_visibility(page, log)
    _set_schedule(page, when, log)
    _wait_uploaded(page, log, stall_minutes)
    link = _video_link(page)
    if now and (when - now()).total_seconds() < 120:
        raise StudioError("schedule", f"Giờ đăng {when:%Y-%m-%d %H:%M} đã qua trong lúc tải lên; video để nháp riêng "
                                      "tư trong Studio. Đặt giờ muộn hơn rồi chạy lại")
    if before_publish:
        before_publish(link)
    _publish(page, log)
    page.wait_for_timeout(3000)  # let Studio finish saving before the window closes
    return link


def save_failure(page, path_stem):
    """A screenshot and the upload dialog's HTML (not the whole page: it holds session data) for fixing selectors."""
    try:
        page.screenshot(path=f"{path_stem}.png", full_page=True)
    except Exception:
        pass
    try:
        html = page.evaluate("() => { const d = document.querySelector('ytcp-uploads-dialog'); "
                             "return d ? d.outerHTML : ''; }")
        if html:
            with open(f"{path_stem}.html", "w", encoding="utf-8") as f:
                f.write(html)
    except Exception:
        pass
