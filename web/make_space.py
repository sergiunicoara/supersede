"""Assemble a folder that can be pushed as-is to a Hugging Face Space (Docker SDK).

    python web/make_space.py ../supersede-space

Copies the Dockerfile, the package, the web app, the committed demo store and the licence, and writes
the Space README with its front matter. It never contains keys or tokens. Then, from that folder:

    git init && git add . && git commit -m "Supersede demo"
    git remote add space https://huggingface.co/spaces/<your-user>/supersede
    git push space main
"""
from __future__ import annotations

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

SPACE_README = """---
title: Supersede
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Agent memory that knows which fact is in force, and why
---

# Supersede (demo)

Ask plain-language questions about a fictional set of quality documents. Supersede answers with the
value currently in force, the reason, what it overruled, stale sources and date problems.
Read-only, fictional data, no accounts. Built on Relate by Neo4j.

Source code, tests and write-up: https://github.com/sergiunicoara/supersede
"""


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = pathlib.Path(sys.argv[1]).resolve()
    if out.exists():
        sys.exit(f"{out} already exists; pass a new folder")
    out.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info")
    for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "LICENSE"):
        shutil.copy2(ROOT / name, out / name)
    shutil.copytree(ROOT / "src", out / "src", ignore=ignore)
    shutil.copytree(ROOT / "web", out / "web", ignore=ignore)
    shutil.copytree(ROOT / "examples" / "store", out / "examples" / "store")
    (out / "README.md").write_text(SPACE_README, encoding="utf-8")
    print(f"Space folder ready: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
