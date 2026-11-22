import http.client
import json
import pathlib
import sys
import threading
import xml.etree.ElementTree as ET

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import app  # noqa: E402
import timeline  # noqa: E402
from supersede.store import Store  # noqa: E402

STORE = ROOT / "examples" / "store" / "supersede-demo.relate"
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def committed():
    s = Store(str(STORE), read_only=True)
    yield s
    s.close()


def svg(store, key, day):
    subject, predicate = key.split(".", 1)
    return ET.fromstring(timeline.render_svg(store, subject, predicate, day))


def rects(root, stroke):
    return [r for r in root.iter("{http://www.w3.org/2000/svg}rect") if r.get("stroke") == stroke]


def headline(root):
    """The big answer under the chart (the only 22 px text)."""
    return next("".join(t.itertext()) for t in root.iter("{http://www.w3.org/2000/svg}text") if t.get("font-size") == "22")


def texts(root):
    return " | ".join("".join(t.itertext()) for t in root.iter("{http://www.w3.org/2000/svg}text"))


# -- the data layer ------------------------------------------------------------------------------
def test_timeline_gives_each_fact_its_start_and_end(committed):
    t = {f["rev"]: (f["starts"], f["ends"], f["superseded_by"]) for f in committed.timeline("final_inspection", "sampling")}
    assert t["QP-07-r1"] == ("2024-01-10", "2025-03-01", ["QP-07-r2"])
    assert t["QP-07-r3"] == ("2025-11-01", None, [])
    assert t["WI-12-r1"] == ("2025-06-01", None, [])


def test_timeline_reports_unusable_dates_as_none(committed):
    t = {f["rev"]: f for f in committed.timeline("furnace_loading", "preheat_minutes")}
    assert t["WI-31-r2"]["starts"] is None            # the blank effective date
    assert t["WI-31-r1"]["ends"] is None              # an undated successor cannot end its predecessor


def test_topics_lists_the_searchable_keys(committed):
    topics = committed.topics()
    assert len(topics) == 19 and {"subject", "predicate", "description"} <= set(topics[0])
    assert Store().topics() == []                      # a store without topics is not an error


# -- the picture ---------------------------------------------------------------------------------
def test_frame_in_the_middle_of_history_shows_the_winner_the_overruled_and_the_stale_tag(committed):
    root = svg(committed, "final_inspection.sampling", "2025-07-01")
    gold = [g for g in root.iter("{http://www.w3.org/2000/svg}g")
            if any(r.get("stroke") == "#f59e0b" for r in g.findall("s:rect", NS))]
    assert len(gold) == 1 and "QP-07-r2" in "".join(gold[0].find("s:title", NS).itertext())
    t = texts(root)
    assert "AQL 1.0" in t and "2025-07-01" in t
    assert "overruled: 100% inspection (WI-12-r1)" in t and "stale source" in t


def test_frames_change_with_the_date(committed):
    early = svg(committed, "final_inspection.sampling", "2024-06-01")
    late = svg(committed, "final_inspection.sampling", "2026-03-01")
    assert headline(early) == "100% inspection" and headline(late) == "AQL 0.65"


def test_a_tie_outlines_only_the_equal_authority_sources(committed):
    root = svg(committed, "supplier_audit.frequency", "2024-12-01")
    assert len(rects(root, "#dc2626")) == 2           # the two authority-4 documents, not the authority-3 procedure
    t = texts(root)
    assert "unresolved" in t and "QP-18-r2" not in t.split("unresolved", 1)[1]


def test_date_problems_are_drawn_not_hidden(committed):
    t = texts(svg(committed, "fastening.head_bolt_torque", "2025-10-01"))
    assert "dated 2052-01-15" in t and "date problem" in t and "48 Nm" in t
    assert "no effective date" in texts(svg(committed, "furnace_loading.preheat_minutes", "2025-01-01"))


def test_nothing_in_force_is_said_plainly(committed):
    assert "nothing in force" in texts(svg(committed, "final_inspection.sampling", "2023-01-01"))


def test_today_view_without_a_date(committed):
    root = svg(committed, "final_inspection.sampling", None)
    assert "today (" in texts(root) and "AQL 0.65" in texts(root)


def test_hostile_text_cannot_break_out_of_the_svg():
    s = Store()
    s.add_document('D<"&>', 'd', 3)
    r = s.add_revision('D<"&>', 1, "2025-01-01")
    s.assert_fact(r, "F1", "k", "p", '<script>alert(1)</script> & "x"')
    raw = timeline.render_svg(s, "k", "p", "2025-06-01")
    ET.fromstring(raw)                                 # still well-formed
    assert "<script>" not in raw and "&lt;script&gt;" in raw


