"""suno.com, driven in a real Chrome: sign in once, read the songs of a workspace, download each song.

No Suno API: the program does what a person does on suno.com. It opens the workspace (or playlist) link, reads the
song links in its list while scrolling, then for each song opens the song's page and presses More options →
Download → WAV Audio (or MP3 Audio), answers Suno's download box and keeps the file Chrome receives. Downloads go
through Suno's own Download button, so Suno counts them exactly as when a person downloads by hand; when Suno says
the plan's downloads are used up, the run stops. The program never presses a Buy/Upgrade button and never takes the
audio any other way. Every selector and button text is in SEL. BOKIN_SUNO_URL points the program at a stand-in Suno
(tests/fake_suno.py).
"""
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

BASE = os.environ.get("BOKIN_SUNO_URL", "https://suno.com").rstrip("/")

SEL = {
    "song_link": 'a[href*="/song/"]',
    "sign_in": 'button:text-matches("^(sign in|log in|sign up)$", "i"), a:text-matches("^(sign in|log in)$", "i")',
    "next_page": 'button[aria-label="Next page" i], button:text-matches("^(load more|show more)$", "i")',
    "more": 'button[aria-label="More Options" i], button[aria-label="More options" i], '
            'button[aria-label="More actions" i], button[aria-label="More" i]',
    "menu_item": '[role="menuitem"], [role="menu"] button, [data-radix-popper-content-wrapper] button, '
                 '[data-radix-popper-content-wrapper] [role="button"]',
    "dialog": '[role="dialog"], [role="alertdialog"]',
    "dialog_button": 'button, a[href], [role="button"]',
    "song_title": "h1",
    # button and box texts (English UI)
    "text_download": re.compile(r"^download\b", re.I),
    "text_format": {"wav": re.compile(r"\bwav\b", re.I), "mp3": re.compile(r"\bmp3\b", re.I)},
    "text_go": re.compile(r"^(download( file| wav| mp3| audio| song)?|continue|confirm)$", re.I),
    "text_buy": re.compile(r"\b(buy|purchase|upgrade|subscribe|payment|checkout)\b|[$€£₫]\s?\d", re.I),
    "text_limit": re.compile(r"\b(limit|out of downloads|no downloads|0 downloads|downloads? (left|remaining))\b", re.I),
}

