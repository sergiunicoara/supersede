"""Draw what was in force over time for one question, as a standalone SVG (no JavaScript, light background).

Every document that states a value for (subject, predicate) is a lane; each of its revisions is a bar from the day it
takes effect to the day a newer revision replaces it. For a chosen date the bars in force are solid, the others are
faded, the value that wins gets a gold outline (an unresolved tie gets red dashes), and the answer is written under
the chart. Orange tags mark revisions written from a source that was since replaced; red tags mark date problems.
The picture is computed from the real store with the same functions the tools use, so it cannot disagree with them.

    python web/timeline.py --key final_inspection.sampling --dates 2024-06-01,2025-07-01,2026-03-01 --out docs/img
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from supersede.store import Store  # noqa: E402

DEFAULT_DB = ROOT / "examples" / "store" / "supersede-demo.relate"
AUTH_COLOR = {4: "#7c3aed", 3: "#2563eb", 2: "#0d9488", 1: "#64748b"}
AUTH_NAME = {4: "customer / regulation", 3: "controlled procedure", 2: "work instruction", 1: "shift note / email"}
W, ML, MR, MT, LANE, BAR = 920, 150, 24, 96, 56, 30
FONT = "Segoe UI, Helvetica, Arial, sans-serif"


def _day(text) -> dt.date | None:
    return Store._day(text)


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: max(n - 1, 1)] + "…"


def render_svg(store: Store, subject: str, predicate: str, as_of: str | None = None) -> str:
    """The timeline for (subject, predicate) as an SVG string. `as_of` None draws today's state."""
    facts = store.timeline(subject, predicate)
    warn = {w["revision"]: w for w in store.date_warnings()}
    stale = {x["revision"]: x for x in store.stale_derivations()}
    today = dt.date.today()
    future = {f["rev"] for f in facts if f["starts"] and _day(f["starts"]) > today.replace(year=today.year + 1)}
    in_force = store.in_force(as_of) if as_of else set(store.current_revisions())
    ans = store.answer(subject, predicate, as_of=as_of) if as_of else store.answer(subject, predicate)
    win = {ans["source"]} if "source" in ans else set(ans.get("sources", []))
    cands = ans.get("candidates", [])
    top = max((c["authority"] for c in cands), default=None)
    tied = [c for c in cands if c["authority"] == top]  # lower-authority candidates are overruled, not tied
    tie = {c["rev"] for c in tied}

    marked = _day(as_of) if as_of else today
    dated = [_day(f["starts"]) for f in facts if f["starts"] and f["rev"] not in future]
    dated += [_day(f["ends"]) for f in facts if f["ends"] and f["rev"] not in future]
    dated.append(marked)
    d0, d1 = min(dated) - dt.timedelta(days=75), max(dated) + dt.timedelta(days=110)
    span = max((d1 - d0).days, 1)
    right = W - MR

    def x(d: dt.date) -> float:
        return ML + (d - d0).days / span * (right - ML)

    docs = sorted({f["doc"] for f in facts}, key=lambda d: (-max(f["authority"] for f in facts if f["doc"] == d), d))
    height = MT + LANE * len(docs) + 104
    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" '
        f'font-family="{FONT}" role="img" aria-label="Timeline of {escape(subject)} / {escape(predicate)}">',
        f'<rect width="{W}" height="{height}" fill="#ffffff"/>',
        f'<text x="20" y="30" font-size="18" font-weight="700" fill="#0f172a">{escape(subject)} / {escape(predicate)}</text>',
        f'<text x="20" y="50" font-size="12" fill="#475569">Each bar is a revision, from the day it takes effect to the day a newer one replaces it. '
        f'Colour = document authority.</text>',
    ]
    # axis
    for year in range(d0.year, d1.year + 2):
        for month in (1, 7) if span > 900 else (1, 4, 7, 10):
            d = dt.date(year, month, 1)
            if d0 <= d <= d1:
                label = str(year) if month == 1 else d.strftime("%b %Y")
                o.append(f'<line x1="{x(d):.1f}" y1="{MT - 14}" x2="{x(d):.1f}" y2="{height - 104}" stroke="#e2e8f0"/>')
                o.append(f'<text x="{x(d) + 3:.1f}" y="{MT - 3}" font-size="11" fill="#64748b">{label}</text>')
    # lanes and bars
    for i, doc in enumerate(docs):
        y = MT + i * LANE
        auth = max(f["authority"] for f in facts if f["doc"] == doc)
        o.append(f'<text x="14" y="{y + 20}" font-size="13" font-weight="600" fill="#0f172a">{escape(doc)}</text>')
        o.append(f'<circle cx="20" cy="{y + 34}" r="5" fill="{AUTH_COLOR.get(auth, "#64748b")}"/>')
        o.append(f'<text x="30" y="{y + 38}" font-size="10" fill="#475569">authority {auth}</text>')
        for f in (g for g in facts if g["doc"] == doc):
            col = AUTH_COLOR.get(f["authority"], "#64748b")
            active = f["rev"] in in_force
            if f["rev"] in future or not f["starts"]:
                bx, bw = (right - 74, 70) if f["rev"] in future else (ML + 4, 70)
                o.append(f'<g opacity="{1 if active else 0.55}"><rect x="{bx}" y="{y + 6}" width="{bw}" height="{BAR}" rx="6" '
                         f'fill="#fee2e2" stroke="#dc2626" stroke-dasharray="4 3"/>'
                         f'<text x="{bx + 5}" y="{y + 26}" font-size="10" fill="#991b1b">{escape(_short(f["value"], 10))}</text>'
                         f'<title>{escape(f["rev"])}: {escape(f["value"])} (date problem)</title></g>')
                note = ("dated " + f["starts"]) if f["rev"] in future else "no effective date"
                o.append(f'<text x="{bx}" y="{y + 52}" font-size="10" fill="#dc2626">! {escape(note)}</text>')
                continue
            sd = _day(f["starts"])
            ed = _day(f["ends"]) if f["ends"] else d1
            bx, bw = x(sd), max(x(ed) - x(sd), 6)
            stroke, sw, dash = ("#f59e0b", 3, "") if f["rev"] in win else (("#dc2626", 3, "6 4") if f["rev"] in tie else ("none", 0, ""))
            o.append(
                f'<g opacity="{1 if active else 0.28}"><rect x="{bx:.1f}" y="{y + 6}" width="{bw:.1f}" height="{BAR}" rx="6" '
                f'fill="{col}" stroke="{stroke}" stroke-width="{sw}"' + (f' stroke-dasharray="{dash}"' if dash else "") + '/>'
                f'<text x="{bx + 7:.1f}" y="{y + 26}" font-size="12" font-weight="600" fill="#ffffff">'
                f'{escape(_short(f["value"], int((bw - 10) / 6.6)))}</text>'
                f'<title>{escape(f["rev"])}: {escape(f["value"])} (authority {f["authority"]}), effective {escape(f["starts"])}'
                + (f", replaced {escape(f['ends'])}" if f["ends"] else "") + "</title></g>")
            o.append(f'<text x="{bx + 2:.1f}" y="{y + 50}" font-size="10" fill="#475569">{escape(f["rev"].rsplit("-", 1)[1])}</text>')
            tag_x = bx + 26
            if f["rev"] in stale and active:
                o.append(f'<text x="{tag_x:.1f}" y="{y + 50}" font-size="10" font-weight="700" fill="#c2410c">⚠ stale source</text>')
                tag_x += 78
            if f["rev"] in warn and warn[f["rev"]]["issue"] != "future_date":
                o.append(f'<text x="{tag_x:.1f}" y="{y + 50}" font-size="10" font-weight="700" fill="#dc2626">! date problem</text>')
    # the chosen date
    mx = x(marked)
    label = as_of if as_of else f"today ({today.isoformat()})"
    o.append(f'<line x1="{mx:.1f}" y1="{MT - 12}" x2="{mx:.1f}" y2="{MT + LANE * len(docs)}" stroke="#0f172a" stroke-width="2" stroke-dasharray="5 3"/>')
    o.append(f'<rect x="{mx - 52:.1f}" y="{MT - 40}" width="104" height="20" rx="10" fill="#0f172a"/>'
             f'<text x="{mx:.1f}" y="{MT - 26}" font-size="11" font-weight="700" fill="#ffffff" text-anchor="middle">{escape(label)}</text>')
    # the answer
    fy = MT + LANE * len(docs) + 22
    o.append(f'<line x1="14" y1="{fy - 12}" x2="{W - 14}" y2="{fy - 12}" stroke="#cbd5e1"/>')
    st = ans["status"]
    if st in ("resolved", "agreed"):
        who = ans.get("source") or ", ".join(ans["sources"])
        head, col = f'{ans["value"]}', "#166534"
        sub = f"{st} · from {who}" + (f" · {ans['reason']}" if "reason" in ans else "")
    elif st == "unresolved":
        head, col = "unresolved", "#b91c1c"
        sub = "equal-authority sources disagree: " + "; ".join(f'{c["value"]} ({c["rev"]})' for c in tied)
    else:
        head, col, sub = "nothing in force", "#92400e", ans.get("reason", "no fact in force")
    o.append(f'<text x="20" y="{fy + 12}" font-size="22" font-weight="700" fill="{col}">{escape(_short(head, 44))}</text>')
    o.append(f'<text x="20" y="{fy + 34}" font-size="12" fill="#334155">{escape(_short(sub, 150))}</text>')
    over = [f'{v["value"]} ({v["rev"]})' for v in ans.get("overruled", [])]
    if over:
        o.append(f'<text x="20" y="{fy + 52}" font-size="12" fill="#64748b">overruled: {escape(_short("; ".join(over), 130))}</text>')
    # legend
    lx = W - 14
    for a in (1, 2, 3, 4):
        lx -= 8 + 6.2 * len(AUTH_NAME[a]) + 14
        o.append(f'<rect x="{lx:.1f}" y="{height - 22}" width="10" height="10" rx="2" fill="{AUTH_COLOR[a]}"/>'
                 f'<text x="{lx + 14:.1f}" y="{height - 13}" font-size="10" fill="#475569">{escape(AUTH_NAME[a])}</text>')
    o.append(f'<text x="20" y="{height - 13}" font-size="10" fill="#475569">gold outline = value in force · faded = not in force on this date</text>')
    o.append("</svg>")
    return "\n".join(o)


