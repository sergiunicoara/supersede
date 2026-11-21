import http.client
import json
import pathlib
import sys
import threading

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import app  # noqa: E402


@pytest.fixture(scope="module")
def server():
    srv = app.make_server(0, host="127.0.0.1")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    app.get_store().close()
    app._store = None


def get(port, path):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request("GET", path)
    r = c.getresponse()
    body = r.read()
    return r.status, dict(r.getheaders()), body


def test_page_is_served_with_a_strict_content_security_policy(server):
    status, h, body = get(server, "/")
    assert status == 200 and b"Supersede" in body and b"fictional" in body
    assert "default-src 'none'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"
    assert b"innerHTML" not in body  # results are built with textContent, never as HTML


def test_ask_api_returns_the_value_in_force_with_its_reason(server):
    status, h, body = get(server, "/api/ask?q=How+long+must+retained+samples+be+kept%3F")
    r = json.loads(body)
    assert status == 200 and h["Content-Type"].startswith("application/json")
    assert (r["answer"]["value"], r["answer"]["source"]) == ("10 years", "CSR-VEL-01-r2")


def test_ask_api_as_of_and_stale_and_no_match(server):
    r = json.loads(get(server, "/api/ask?q=What+sampling+rule+applied%3F&as_of=2025-07-01")[2])
    assert r["answer"]["value"] == "AQL 1.0" and r["answer"]["as_of"] == "2025-07-01"
    r = json.loads(get(server, "/api/ask?q=Which+form+do+inspectors+fill+in+for+final+inspection+results%3F")[2])
    assert r["stale_sources"][0]["revision"] == "WI-52-r1"
    assert json.loads(get(server, "/api/ask?q=Who+is+the+plant+manager%3F")[2])["status"] == "no_match"


def test_bad_input_is_a_400_not_a_crash(server):
    assert get(server, "/api/ask")[0] == 400
    assert get(server, "/api/ask?q=" + "x" * 301)[0] == 400
    status, _, body = get(server, "/api/ask?q=hello&as_of=2025/07/01")
    assert status == 400 and b"as_of" in body
    assert get(server, "/api/ask?q=hello&as_of=2025-13-40")[0] == 400  # looks like a date but is not one
    assert get(server, "/nope")[0] == 404


def test_hostile_text_is_just_data(server):
    status, _, body = get(server, "/api/ask?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E+%7B%7B+OR+%22+*")
    assert status == 200 and json.loads(body)["status"] in {"no_match", "resolved", "agreed", "unresolved", "unknown"}


def test_examples_and_health(server):
    assert get(server, "/healthz")[2] == b"ok"
    ex = json.loads(get(server, "/api/examples")[2])
    assert len(ex) >= 4 and all("q" in x for x in ex)


def test_concurrent_requests_all_succeed(server):
    results = []

    def one():
        results.append(get(server, "/api/ask?q=How+often+must+we+calibrate+our+gauges%3F")[0])

    threads = [threading.Thread(target=one) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == [200] * 12
