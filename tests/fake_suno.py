"""A stand-in suno.com for the tests: sign-in, a workspace's song list, a song page with its Download menu and box.

It copies only what the program touches (suno/web.py SEL): window.Clerk for the sign-in state, song links in a
scrolling list that loads more as it scrolls (or by a Load more button) and drops rows scrolled far away, a player
bar with a link to a song not in the workspace, More Options → Download → MP3 Audio / WAV Audio, the WAV box that
prepares the file before its Download File button works, an optional "uses 1 download" box for MP3, the box saying
the plan's downloads are used up, with a Buy button that must never be pressed, and song pages that fail once
(`fail_once`). Files arrive as a download
(from a blob or a link) or open in a new tab, as `config["delivery"]` says. Like Suno, a song counts as one download
whatever the format and however often it is downloaded.
"""
import hashlib
import html
import json
import secrets
import struct
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

USER_ID = "user_fakeBokinSuno0001"
WORKSPACE = "7b0c5f4e-ws01-4e4e-9c9c-000000000001"
PAGE_SIZE = 15


def audio_bytes(song_id, fmt):
    """The song's file: a short WAV (RIFF) or MP3 (ID3), different for every song."""
    seed = hashlib.sha256(f"{song_id}|{fmt}".encode()).digest()
    body = (seed * 700)[:20000]
    if fmt == "wav":
        return (b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000,
                16000, 2, 16) + b"data" + struct.pack("<I", len(body)) + body)
    return b"ID3\x04\x00\x00\x00\x00\x00\x00" + body


