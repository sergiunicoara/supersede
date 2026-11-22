# Judge guide: 3 minutes

Supersede answers "what is in force, and why?" from a graph of documents, revisions and authority on Relate. All data
here is fictional except the clearly marked real regulation text. Everything below runs offline, no key needed.

## 0. Nothing to install: the live page (30 seconds)

https://supersede-demo.onrender.com (a free instance: if it is asleep, the first load takes about a minute).
Pick `final_inspection / sampling` and **drag the date slider**: the gold outline moves between revisions and the
answer changes. Then type a plain-language question, for example *How often do we calibrate a gauge?*

## Install once

```bash
python -m venv .venv && . .venv/bin/activate    # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## 1. See the difference (30 seconds)

```bash
python examples/demo_session.py
```

A naive "newest fact wins" memory against Supersede on the same documents. **Proves:** a newer shift note does not
override a higher-authority customer requirement, and two equal-authority sources are reported as `unresolved`
instead of guessed.

## 2. See it measured (1 minute)

```bash
python eval/run_eval.py
```

Deterministic and offline. **Proves:** 19/19 revision questions against 9/19 for newest-date-wins; two ablations show
what each part of the graph (supersession, authority) adds; 13/13 date questions; 23/23 plain-language questions
through hybrid retrieval (Relate full-text plus vector index). These are cases I designed, and
[docs/EVIDENCE.md](docs/EVIDENCE.md) lists every number with its blind result and its limits.

## 3. Ask it in plain language, at a past date (30 seconds)

```bash
python examples/ask.py "What sampling rule applied?" --as-of 2025-07-01
```

**Proves:** retrieval finds the topic (Relate's full-text and vector indexes), then the graph, not the text match,
decides the value, and it gives the reason and what it overruled.

## Where to look next

| If you want to check... | Look at |
|---|---|
| How Relate is used (Cypher, both indexes, read-only store) | README, "How it uses Relate"; `src/supersede/store.py` |
| The data itself | `examples/store/supersede-demo.relate/` (committed), README "Where the data lives" |
| Real text, not fictional | [docs/EVIDENCE.md](docs/EVIDENCE.md) sections 4 and 5 (eCFR regulations, FDA guidance) |
| An agent using it | `docs/agent_transcript.md` (a real Claude agent over MCP) |
| What it does **not** do | README "Limits" and EVIDENCE section 7: mostly fictional data, strings not meaning, hashing embedder misses true synonyms |
| Tests | `python -m pytest -q` (192 tests, 188 on a plain install; CI runs Linux, macOS, Windows, Python 3.10 to 3.13) |
