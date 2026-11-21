import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(script, *args, key=False):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run([sys.executable, str(ROOT / "examples" / script), *args],
                          capture_output=True, text=True, timeout=120, env=env)


def test_ask_cli_answers_from_the_committed_store():
    r = run("ask.py", "How long must retained samples be kept?")
    assert r.returncode == 0, r.stderr
    assert "value    : 10 years   from CSR-VEL-01-r2" in r.stdout
    assert "overruled: '3 years' (SN-0914-r1, authority 1)" in r.stdout


def test_ask_cli_as_of_and_stale_source_output():
    r = run("ask.py", "What sampling rule applied?", "--as-of", "2025-07-01")
    assert r.returncode == 0 and "AQL 1.0   from QP-07-r2" in r.stdout and "as of 2025-07-01" in r.stdout
    r = run("ask.py", "Which form do inspectors fill in for final inspection results?")
    assert "STALE    : WI-52-r1 was written from QP-07-r1, replaced by QP-07-r3" in r.stdout


def test_ask_cli_off_topic_and_bad_input():
    assert "no_match" in run("ask.py", "Who is the plant manager?").stdout
    bad = run("ask.py", "How long must retained samples be kept?", "--as-of", "not-a-date")
    assert bad.returncode != 0 and "as_of must be a date" in bad.stderr
    assert run("ask.py", "x", "--db", str(ROOT / "nope.relate")).returncode != 0


def test_agent_demo_without_a_key_fails_cleanly():
    r = run("agent_demo.py")
    assert r.returncode != 0
    assert "ANTHROPIC_API_KEY" in r.stderr or "optional SDK" in r.stderr
