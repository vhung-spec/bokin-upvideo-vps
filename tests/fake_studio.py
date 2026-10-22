"""A stand-in YouTube Studio for the tests: sign-in, the upload dialog, the Schedule date and time pickers.

It copies only what the program touches (studio.SEL): the element names and ids, a chunked upload with a progress
line, the Next button locked until a step is answered, the date and time fields that refuse a wrongly written value.
The tests change `config` to switch the date style (US/UK), 12h/24h time, the UI language, an Ad suitability step,
an upload that stops part way, and a sign-out. Everything the dialog sends back lands in `uploads` and `drafts`.
"""
import hashlib
import html
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CHANNEL_ID = "UCfakeBokinChannel000001"
DEFAULT_DESCRIPTION = "Default description from Upload defaults"


class FakeStudio:
    def __init__(self):
        self.config = {"lang": "en", "date_style": "mdy", "time_style": "12h", "questionnaire": False,
                       "stall_at": None, "chunk_delay": 0.03, "channel_id": CHANNEL_ID}
        self.sessions = set()
        self.signins = 0
        self.drafts = {}
        self.uploads = []
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.server.shutdown()

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
                    if k == "SID" and v in fake.sessions:
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

            def _redirect(self, to, headers=()):
                self._send(302, b"", headers=(("Location", to),) + tuple(headers))

            def do_GET(self):
                u = urlparse(self.path)
                own = fake.config["channel_id"]
                parts = [p for p in u.path.split("/") if p]
                if u.path == "/signin":
                    return self._send(200, SIGNIN_PAGE)
                if not self._signed_in():
                    return self._redirect("/signin?continue=" + u.path)
                if u.path == "/":
                    return self._redirect(f"/channel/{own}")
                if len(parts) >= 2 and parts[0] == "channel":
                    if parts[1] != own:  # an account without that channel lands on its own
                        rest = "/".join(parts[2:])
                        return self._redirect(f"/channel/{own}" + (f"/{rest}?{u.query}" if rest else ""))
                    if parts[2:] == ["videos", "upload"]:
                        cfg = {k: fake.config[k] for k in ("date_style", "time_style", "questionnaire")}
                        cfg["default_description"] = DEFAULT_DESCRIPTION
                        page = UPLOAD_PAGE.replace("__LANG__", html.escape(fake.config["lang"]))
                        return self._send(200, page.replace("__CFG__", json.dumps(cfg)))
                    return self._send(200, f'<html lang="{html.escape(fake.config["lang"])}"><body>'
                                           f'<h1>Channel dashboard</h1></body></html>')
                return self._send(404, "not found")

            def do_POST(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if u.path == "/signin":
                    sid = secrets.token_hex(16)
                    fake.sessions.add(sid)
                    fake.signins += 1
                    return self._send(303, b"", headers=(
                        ("Set-Cookie", f"SID={sid}; Max-Age=31536000; Path=/; HttpOnly"),
                        ("Location", f"/channel/{fake.config['channel_id']}")))
                if not self._signed_in():
                    return self._send(401, "signed out")
                if u.path == "/_chunk":
                    import time
                    vid = q["vid"][0]
                    with fake.lock:
                        d = fake.drafts.setdefault(vid, {"bytes": 0, "sha": hashlib.sha256(), "size": int(q["size"][0])})
                        if int(q["off"][0]) != d["bytes"]:
                            return self._send(400, json.dumps({"error": "out of order"}), "application/json")
                        d["sha"].update(body)
                        d["bytes"] += len(body)
                        pct = d["bytes"] * 100 // max(d["size"], 1)
                    time.sleep(fake.config["chunk_delay"])
                    stall = fake.config["stall_at"] is not None and pct >= fake.config["stall_at"] and pct < 100
                    return self._send(200, json.dumps({"stall": stall}), "application/json")
                if u.path == "/_publish":
                    rec = json.loads(body)
                    with fake.lock:
                        d = fake.drafts.get(rec.get("video_id"), {})
                        rec["bytes"] = d.get("bytes", 0)
                        rec["sha256"] = d["sha"].hexdigest() if d else ""
                        fake.uploads.append(rec)
                    return self._send(200, "{}", "application/json")
                return self._send(404, "not found")

        return Handler


SIGNIN_PAGE = """<!doctype html><html lang="en"><body>
<h1>Sign in</h1><form method="post" action="/signin"><button id="next">Next</button></form>
<script>setTimeout(() => document.forms[0].submit(), 300);</script>
</body></html>"""

UPLOAD_PAGE = r"""<!doctype html>
<html lang="__LANG__"><head><meta charset="utf-8"><title>Channel content - YouTube Studio</title>
<style>
  body { font: 14px sans-serif; }
  ytcp-uploads-dialog, ytcp-video-share-dialog, ytcp-date-picker, .step, #scheduler { display: block; }
  ytcp-uploads-dialog { border: 1px solid #ccc; padding: 12px; width: 900px; }
  [hidden] { display: none !important; }
  [contenteditable] { border: 1px solid #999; min-height: 1.5em; padding: 4px; white-space: pre-wrap; }
  ytcp-button, tp-yt-paper-radio-button, #second-container-expand-button, #checkbox-container,
  ytcp-text-dropdown-trigger { display: inline-block; border: 1px solid #555; padding: 4px 8px; margin: 4px;
    cursor: pointer; }
  [aria-disabled="true"] { opacity: .4; }
  [aria-checked="true"] { background: #def; }
  ytcp-date-picker { position: fixed; top: 80px; left: 300px; background: #fff; border: 2px solid #333; padding: 10px; }
</style></head>
<body>
<script type="application/json" id="cfg">__CFG__</script>
<ytcp-uploads-dialog>
  <div id="picker"><ytcp-uploads-file-picker>Select files <input type="file" name="Filedata"></ytcp-uploads-file-picker></div>
  <div id="body" hidden>
    <div class="step" id="step-details">
      <h2>Details</h2>
      Title <div id="title-textarea"><div id="textbox" contenteditable="true"></div></div>
      Description <div id="description-textarea"><div id="textbox" contenteditable="true"></div></div>
      Audience
      <tp-yt-paper-radio-button name="VIDEO_MADE_FOR_KIDS_MFK">Yes, it's made for kids</tp-yt-paper-radio-button>
      <tp-yt-paper-radio-button name="VIDEO_MADE_FOR_KIDS_NOT_MFK">No, it's not made for kids</tp-yt-paper-radio-button>
    </div>
    <div class="step" id="step-ads" hidden>
      <h2>Ad suitability</h2>
      <div class="ytpp-self-certification-questionnaire">
        <div id="checkbox-container" role="checkbox" aria-checked="false">None of the above</div>
        <ytcp-button id="submit-questionnaire-button" aria-disabled="true">Submit rating</ytcp-button>
      </div>
    </div>
    <div class="step" id="step-elements" hidden><h2>Video elements</h2></div>
    <div class="step" id="step-checks" hidden><h2>Checks</h2>No issues found</div>
    <div class="step" id="step-visibility" hidden>
      <h2>Visibility</h2>
      <div id="privacy-radios">
        <tp-yt-paper-radio-button name="PRIVATE">Private</tp-yt-paper-radio-button>
        <tp-yt-paper-radio-button name="UNLISTED">Unlisted</tp-yt-paper-radio-button>
        <tp-yt-paper-radio-button name="PUBLIC">Public</tp-yt-paper-radio-button>
      </div>
      <div id="second-container-expand-button" role="button">Schedule</div>
      <div id="scheduler" hidden>
        <ytcp-datetime-picker>
          <ytcp-text-dropdown-trigger id="datepicker-trigger"><span id="date-text"></span></ytcp-text-dropdown-trigger>
          <ytcp-form-input-container id="time-of-day-container"><tp-yt-paper-input><input id="time-input"></tp-yt-paper-input></ytcp-form-input-container>
        </ytcp-datetime-picker>
      </div>
    </div>
    <ytcp-video-info>Video link <a id="link" href="https://youtu.be/">https://youtu.be/</a></ytcp-video-info>
    <ytcp-video-upload-progress><span class="progress-label"></span></ytcp-video-upload-progress>
    <ytcp-button id="next-button" aria-disabled="true">Next</ytcp-button>
    <ytcp-button id="done-button" hidden>Save</ytcp-button>
  </div>
</ytcp-uploads-dialog>
<ytcp-date-picker hidden><tp-yt-paper-dialog><tp-yt-paper-input><input id="date-input"></tp-yt-paper-input></tp-yt-paper-dialog></ytcp-date-picker>
<ytcp-video-share-dialog hidden><h2 id="share-title"></h2></ytcp-video-share-dialog>
<script>
const cfg = JSON.parse(document.getElementById('cfg').textContent);
const $ = (s) => document.querySelector(s);
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const steps = ['details'].concat(cfg.questionnaire ? ['ads'] : [], ['elements', 'checks', 'visibility']);
let step = 0, vid = null, uploadDone = false, kids = null, privacy = 'PRIVATE', scheduled = false, adsDone = false;
const title = $('#title-textarea #textbox'), desc = $('#description-textarea #textbox');
const next = $('#next-button'), done = $('#done-button'), label = $('.progress-label');
const dateText = $('#date-text'), timeInput = $('#time-input'), dateInput = $('#date-input');

function fmtDate(d) {
  return cfg.date_style === 'dmy' ? `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
                                  : `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}
function parseDate(s) {
  s = s.trim();
  const m = cfg.date_style === 'dmy' ? s.match(/^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})$/)
                                     : s.match(/^([A-Z][a-z]{2}) (\d{1,2}), (\d{4})$/);
  if (!m) return null;
  const [day, mon, year] = cfg.date_style === 'dmy' ? [m[1], m[2], m[3]] : [m[2], m[1], m[3]];
  const mi = MONTHS.indexOf(mon);
  if (mi < 0) return null;
  const d = new Date(+year, mi, +day);
  return d.getDate() === +day ? d : null;
}
function fmtTime(h, mi) {
  if (cfg.time_style === '24h') return `${String(h).padStart(2, '0')}:${String(mi).padStart(2, '0')}`;
  return `${(h % 12) || 12}:${String(mi).padStart(2, '0')} ${h >= 12 ? 'PM' : 'AM'}`;
}
function parseTime(s) {
  s = s.replace(/[  ]/g, ' ').trim();
  if (cfg.time_style === '24h') {
    const m = s.match(/^(\d{1,2}):(\d{2})$/);
    return m && +m[1] < 24 && +m[2] < 60 ? [+m[1], +m[2]] : null;
  }
  const m = s.match(/^(\d{1,2}):(\d{2}) (AM|PM)$/i);
  if (!m || +m[1] < 1 || +m[1] > 12 || +m[2] > 59) return null;
  return [(+m[1] % 12) + (m[3].toUpperCase() === 'PM' ? 12 : 0), +m[2]];
}

function show() {
  document.querySelectorAll('.step').forEach((el) => { el.hidden = el.id !== 'step-' + steps[step]; });
  const last = steps[step] === 'visibility';
  next.hidden = last;
  done.hidden = !last;
  update();
}
function update() {
  const s = steps[step];
  let ok = true;
  if (s === 'details') ok = title.innerText.trim() !== '' && kids !== null;
  if (s === 'ads') ok = adsDone;
  next.setAttribute('aria-disabled', ok ? 'false' : 'true');
  done.setAttribute('aria-disabled', title.innerText.trim() ? 'false' : 'true');
  done.textContent = scheduled ? 'Schedule' : (privacy === 'PUBLIC' ? 'Publish' : 'Save');
}
title.addEventListener('input', update);
document.querySelectorAll('tp-yt-paper-radio-button[name^="VIDEO_MADE_FOR_KIDS"]').forEach((r) =>
  r.addEventListener('click', () => {
    kids = r.getAttribute('name');
    document.querySelectorAll('tp-yt-paper-radio-button[name^="VIDEO_MADE_FOR_KIDS"]').forEach((o) =>
      o.setAttribute('aria-checked', o === r ? 'true' : 'false'));
    update();
  }));
document.querySelectorAll('#privacy-radios tp-yt-paper-radio-button').forEach((r) =>
  r.addEventListener('click', () => { privacy = r.getAttribute('name'); scheduled = false; $('#scheduler').hidden = true; update(); }));
$('#checkbox-container').addEventListener('click', (e) => {
  const on = e.target.getAttribute('aria-checked') !== 'true';
  e.target.setAttribute('aria-checked', on ? 'true' : 'false');
  $('#submit-questionnaire-button').setAttribute('aria-disabled', on ? 'false' : 'true');
});
$('#submit-questionnaire-button').addEventListener('click', (e) => {
  if (e.target.getAttribute('aria-disabled') === 'true') return;
  adsDone = true; update();
});
let typed = { title: '', description: '' };  // innerText while the details step is shown keeps the line breaks
next.addEventListener('click', () => {
  if (next.getAttribute('aria-disabled') === 'true') return;
  if (steps[step] === 'details') typed = { title: title.innerText, description: desc.innerText };
  step = Math.min(step + 1, steps.length - 1); show();
});
$('#second-container-expand-button').addEventListener('click', () => {
  scheduled = true; $('#scheduler').hidden = false;
  document.querySelectorAll('#privacy-radios tp-yt-paper-radio-button').forEach((o) => o.setAttribute('aria-checked', 'false'));
  if (!dateText.textContent) {
    const t = new Date(Date.now() + 86400000);
    dateText.textContent = fmtDate(t);
    timeInput.value = fmtTime(21, 0);
    timeInput.dataset.good = timeInput.value;
  }
  update();
});
$('#datepicker-trigger').addEventListener('click', () => {
  $('ytcp-date-picker').hidden = false; dateInput.value = dateText.textContent; dateInput.focus();
});
dateInput.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  const d = parseDate(dateInput.value);
  if (!d) { dateInput.setAttribute('aria-invalid', 'true'); return; }
  dateText.textContent = fmtDate(d); $('ytcp-date-picker').hidden = true;
});
function commitTime() {
  const t = parseTime(timeInput.value);
  timeInput.value = t ? fmtTime(t[0], t[1]) : timeInput.dataset.good;
  timeInput.dataset.good = timeInput.value;
}
timeInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') commitTime(); });
timeInput.addEventListener('blur', commitTime);

$('input[name="Filedata"]').addEventListener('change', (e) => {
  const f = e.target.files[0];
  vid = Array.from(crypto.getRandomValues(new Uint8Array(11)), (b) => 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'[b % 64]).join('');
  $('#link').href = 'https://youtu.be/' + vid; $('#link').textContent = $('#link').href;
  $('#picker').hidden = true; $('#body').hidden = false;
  title.textContent = f.name.replace(/\.[^.]+$/, '');
  desc.textContent = cfg.default_description;
  show();
  upload(f);
});
async function upload(f) {
  const CH = 512 * 1024;
  let off = 0;
  label.textContent = 'Uploading 0% ...';
  while (off < f.size) {
    const chunk = f.slice(off, off + CH);
    const r = await fetch(`/_chunk?vid=${vid}&off=${off}&size=${f.size}`, { method: 'POST', body: chunk });
    const j = await r.json();
    off += chunk.size;
    const pct = Math.floor(off * 100 / f.size);
    label.textContent = `Uploading ${pct}% ... 1 minute left`;
    if (j.stall) return;
  }
  uploadDone = true;
  label.textContent = 'Upload complete ... Processing will begin shortly';
}
done.addEventListener('click', async () => {
  if (done.getAttribute('aria-disabled') === 'true') return;
  await fetch('/_publish', { method: 'POST', body: JSON.stringify({
    video_id: vid, channel: location.pathname.split('/')[2], title: typed.title, description: typed.description,
    kids, privacy, scheduled, date_text: dateText.textContent, time_text: timeInput.value,
    upload_complete: uploadDone, button: done.textContent }) });
  $('ytcp-uploads-dialog').hidden = true;
  $('ytcp-video-share-dialog').hidden = false;
  $('#share-title').textContent = scheduled ? 'Video scheduled' : 'Video published';
});
</script>
</body></html>
"""
