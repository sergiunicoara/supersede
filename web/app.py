"""A read-only web demo of Supersede: ask a question, see the value in force and why.

Standard library only (plus the supersede package). It serves one page and a small JSON API over the
committed FICTIONAL demo store, opened read-only. No accounts, no API keys, no writes, no model calls.

    python web/app.py                 # http://127.0.0.1:7860
    PORT=8080 SUPERSEDE_DB=path python web/app.py

GET /                      the page
GET /api/ask?q=...&as_of=  the same result as Store.ask(), as JSON (as_of is optional, YYYY-MM-DD)
GET /api/answer?key=subject.predicate&as_of=   the value in force for one key (as_of optional), as JSON
GET /api/examples          sample questions
GET /healthz               "ok"
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from supersede.store import Store  # noqa: E402
import timeline  # noqa: E402

DEFAULT_DB = ROOT / "examples" / "store" / "supersede-demo.relate"
MAX_QUESTION = 300
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEY = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")
EXAMPLES = [
    {"q": "How long must retained samples be kept?"},
    {"q": "What sampling rule applied?", "as_of": "2025-07-01"},
    {"q": "Which form do inspectors fill in for final inspection results?"},
    {"q": "After how many parts do we swap the cutting tools in the machining cell?"},
    {"q": "What torque do we use on the cylinder head bolts?", "as_of": "2025-08-01"},
    {"q": "Who is the plant manager?"},  # not in any document: shows the refusal
]

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Supersede demo</title>
<style>
:root{color-scheme:light dark;--fg:#0f172a;--bg:#fff;--mut:#475569;--line:#cbd5e1;--ok:#166534;--warn:#b45309;--bad:#b91c1c;--card:#f8fafc}
@media (prefers-color-scheme:dark){:root{--fg:#e2e8f0;--bg:#0f172a;--mut:#94a3b8;--line:#334155;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--card:#1e293b}}
body{font:16px/1.5 system-ui,Segoe UI,Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg);margin:0}
main{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:1.5rem;margin:.2em 0}p.sub{color:var(--mut);margin-top:0}
form{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
input[type=text]{flex:1 1 320px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
input[type=date]{padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
button{padding:10px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);font:inherit;cursor:pointer}
button.go{background:#1d4ed8;border-color:#1d4ed8;color:#fff}
.ex{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}.ex button{font-size:.85rem;padding:6px 10px}
.card{border:1px solid var(--line);border-radius:10px;padding:14px;background:var(--card);margin-top:12px}
.big{font-size:1.4rem;font-weight:600}.mut{color:var(--mut)}.tag{display:inline-block;padding:1px 8px;border-radius:999px;border:1px solid var(--line);font-size:.8rem}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
ul{margin:.4em 0;padding-left:1.2em}footer{margin:24px 0;color:var(--mut);font-size:.85rem}
.tlbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}.tlbar select{padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit;max-width:100%}.tlbar input[type=range]{flex:1 1 220px}details{margin-top:10px}pre{overflow:auto;background:var(--bg);border:1px solid var(--line);padding:8px;border-radius:6px;font-size:.8rem}
</style></head><body><main>
<h1>Supersede</h1>
<p class="sub">Agent memory that knows which fact is currently in force, and why. Ask about the fictional quality documents.</p>
<form id="f"><input id="q" type="text" maxlength="300" placeholder="How long must retained samples be kept?" aria-label="Question" required>
<input id="d" type="date" aria-label="As of date (optional)" title="As of date (optional)"><button class="go" type="submit">Ask</button></form>
<div class="ex" id="ex"></div>
<div id="out" aria-live="polite"></div>
<h2 style="font-size:1.1rem;margin:28px 0 4px">Watch the answer change over time</h2>
<p class="sub" style="margin:0 0 4px">Pick a question and drag the date. Each bar is a revision, colour is authority, the gold outline is the value in force that day.</p>
<div class="tlbar"><select id="key" aria-label="Question"></select><input id="slider" type="range" min="0" max="1" value="0" aria-label="Date"><span id="dlabel" class="tag"></span></div>
<div id="live" class="card" aria-live="polite"></div>
<img id="tl" alt="Timeline of the revisions in force" style="width:100%;height:auto;border:1px solid var(--line);border-radius:10px;background:#fff">
<footer>All data is fictional. Read-only; nothing you type is stored. Retrieval is Relate's full-text and vector indexes; the answer comes from the graph
(supersession, authority, ties, dates). Source: <a href="https://github.com/sergiunicoara/supersede">github.com/sergiunicoara/supersede</a>.</footer>
<script>
const $=id=>document.getElementById(id);
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e}
function line(parent,text,cls){const p=el('div',cls||'',text);parent.appendChild(p);return p}
function render(r){
  const out=$('out');out.textContent='';const c=el('div','card');out.appendChild(c);
  if(r.error){line(c,r.error,'bad');return}
  if(r.status==='no_match'||r.status==='no_topics'){line(c,'No answer: '+r.reason,'warn');line(c,'That is deliberate. Supersede only answers from the documents it holds, and none of them covers this question, so it says so instead of guessing.','mut');return}
  const a=r.answer,m=r.matched;
  line(c,'Topic: '+m.subject+' / '+m.predicate,'mut');line(c,m.description,'mut');
  const st=el('div','');st.appendChild(el('span','tag',a.status));if(a.as_of)st.appendChild(el('span','tag','as of '+a.as_of));c.appendChild(st);
  if(a.status==='resolved'||a.status==='agreed'){
    line(c,a.value,'big ok');line(c,'from '+(a.source||a.sources.join(', ')))}
  if(a.status==='unresolved'){line(c,'The sources disagree and have equal authority, so no value is chosen.','big warn')}
  if(a.status==='unknown'){line(c,'No fact is in force for this topic.','big warn')}
  if(a.reason)line(c,'Why: '+a.reason);
  const lst=(title,items)=>{if(!items.length)return;line(c,title,'mut');const u=el('ul');items.forEach(i=>u.appendChild(el('li','',i)));c.appendChild(u)};
  lst('Overruled:',(a.overruled||[]).map(o=>o.value+' ('+o.rev+', authority '+o.authority+')'));
  lst('Candidates:',(a.candidates||[]).map(o=>o.value+' ('+o.rev+', authority '+o.authority+')'));
  lst('Stale source:',(r.stale_sources||[]).map(s=>s.revision+' was written from '+s.source+', which '+s.replaced_by.join(', ')+' replaced'));
  lst('Date notes:',(a.warnings||[]).map(w=>w.revision+': '+w.detail));
  if((r.alternatives||[]).length)line(c,'Also close: '+r.alternatives.map(x=>x.subject+'/'+x.predicate).join(', '),'mut');
  const d=el('details');d.appendChild(el('summary','','Raw JSON'));d.appendChild(el('pre','',JSON.stringify(r,null,2)));c.appendChild(d);
}
async function ask(q,d){
  const u='/api/ask?q='+encodeURIComponent(q)+(d?'&as_of='+encodeURIComponent(d):'');
  try{const res=await fetch(u);render(await res.json())}catch(e){render({error:'Could not reach the server.'})}
}
const TL={min:null};
function addDays(d,n){const x=new Date(d+'T00:00:00Z');x.setUTCDate(x.getUTCDate()+n);return x.toISOString().slice(0,10)}
let liveN=0;
async function showLive(key,d){
  const n=++liveN,c=$('live');
  let a;try{a=await (await fetch('/api/answer?key='+encodeURIComponent(key)+'&as_of='+d)).json()}catch(e){return}
  if(n!==liveN)return;  /* a newer drag already replaced this one */
  c.textContent='';
  const t=a.status==='unknown'?'Nothing in force on '+d:a.status==='unresolved'?'Unresolved on '+d+': equal-authority sources disagree':'In force on '+d+': '+a.value;
  c.appendChild(el('div','big '+(a.status==='unresolved'?'warn':'ok'),t));
  const src=a.source||(a.sources||[]).join(', ');const why=a.status==='resolved'?a.reason+' (from '+src+')':a.status==='agreed'?'from '+src:'';
  if(why)c.appendChild(el('div','mut',why));
  (a.overruled||[]).forEach(o=>c.appendChild(el('div','mut','overruled: '+o.value+' ('+o.rev+', authority '+o.authority+')')));
  (a.candidates||[]).forEach(o=>c.appendChild(el('div','mut','candidate: '+o.value+' ('+o.rev+', authority '+o.authority+')')));
}
function showTl(){const d=addDays(TL.min,+$('slider').value);$('dlabel').textContent=d;showLive($('key').value,d);$('tl').src='/api/timeline.svg?key='+encodeURIComponent($('key').value)+'&as_of='+d}
async function loadKey(){const r=await (await fetch('/api/timeline.json?key='+encodeURIComponent($('key').value))).json();TL.min=r.min;const s=$('slider');s.max=r.days;s.value=r.start;showTl()}
fetch('/api/keys').then(r=>r.json()).then(list=>{const sel=$('key');list.forEach(k=>{const o=el('option','',k.subject+' / '+k.predicate);o.value=k.key;sel.appendChild(o)});
  if(list.some(k=>k.key==='final_inspection.sampling'))sel.value='final_inspection.sampling';if(list.length)loadKey()});
$('key').addEventListener('change',loadKey);$('slider').addEventListener('input',showTl);
$('f').addEventListener('submit',e=>{e.preventDefault();ask($('q').value.trim(),$('d').value)});
fetch('/api/examples').then(r=>r.json()).then(list=>{list.forEach(x=>{
  const b=el('button','',x.q+(x.as_of?'  ['+x.as_of+']':''));b.type='button';
  b.onclick=()=>{$('q').value=x.q;$('d').value=x.as_of||'';ask(x.q,x.as_of||'')};$('ex').appendChild(b)})});
</script></main></body></html>
"""