SONG_ID_RE = re.compile(r"/song/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
AUDIO_URL_RE = re.compile(r"\.(wav|mp3)$", re.I)

# window.Clerk is Suno's sign-in library: 'in:<user id>', 'out', 'loading' or 'none' (not on the page). It lives in
# the page's own JavaScript world, so it is read with isolated_context=False (patchright reads in a separate world)
JS_STATE = """() => { const c = window.Clerk; if (!c) return 'none'; if (!c.loaded) return 'loading';
  return c.user ? 'in:' + (c.user.id || '') : 'out'; }"""

# One pass over the song list: the songs it shows now, then a scroll. The list is the scrollable box holding most
# song links (marked so later passes use the same box); links in fixed or sticky bars (the player) are not songs of
# the list.
JS_COLLECT = r"""(sel) => {
  const ID = /\/song\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;
  const pinned = (el) => { for (let p = el; p && p !== document.body; p = p.parentElement) {
    const pos = getComputedStyle(p).position; if (pos === 'fixed' || pos === 'sticky') return true; } return false; };
  const scrollable = (el) => /(auto|scroll|overlay)/.test(getComputedStyle(el).overflowY)
    && el.scrollHeight > el.clientHeight + 4;
  const links = [...document.querySelectorAll(sel)].filter(a => ID.test(a.getAttribute('href') || '') && !pinned(a));
  let box = document.querySelector('[data-bokin-list]');
  if (!box || !box.isConnected) {
    const counts = new Map();
    for (const a of links) {
      let p = a.parentElement;
      while (p && p !== document.body && !scrollable(p)) p = p.parentElement;
      const b = (p && p !== document.body) ? p : document.scrollingElement;
      counts.set(b, (counts.get(b) || 0) + 1);
    }
    let best = 0; box = null;
    for (const [b, n] of counts) if (n > best) { box = b; best = n; }
    if (box && box !== document.scrollingElement) box.setAttribute('data-bokin-list', '1');
  }
  if (!box) return {songs: [], bottom: true, height: 0};
  const songs = [];
  for (const a of links) {
    if (box !== document.scrollingElement && !box.contains(a)) continue;
    const text = ((a.innerText || '').trim().split('\n')[0] || a.getAttribute('title') || '').trim();
    songs.push([a.getAttribute('href').match(ID)[1].toLowerCase(), text]);
  }
  const before = box.scrollTop;
  box.scrollTop = before + Math.max(200, box.clientHeight * 0.8);
  const bottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 4;
  return {songs, bottom, height: box.scrollHeight};
}"""


class SunoError(Exception):
    """A step on suno.com failed. code: not_signed_in, wrong_account, no_songs, not_ready, limit, stuck."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass
class Song:
    id: str
    title: str

    @property
    def link(self):
        return f"{BASE}/song/{self.id}"


# ---- links ----

def check_link(text):
    """A workspace, playlist or song link on suno.com -> the full URL. Raises ValueError (the reason, in Vietnamese)."""
    text = (text or "").strip().strip('"').strip("'")
    if text and "://" not in text:
        text = "https://" + text
    u = urlparse(text)
    allowed = {urlparse(BASE).netloc.lower()}
    if urlparse(BASE).netloc.lower() == "suno.com":
        allowed.add("www.suno.com")
    if u.scheme not in ("http", "https") or u.netloc.lower() not in allowed:
        raise ValueError(f"'{text}' không phải link của Suno. Mở workspace trên suno.com rồi chép link trên thanh "
                         "địa chỉ (dạng https://suno.com/...)")
    if u.path.strip("/") == "":
        raise ValueError("Link chỉ là trang chủ Suno. Mở đúng workspace rồi chép link trên thanh địa chỉ")
    return text


def song_id_of(url):
    m = SONG_ID_RE.search(urlparse(url).path)
    return m.group(1).lower() if m else None


# ---- small page helpers ----

def _visible(locator):
    try:
        return locator.is_visible()
    except Exception:
        return False


def _enabled(locator):
    try:
        return (locator.is_visible() and locator.is_enabled() and locator.get_attribute("aria-disabled") != "true"
                and locator.get_attribute("data-disabled") is None)
    except Exception:
        return False


def _text(locator):
    try:
        return re.sub(r"\s+", " ", locator.inner_text()).strip()
    except Exception:
        return ""


def _find_text(page, selector, pattern):
    """The first visible element of `selector` whose text (or aria-label) matches `pattern`, or None."""
    for loc in page.locator(selector).all():
        if not _visible(loc):
            continue
        text = _text(loc)
        if not text:
            try:
                text = loc.get_attribute("aria-label") or ""
            except Exception:
                text = ""
        if pattern.search(text):
            return loc
    return None


def _poll(page, find, timeout_ms, step_ms=100):
    """find() again and again until it returns something or the time is up: no fixed waits."""
    end = time.monotonic() + timeout_ms / 1000
    while True:
        found = find()
        if found or time.monotonic() >= end:
            return found
        page.wait_for_timeout(step_ms)


def _signed_out_url(url):
    return bool(re.search(r"/(sign-?in|log-?in|sign-?up)\b|accounts\.", url, re.I))


def page_state(page, wait_seconds=25):
    """('in', user id or None) or ('out', None) for the page as it is now (waits for the sign-in library)."""
    start = time.monotonic()
    while True:
        if _signed_out_url(page.url):
            return "out", None
        try:
            s = page.evaluate(JS_STATE, isolated_context=False)
        except Exception:
            s = "loading"  # the page is still navigating
        if s.startswith("in:"):
            return "in", s[3:] or None
        if s == "out":
            return "out", None
        waited = time.monotonic() - start
        if (s == "none" and waited > 8) or waited > wait_seconds:
            # no sign-in library to ask: a Sign in button means signed out
            return ("out", None) if _visible(page.locator(SEL["sign_in"]).first) else ("in", None)
        page.wait_for_timeout(500)


# ---- sign-in ----

def signed_in_user(page):
    """Opens suno.com; ('in', user id or None) or ('out', None)."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=90_000)
    return page_state(page)


def ensure_account(page, user_id):
    state, got = signed_in_user(page)
    if state != "in":
        raise SunoError("not_signed_in", "Tài khoản Suno chưa đăng nhập hoặc đã bị đăng xuất. Chạy lại: suno login <tên>")
    if user_id and got and got != user_id:
        raise SunoError("wrong_account", "Chrome đang đăng nhập một tài khoản Suno khác tài khoản đã lưu. "
                                         "Chạy lại: suno login <tên>")
    return got


def wait_for_login(context, log, settle_seconds=None, limit_minutes=30):
    """Opens suno.com in a visible window and waits while the person signs in and closes the window. Returns
    (signed_in, user id or None) as last seen. settle_seconds (tests) stops on its own once signed in that long."""
    closed = []
    context.on("close", lambda *_: closed.append(True))
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=90_000)
    host = urlparse(BASE).netloc.lower()
    signed_in, user, seen_at = False, None, 0.0
    deadline = time.monotonic() + limit_minutes * 60
    while not closed and time.monotonic() < deadline:
        try:
            pages = list(context.pages)
        except Exception:
            break
        if not pages:
            break
        for p in pages:
            if urlparse(p.url).netloc.lower() not in (host, "www." + host):
                continue
            try:
                s = p.evaluate(JS_STATE, isolated_context=False)
            except Exception:
                continue
            if s.startswith("in:") and (not signed_in or (s[3:] or None) != user):
                signed_in, user, seen_at = True, s[3:] or None, time.monotonic()
                log.info("Đã thấy đăng nhập Suno. Giờ đóng cửa sổ Chrome.")
            elif s == "out" and signed_in:
                signed_in, user = False, None
        if settle_seconds and signed_in and time.monotonic() - seen_at >= settle_seconds:
            break
        try:
            context.wait_for_event("close", timeout=1000)
        except Exception:
            pass
    return signed_in, user