# -- over HTTP -----------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def server():
    srv = app.make_server(0, host="127.0.0.1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    app.get_store().close()
    app._store = None


def get(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request("GET", path)
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_timeline_endpoints(server):
    status, h, body = get(server, "/api/timeline.svg?key=final_inspection.sampling&as_of=2025-07-01")
    assert status == 200 and h["Content-Type"].startswith("image/svg+xml")
    assert "default-src 'none'" in h["Content-Security-Policy"]
    ET.fromstring(body)
    j = json.loads(get(server, "/api/timeline.json?key=final_inspection.sampling")[2])
    assert set(j) == {"min", "days", "start"} and 0 <= j["start"] <= j["days"]
    keys = json.loads(get(server, "/api/keys")[2])
    assert len(keys) == 19 and keys[0]["key"] == f"{keys[0]['subject']}.{keys[0]['predicate']}"


@pytest.mark.parametrize("path", [
    "/api/timeline.svg?key=a;b", "/api/timeline.svg", "/api/timeline.json?key=nodot",
    "/api/timeline.svg?key=final_inspection.sampling&as_of=2025-13-40",
    "/api/timeline.svg?key=final_inspection.sampling&as_of=yesterday",
])
def test_bad_timeline_requests_are_400_not_crashes(server, path):
    assert get(server, path)[0] == 400


def test_page_embeds_the_timeline_without_injecting_html(server):
    _, h, body = get(server, "/")
    assert b"Watch the answer change over time" in body and b'id="slider"' in body
    assert "img-src 'self'" in h["Content-Security-Policy"] and b"innerHTML" not in body


# -- the animated picture in the README ------------------------------------------------------------

ANIMATED = ROOT / "docs" / "img" / "timeline-final_inspection-sampling-animated.svg"
DATES = ["2024-06-01", "2025-07-01", "2026-03-01"]


def animated(store, dates=DATES, still=1):
    return timeline.render_animated(store, "final_inspection", "sampling", dates, still=still)


def test_animated_picture_has_one_frame_per_date_and_each_says_its_own_answer(committed):
    root = ET.fromstring(animated(committed))
    frames = [g for g in root if g.tag.endswith("}g")]
    assert len(frames) == len(DATES)
    said = ["".join(t.itertext()) for g in frames for t in g.iter("{http://www.w3.org/2000/svg}text")
            if t.get("font-size") == "22"]
    assert said == ["100% inspection", "AQL 1.0", "AQL 0.65"]  # same as the static frames: nothing is invented


def test_animated_picture_shows_only_the_still_frame_when_animation_is_off(committed):
    root = ET.fromstring(animated(committed, still=2))
    assert [g.get("opacity") for g in root if g.tag.endswith("}g")] == ["0", "0", "1"]
    assert "prefers-reduced-motion" in animated(committed)


def test_animated_picture_uses_no_script_and_no_external_reference(committed):
    text = animated(committed).lower()
    assert "<script" not in text and "href" not in text and "onload" not in text


def test_animated_picture_rejects_bad_arguments(committed):
    with pytest.raises(ValueError):
        timeline.render_animated(committed, "final_inspection", "sampling", [])
    with pytest.raises(ValueError):
        timeline.render_animated(committed, "final_inspection", "sampling", DATES, still=3)


def test_committed_animated_picture_matches_the_store(committed):
    assert ANIMATED.read_text(encoding="utf-8") == animated(committed)


# -- the live answer line next to the slider ---------------------------------------------------------


@pytest.mark.parametrize("day, status, value", [
    ("2024-06-01", "agreed", "100% inspection"),
    ("2025-07-01", "resolved", "AQL 1.0"),
    ("2026-03-01", "resolved", "AQL 0.65"),
])
def test_answer_endpoint_gives_the_value_in_force_on_that_day(server, day, status, value):
    code, h, body = get(server, f"/api/answer?key=final_inspection.sampling&as_of={day}")
    got = json.loads(body)
    assert code == 200 and h["Content-Type"].startswith("application/json")
    assert (got["status"], got["value"]) == (status, value)


def test_answer_endpoint_reports_what_it_overruled(server):
    got = json.loads(get(server, "/api/answer?key=final_inspection.sampling&as_of=2025-07-01")[2])
    assert [o["rev"] for o in got["overruled"]] == ["WI-12-r1"]


@pytest.mark.parametrize("path", [
    "/api/answer", "/api/answer?key=nodot", "/api/answer?key=a;b",
    "/api/answer?key=final_inspection.sampling&as_of=2025-13-40",
    "/api/answer?key=final_inspection.sampling&as_of=yesterday",
])
def test_bad_answer_requests_are_400_not_crashes(server, path):
    assert get(server, path)[0] == 400


def test_page_has_the_live_line_and_writes_it_as_text_only(server):
    page = get(server, "/")[2].decode("utf-8")
    assert 'id="live"' in page and "showLive" in page
    live_fn = page[page.index("async function showLive"):page.index("function showTl")]
    assert "innerHTML" not in live_fn  # server values are put in with textContent only


def test_agreed_answers_name_their_sources_and_the_browser_gets_no_favicon_error(server):
    page = get(server, "/")[2].decode("utf-8")
    assert "a.sources" in page  # an agreed answer has `sources`, not `source`: no 'from undefined'
    assert get(server, "/favicon.ico")[0] == 204