class FakeSuno:
    def __init__(self):
        self.config = {"auto_signin": True, "user_id": USER_ID, "delivery": "blob", "confirm": False,
                       "downloads_left": None, "paging": "scroll", "prepare_ms": 800, "more_label": "More Options"}
        self.sessions = set()
        self.signins = 0
        self.songs = {}
        self.workspace = []
        self.counted = []  # songs Suno counted as downloads (each song once)
        self.picked = []  # (song id, format) every time a format was chosen in the menu
        self.buy_clicks = 0
        self.fail_once = set()  # song pages that answer with an error the first time
        self.list_pages = []  # the pages of the workspace's list that were asked for
        self.lock = threading.Lock()
        self.stray = self.add_song("Bài đang phát", in_workspace=False)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.server.shutdown()

    def add_song(self, title, status="complete", in_workspace=True):
        sid = str(uuid.uuid4())
        self.songs[sid] = {"title": title, "status": status}
        if in_workspace:
            self.workspace.insert(0, sid)  # newest first, as Suno lists them
        return sid

    def sign_everyone_out(self):
        self.sessions.clear()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _signed_in(self):
                for part in (self.headers.get("Cookie") or "").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == "__session" and v in fake.sessions:
                        return True
                return False

            def _send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=()):
                if isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in headers:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _page(self, body, script=""):
                user = json.dumps({"id": fake.config["user_id"]}) if self._signed_in() else "null"
                return self._send(200, PAGE.replace("__USER__", user).replace("__BODY__", body)
                                  .replace("__SCRIPT__", script))

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                parts = [p for p in u.path.split("/") if p]
                if u.path == "/sign-in":
                    return self._send(200, SIGNIN_PAGE)
                if u.path == "/":
                    auto = "true" if fake.config["auto_signin"] else "false"
                    return self._page('<h1>Explore</h1>' + ("" if self._signed_in() else SIGN_IN_BUTTON),
                                      f"setTimeout(() => {{ if (!window.Clerk.user && {auto}) location.href = "
                                      f"'/sign-in'; }}, 500);")
                if len(parts) == 2 and parts[0] in ("files", "cdn"):
                    sid, _, fmt = parts[1].rpartition(".")
                    if sid not in fake.songs or fmt not in ("wav", "mp3"):
                        return self._send(404, "not found")
                    ctype = "audio/wav" if fmt == "wav" else "audio/mpeg"
                    disp = (("Content-Disposition", f'attachment; filename="{sid}.{fmt}"'),) if parts[0] == "files" \
                        else ()
                    return self._send(200, audio_bytes(sid, fmt), ctype, disp)
                if not self._signed_in():
                    return self._page(SIGN_IN_BUTTON)
                if u.path == "/create":
                    if q.get("wid", [""])[0] != WORKSPACE:
                        return self._page("<h1>Create</h1><p>Workspace not found</p>")
                    cfg = json.dumps({"wid": WORKSPACE, "paging": fake.config["paging"], "stray": fake.stray})
                    return self._page(WORKSPACE_BODY, WORKSPACE_SCRIPT.replace("__CFG__", cfg))
                if len(parts) == 3 and parts[:2] == ["api", "ws"]:
                    page = int(q.get("page", ["0"])[0])
                    fake.list_pages.append(page)
                    ids = fake.workspace[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
                    out = {"songs": [{"id": s, "title": fake.songs[s]["title"]} for s in ids],
                           "more": (page + 1) * PAGE_SIZE < len(fake.workspace)}
                    return self._send(200, json.dumps(out), "application/json")
                if len(parts) == 2 and parts[0] == "song" and parts[1] in fake.fail_once:
                    fake.fail_once.discard(parts[1])
                    return self._send(503, "<html><body><h1>Something went wrong</h1></body></html>")
                if len(parts) == 2 and parts[0] == "song" and parts[1] in fake.songs:
                    song = fake.songs[parts[1]]
                    cfg = json.dumps({"id": parts[1], "title": song["title"], "delivery": fake.config["delivery"],
                                      "confirm": fake.config["confirm"], "prepare_ms": fake.config["prepare_ms"]})
                    body = (SONG_BODY.replace("__TITLE__", html.escape(song["title"]))
                            .replace("__MORE__", html.escape(fake.config["more_label"]))
                            .replace("__DISABLED__", "" if song["status"] == "complete" else 'aria-disabled="true"')
                            .replace("__STRAY__", fake.stray))
                    return self._page(body, SONG_SCRIPT.replace("__CFG__", cfg))
                return self._send(404, "not found")

            def do_POST(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                parts = [p for p in u.path.split("/") if p]
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if u.path == "/sign-in":
                    sid = secrets.token_hex(16)
                    fake.sessions.add(sid)
                    fake.signins += 1
                    return self._send(303, b"", headers=(
                        ("Set-Cookie", f"__session={sid}; Max-Age=31536000; Path=/; HttpOnly"), ("Location", "/")))
                if not self._signed_in():
                    return self._send(401, "signed out")
                if u.path == "/api/buy":
                    fake.buy_clicks += 1
                    return self._send(200, "{}", "application/json")
                if len(parts) == 3 and parts[:2] == ["api", "download"] and parts[2] in fake.songs:
                    sid, fmt = parts[2], q.get("fmt", [""])[0]
                    with fake.lock:
                        fake.picked.append((sid, fmt))
                        if sid not in fake.counted:
                            left = fake.config["downloads_left"]
                            if left is not None and left <= 0:
                                return self._send(200, json.dumps({"limit": True}), "application/json")
                            if left is not None:
                                fake.config["downloads_left"] = left - 1
                            fake.counted.append(sid)
                    return self._send(200, json.dumps({"ok": True}), "application/json")
                return self._send(404, "not found")

        return Handler


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Suno</title>
<style>
  body { font: 14px sans-serif; margin: 0; padding: 10px 10px 60px; }
  [hidden] { display: none !important; }
  button, [role=menuitem] { display: inline-block; border: 1px solid #555; padding: 4px 8px; margin: 2px;
    cursor: pointer; background: #fff; }
  [role=menu] { position: absolute; background: #fff; border: 1px solid #333; padding: 4px; z-index: 5; }
  [role=menuitem] { display: block; }
  [aria-disabled=true], button:disabled { opacity: .4; }
  [role=dialog] { position: fixed; top: 100px; left: 200px; width: 420px; background: #fff; border: 2px solid #333;
    padding: 16px; z-index: 10; }
  .player { position: fixed; left: 0; right: 0; bottom: 0; height: 40px; background: #eee; }
  .row { height: 56px; border-bottom: 1px solid #ddd; display: flex; align-items: center; gap: 8px; }
  #songs { height: 420px; overflow-y: auto; border: 1px solid #999; width: 700px; }
</style></head>
<body>
<script>
window.Clerk = {loaded: false, user: null};
setTimeout(() => { window.Clerk.user = __USER__; window.Clerk.loaded = true; }, 300);
</script>
__BODY__
<script>__SCRIPT__</script>
</body></html>"""

SIGN_IN_BUTTON = '<button id="signin" onclick="location.href=\'/sign-in\'">Sign In</button>'

SIGNIN_PAGE = """<!doctype html><html lang="en"><body>
<h1>Sign in to Suno</h1><form method="post" action="/sign-in"><button>Continue with Google</button></form>
<script>setTimeout(() => document.forms[0].submit(), 300);</script>
</body></html>"""

WORKSPACE_BODY = """
<aside><a href="/create">Create</a> <a href="/me">Library</a></aside>
<h2>My Workspace</h2>
<div id="songs"><div id="spacer"></div><div id="rows"></div><button id="loadmore" hidden>Load more</button></div>
<div class="player">Now playing: <a href="/song/" id="stray">Bài đang phát</a></div>
"""

WORKSPACE_SCRIPT = """
const cfg = __CFG__;
const box = document.getElementById('songs'), rows = document.getElementById('rows');
const spacer = document.getElementById('spacer'), more = document.getElementById('loadmore');
document.getElementById('stray').href = '/song/' + cfg.stray;
let page = 0, hasMore = true, loading = false, dropped = 0;
function load() {
  if (loading || !hasMore) return;
  loading = true;
  fetch(`/api/ws/${cfg.wid}?page=${page}`).then(r => r.json()).then(j => {
    for (const s of j.songs) {
      const row = document.createElement('div'); row.className = 'row';
      const cover = document.createElement('a'); cover.href = '/song/' + s.id; cover.innerHTML = '<img alt="">';
      const title = document.createElement('a'); title.href = '/song/' + s.id; title.textContent = s.title;
      const tag = document.createElement('span'); tag.textContent = 'v5';
      const btn = document.createElement('button'); btn.setAttribute('aria-label', 'More Options');
      btn.textContent = '...';
      row.append(cover, title, tag, btn); rows.append(row);
    }
    page += 1; hasMore = j.more; loading = false;
    more.hidden = !(cfg.paging === 'button' && hasMore);
    trim();
  });
}
function trim() {  // like a virtual list: rows far above the view are dropped, a spacer keeps the height
  while (rows.children.length > 20) {
    const first = rows.children[0];
    if (first.offsetTop + first.offsetHeight > box.scrollTop - 200) break;
    dropped += first.offsetHeight; first.remove(); spacer.style.height = dropped + 'px';
  }
}
box.addEventListener('scroll', () => {
  trim();
  if (cfg.paging === 'scroll' && box.scrollTop + box.clientHeight > box.scrollHeight - 100) setTimeout(load, 300);
});
more.addEventListener('click', load);
setTimeout(load, 400);
"""

SONG_BODY = """
<h1>__TITLE__</h1>
<div><button aria-label="Like">Like</button> <button aria-label="__MORE__" id="more">...</button></div>
<div role="menu" id="menu" hidden>
  <div role="menuitem">Remix/Edit</div>
  <div role="menuitem">Add to Playlist</div>
  <div role="menuitem" id="dl" __DISABLED__>Download &rsaquo;</div>
</div>
<div role="menu" id="sub" hidden style="margin-left: 160px">
  <div role="menuitem" data-fmt="mp3">MP3 Audio</div>
  <div role="menuitem" data-fmt="wav">WAV Audio</div>
  <div role="menuitem" data-fmt="video">Video</div>
</div>
<div role="dialog" id="dlg" hidden></div>
<section><h3>Comments</h3><div>Nice! <button aria-label="More Options">...</button></div></section>
<div class="player">Now playing: <a href="/song/__STRAY__">Bài đang phát</a></div>
"""

SONG_SCRIPT = """
const cfg = __CFG__;
const $ = (s) => document.querySelector(s);
const menu = $('#menu'), sub = $('#sub'), dl = $('#dl'), dlg = $('#dlg');
$('#more').addEventListener('click', () => { menu.hidden = !menu.hidden; sub.hidden = true; });
const openSub = () => { if (dl.getAttribute('aria-disabled') !== 'true') sub.hidden = false; };
dl.addEventListener('mouseenter', openSub);
dl.addEventListener('click', openSub);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { menu.hidden = sub.hidden = true; dlg.hidden = true; }
});
function box(inner) { dlg.innerHTML = inner; dlg.hidden = false; }
function deliver(fmt) {
  const url = `/files/${cfg.id}.${fmt}`;
  if (cfg.delivery === 'newtab') { window.open(`/cdn/${cfg.id}.${fmt}`, '_blank'); }
  else if (cfg.delivery === 'attach') {
    const a = document.createElement('a'); a.href = url; document.body.append(a); a.click();
  }
  else fetch(url).then(r => r.blob()).then(b => {
    const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = cfg.title + '.' + fmt;
    document.body.append(a); a.click();
  });
  dlg.hidden = true;
}
for (const item of sub.querySelectorAll('[data-fmt]')) item.addEventListener('click', () => {
  const fmt = item.dataset.fmt;
  menu.hidden = sub.hidden = true;
  if (fmt === 'video') return;
  fetch(`/api/download/${cfg.id}?fmt=${fmt}`, {method: 'POST'}).then(r => r.json()).then(j => {
    if (j.limit) {
      box(`<h2>You've reached your download limit</h2><p>Your plan's downloads for this month are used up.</p>
           <button id="buy">Buy more downloads</button> <button onclick="dlg.hidden = true">Close</button>`);
      $('#buy').addEventListener('click', () => fetch('/api/buy', {method: 'POST'}));
      return;
    }
    if (fmt === 'wav') {
      box(`<h2>Download WAV Audio</h2><p id="state">Preparing your file...</p>
           <button onclick="dlg.hidden = true">Cancel</button> <button id="go" disabled>Download File</button>`);
      setTimeout(() => { $('#state').textContent = 'Your file is ready'; $('#go').disabled = false; }, cfg.prepare_ms);
      $('#go').addEventListener('click', () => deliver('wav'));
    } else if (cfg.confirm) {
      box(`<h2>Download MP3 Audio</h2><p>This uses 1 of your downloads.</p>
           <button onclick="dlg.hidden = true">Cancel</button> <button id="go">Download</button>`);
      $('#go').addEventListener('click', () => deliver('mp3'));
    } else deliver('mp3');
  });
});
"""