# ---- the songs of a workspace ----

def list_songs(page, url, log, known=None, known_in_a_row=None, limit_minutes=20):
    """The songs shown at `url` (a workspace, playlist or song link), in the order shown. With known(id) and
    known_in_a_row, reading stops once that many songs in a row are known: Suno lists the newest songs first, so a
    second run reads only the top of a large workspace."""
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    if page_state(page)[0] != "in":
        raise SunoError("not_signed_in", "Tài khoản Suno chưa đăng nhập hoặc đã bị đăng xuất. Chạy lại: suno login <tên>")
    one = song_id_of(url)
    if one:
        return [Song(one, "")]
    try:
        page.locator(SEL["song_link"]).first.wait_for(state="attached", timeout=30_000)
    except Exception:
        raise SunoError("no_songs", "Không thấy bài nào ở link này. Kiểm tra link (mở link trong Chrome thường xem có "
                                    "đúng workspace không); workspace trống thì không có gì để tải")
    page.wait_for_timeout(1000)
    songs = {}
    quiet, last_height, last_logged, streak = 0, -1, 0, 0
    deadline = time.monotonic() + limit_minutes * 60
    while time.monotonic() < deadline:
        r = page.evaluate(JS_COLLECT, SEL["song_link"])
        new = 0
        for sid, text in r["songs"]:
            if sid not in songs:
                songs[sid] = text
                new += 1
                streak = streak + 1 if known and known(sid) else 0
                if known_in_a_row and streak >= known_in_a_row:
                    break
            elif len(text) > len(songs[sid]):
                songs[sid] = text
        if known_in_a_row and streak >= known_in_a_row:
            log.info("Đọc tới bài thứ %d thì gặp %d bài liền đã tải từ trước: dừng đọc danh sách (các bài phía dưới "
                     "đã tải rồi; muốn đọc hết thì thêm --full)", len(songs), streak)
            break
        if len(songs) >= last_logged + 50:
            last_logged = len(songs) - len(songs) % 50
            log.info("Đã đọc %d bài...", len(songs))
        if new or r["height"] != last_height:
            quiet, last_height = 0, r["height"]
        elif r["bottom"]:
            quiet += 1
        if quiet >= 3:  # at the end and nothing new after three looks: the next page, if there is one
            more = page.locator(SEL["next_page"]).first
            if not _enabled(more):
                break
            more.click()
            page.evaluate("() => { const b = document.querySelector('[data-bokin-list]') || document.scrollingElement; "
                          "b.scrollTop = 0; }")
            quiet = 0
        page.wait_for_timeout(350 if new and not r["bottom"] else 700)  # quicker while songs keep coming
    else:
        log.warning("Đọc danh sách quá %d phút, dừng ở %d bài", limit_minutes, len(songs))
    if not songs:
        raise SunoError("no_songs", "Không đọc được bài nào trong danh sách của trang này")
    return [Song(sid, text) for sid, text in songs.items()]


# ---- one download ----

class Catcher:
    """Every file Chrome downloads, in any tab, and every tab that opens an audio file directly."""

    def __init__(self, context):
        self.context = context
        self.downloads = []
        for p in context.pages:
            self._watch(p)
        context.on("page", self._watch)

    def _watch(self, page):
        page.on("download", lambda d: self.downloads.append(d))

    def reset(self):
        self.downloads.clear()

    def audio_tab(self, fmt):
        for p in self.context.pages:
            m = AUDIO_URL_RE.search(urlparse(p.url).path)
            if m and m.group(1).lower() == fmt:
                return p
        return None


def _song_title(page):
    loc = page.locator(SEL["song_title"]).first
    title = _text(loc).split("\n")[0] if _visible(loc) else ""
    if not title:
        try:
            title = page.evaluate("() => { const m = document.querySelector('meta[property=\"og:title\"]'); "
                                  "return m ? m.content : document.title; }") or ""
        except Exception:
            title = ""
        title = re.sub(r"\s*\|\s*Suno.*$", "", title).strip()
    return title


