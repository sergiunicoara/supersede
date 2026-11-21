import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_demo_session_runs_offline_end_to_end():
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    r = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "demo_session.py")],
        capture_output=True, text=True, timeout=120, env=env,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "'10 years'" in out and "unresolved" in out
    assert "QP-07-r3 replaced QP-07-r2, then QP-07-r1" in out
    assert "Supersede 13/13" in out
    assert "Traceback" not in out + r.stderr


def test_llm_flag_without_key_fails_cleanly():
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    r = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "demo_session.py"), "--llm"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert r.returncode != 0
    assert "ANTHROPIC_API_KEY" in r.stderr