_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        db = os.environ.get("SUPERSEDE_DB", str(DEFAULT_DB))
        if not os.path.exists(db):
            raise SystemExit(f"store not found: {db}")
        _store = Store(db, read_only=True)
    return _store


class Handler(BaseHTTPRequestHandler):
    server_version = "SupersedeDemo"

    def _send(self, code: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/":
            csp = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                   "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8", {"Content-Security-Policy": csp})
        elif url.path == "/favicon.ico":  # browsers ask for it; there is none, and a 404 only clutters the console
            self._send(204, b"", "image/x-icon")
        elif url.path == "/healthz":
            self._send(200, b"ok", "text/plain; charset=utf-8")
        elif url.path == "/api/examples":
            self._json(200, EXAMPLES)
        elif url.path == "/api/keys":
            self._json(200, [{"key": f"{t['subject']}.{t['predicate']}", **t} for t in get_store().topics()])
        elif url.path in ("/api/timeline.json", "/api/timeline.svg"):
            qs = parse_qs(url.query)
            key = (qs.get("key", [""])[0]).strip()
            if not KEY.match(key) or len(key) > 120:
                return self._json(400, {"error": "key must look like subject.predicate"})
            subject, predicate = key.split(".", 1)
            if url.path.endswith(".json"):
                today = dt.date.today()
                days = [d for f in get_store().timeline(subject, predicate) for d in (f["starts"], f["ends"])
                        if d and dt.date.fromisoformat(d) <= today.replace(year=today.year + 1)]
                lo = dt.date.fromisoformat(min(days)) if days else today
                hi = dt.date.fromisoformat(max(days)) if days else today
                lo, hi = lo - dt.timedelta(days=30), hi + dt.timedelta(days=120)
                mid = sorted({dt.date.fromisoformat(d) for d in days})
                start = ((mid[1] if len(mid) > 1 else mid[0] if mid else lo) - lo).days + 30
                return self._json(200, {"min": lo.isoformat(), "days": (hi - lo).days, "start": min(start, (hi - lo).days)})
            as_of = (qs.get("as_of", [""])[0]).strip() or None
            if as_of is not None and (not DATE.match(as_of) or Store._day(as_of) is None):
                return self._json(400, {"error": "as_of must be a date like 2025-07-01"})
            svg = timeline.render_svg(get_store(), subject, predicate, as_of)
            self._send(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8",
                       {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})
        elif url.path == "/api/answer":
            qs = parse_qs(url.query)
            key = (qs.get("key", [""])[0]).strip()
            as_of = (qs.get("as_of", [""])[0]).strip() or None
            if not KEY.match(key) or len(key) > 120:
                return self._json(400, {"error": "key must look like subject.predicate"})
            if as_of is not None and (not DATE.match(as_of) or Store._day(as_of) is None):
                return self._json(400, {"error": "as_of must be a date like 2025-07-01"})
            subject, predicate = key.split(".", 1)
            self._json(200, get_store().answer(subject, predicate, as_of=as_of))
        elif url.path == "/api/ask":
            qs = parse_qs(url.query)
            q = (qs.get("q", [""])[0]).strip()
            as_of = (qs.get("as_of", [""])[0]).strip() or None
            if not q or len(q) > MAX_QUESTION:
                return self._json(400, {"error": f"the question must be 1 to {MAX_QUESTION} characters"})
            if as_of is not None and not DATE.match(as_of):
                return self._json(400, {"error": "as_of must be a date like 2025-07-01"})
            try:
                self._json(200, get_store().ask(q, as_of=as_of))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:  # one short line per request, no query text (questions are not logged)
        sys.stderr.write(f"{self.address_string()} {self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ''}\n")


def make_server(port: int, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    get_store()  # fail at startup if the store is missing, and open it once
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    port = int(os.environ.get("PORT", "7860"))
    srv = make_server(port)
    print(f"Supersede demo on http://0.0.0.0:{port} (read-only store: {os.environ.get('SUPERSEDE_DB', DEFAULT_DB)})")
    try:
        srv.serve_forever()
    finally:
        get_store().close()


if __name__ == "__main__":
    main()