def render_animated(store: Store, subject: str, predicate: str, dates: list[str], seconds: float = 3.6,
                    still: int = 0) -> str:
    """One SVG that cycles through the frames for `dates` (CSS only, no JavaScript), looping forever.

    Every frame is `render_svg()` for that date, so the animation cannot disagree with the tools. Where CSS
    animation is off (a static renderer, or `prefers-reduced-motion`) only frame number `still` is shown.
    """
    if not dates:
        raise ValueError("need at least one date")
    if not 0 <= still < len(dates):
        raise ValueError("still must index one of the dates")
    frames = [render_svg(store, subject, predicate, d) for d in dates]
    head = frames[0].split(">", 1)[0]  # the opening <svg ...> tag; all frames share the same size
    n = len(frames)
    nl = chr(10)
    css, body = [], []
    for i, frame in enumerate(frames):
        a, b = 100.0 * i / n, 100.0 * (i + 1) / n  # this frame is shown from a% to b% of the cycle
        fade = 1.0  # percent of the cycle spent cross-fading
        stops = [(0.0, 1 if i == 0 else 0)]
        if i > 0:
            stops += [(a - fade, 0), (a, 1)]
        if i < n - 1:
            stops += [(b - fade, 1), (b, 0), (100.0, 0)]
        else:
            stops += [(100.0, 1)]
        css.append(f"@keyframes f{i}{{" + "".join(f"{x:.2f}%{{opacity:{v}}}" for x, v in stops) + "}")
        css.append(f".f{i}{{animation:f{i} {seconds * n:.1f}s linear infinite}}")
        inner = frame.split(">", 1)[1].rsplit("</svg>", 1)[0]
        body.append(f'<g class="f{i}" opacity="{1 if i == still else 0}">{inner}</g>')
    still_css = "".join(f".f{i}{{animation:none;opacity:{1 if i == still else 0}}}" for i in range(n))
    title = escape(f"{subject} / {predicate}: the value in force on {', '.join(dates)}")
    return nl.join([head + ">", f"<title>{title}</title>",
                    "<style>" + nl.join(css) + "@media (prefers-reduced-motion: reduce){" + still_css + "}</style>",
                    *body, "</svg>"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--key", required=True, help="subject.predicate")
    ap.add_argument("--dates", required=True, help="comma-separated YYYY-MM-DD dates (or 'today')")
    ap.add_argument("--out", required=True, help="folder for the SVG files")
    ap.add_argument("--animate", action="store_true", help="write ONE looping animated SVG for all the dates")
    args = ap.parse_args()
    subject, predicate = args.key.split(".", 1)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    store = Store(args.db, read_only=True)
    try:
        if args.animate:
            dates = args.dates.split(",")
            path = out / f"timeline-{subject}-{predicate}-animated.svg"
            path.write_text(render_animated(store, subject, predicate, dates, still=len(dates) // 2), encoding="utf-8")
            print("wrote", path)
            return 0
        for d in args.dates.split(","):
            path = out / f"timeline-{subject}-{predicate}-{d}.svg"
            path.write_text(render_svg(store, subject, predicate, None if d == "today" else d), encoding="utf-8")
            print("wrote", path)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