def _open_format_item(page, fmt):
    """More options → Download → WAV/MP3; returns the format item, ready to click."""
    more = page.locator(SEL["more"]).first
    try:
        more.wait_for(state="visible", timeout=15_000)
    except Exception:
        raise SunoError("stuck", "Không thấy nút More options (⋯) ở trang bài hát")
    want = SEL["text_format"][fmt]

    def format_item():
        return _find_text(page, SEL["menu_item"], want)

    def menu():
        item = format_item()
        if item:
            return "item", item
        down = _find_text(page, SEL["menu_item"], SEL["text_download"])
        return ("download", down) if down else None

    for _ in range(3):  # a click before the page is ready does nothing: open the menu again
        more.click()
        kind, loc = _poll(page, menu, 3000) or (None, None)
        if kind == "item":
            return loc
        if kind == "download":
            if not _enabled(loc):
                raise SunoError("not_ready", "Suno chưa cho tải bài này (bài chưa tạo xong hoặc bị lỗi)")
            loc.hover()
            item = _poll(page, format_item, 1500)
            if not item:
                loc.click()
                item = _poll(page, format_item, 2000)
            if item:
                return item
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    raise SunoError("stuck", f"Không thấy mục Download → {fmt.upper()} trong menu của bài hát")


def _answer_dialog(page, clicked):
    """Suno's download box: presses its Download button once it is ready. Never presses anything in a box that
    offers to buy or upgrade; such a box, or one saying the downloads are used up, stops the run."""
    for box in page.locator(SEL["dialog"]).all():
        if not _visible(box):
            continue
        text = _text(box)
        go = []
        for b in box.locator(SEL["dialog_button"]).all():
            label = _text(b) or (b.get_attribute("aria-label") or "")
            if SEL["text_go"].search(label):
                go.append((label, b))
        if SEL["text_buy"].search(text) or (SEL["text_limit"].search(text) and not go):
            raise SunoError("limit", f"Suno báo hết lượt tải của gói: \"{text[:160]}\". Tool dừng, không mua thêm")
        for label, b in go:
            if _enabled(b) and time.monotonic() - clicked.get(label, 0) > 10:
                b.click()
                clicked[label] = time.monotonic()
                return


def download_song(page, catcher, song, fmt, dest, log, timeout_seconds=300):
    """Downloads one song through its page's Download button into `dest`. Returns the title the page shows."""
    page.goto(song.link, wait_until="domcontentloaded", timeout=90_000)
    catcher.reset()
    try:
        item = _open_format_item(page, fmt)
    except SunoError as e:
        if e.code == "stuck" and page_state(page, wait_seconds=5)[0] != "in":
            raise SunoError("not_signed_in", "Tài khoản Suno đã bị đăng xuất. Chạy lại: suno login <tên>")
        raise
    title = song.title or _song_title(page)
    if not _enabled(item):
        raise SunoError("not_ready", f"Suno chưa cho tải bài này dạng {fmt.upper()} (bài chưa tạo xong hoặc bị lỗi)")
    item.click()
    clicked = {}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if catcher.downloads:
            d = catcher.downloads[-1]
            failure = d.failure()
            if failure:
                raise SunoError("stuck", f"Chrome tải file lỗi: {failure}")
            d.save_as(str(dest))
            break
        tab = catcher.audio_tab(fmt)
        if tab:  # Suno opened the file itself instead of downloading it: take the same file
            r = page.context.request.get(tab.url, timeout=timeout_seconds * 1000)
            if not r.ok:
                raise SunoError("stuck", f"Không lấy được file {fmt.upper()} (HTTP {r.status})")
            dest.write_bytes(r.body())
            if tab is page:
                page.go_back()
            else:
                tab.close()
            break
        _answer_dialog(page, clicked)
        page.wait_for_timeout(250)
    else:
        raise SunoError("stuck", f"Đã bấm tải {fmt.upper()} nhưng sau {timeout_seconds} giây vẫn chưa nhận được file")
    page.keyboard.press("Escape")  # close the download box, if it stays open
    return title


def save_failure(page, path_stem):
    """A screenshot of the window, and the open menus and boxes plus the page's button labels (no whole page: it holds
    account data), for fixing SEL."""
    try:
        page.screenshot(path=f"{path_stem}.png")
    except Exception:
        pass
    try:
        html = page.evaluate(r"""() => {
          const parts = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"], [role="menu"]')]
            .map(e => e.outerHTML);
          const labels = [...document.querySelectorAll('button, [role="button"], [role="menuitem"]')]
            .map(b => (b.getAttribute('aria-label') || '') + ' | ' + (b.innerText || '').trim().split('\n')[0])
            .map(t => t.replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, '<email>').slice(0, 80));
          const esc = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;');
          return '<p>' + esc(location.pathname) + '</p>' + parts.join('\n<hr>\n')
            + '<pre>' + esc(labels.join('\n')) + '</pre>';
        }""")
        with open(f"{path_stem}.html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass
