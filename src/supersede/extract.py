"""Extract facts from UNANNOTATED text with a language model, then hand them to a human.

Free-form extraction would invent facts and corrupt the graph, so this is deliberately constrained:

* **Fixed vocabulary.** The model may only use keys from a vocabulary you supply
  (``{"packaging.units_per_box": "how many parts go in one box", ...}``). It maps text onto your
  schema instead of inventing names.
* **Evidence check.** Every fact must carry a quote from the document, and the quote and the value
  must both really appear in the text (whitespace, case and quote style ignored). Anything else is
  rejected, with the reason, and is never written.
* **Human review.** The result is an annotated copy of each document with an "Extracted facts"
  section of ``{{key = value}}`` lines. Nothing touches a store: you review the copy and load it
  with ``python -m supersede.ingest``, which is deterministic.

The default install stays offline. This module needs the optional ``anthropic`` package
(``pip install -e ".[llm]"``) and ``ANTHROPIC_API_KEY`` in the environment, and it sends the
document text to the API. Do not run it on confidential documents unless that is acceptable.

Usage:
    python -m supersede.extract RAW_DIR --vocabulary vocabulary.json --out REVIEW_DIR [--model M]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ingest import parse, split_document

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_VALUE_CHARS = 120
TOOL_NAME = "record_facts"

SYSTEM = (
    "You extract facts from a quality-management document into a FIXED vocabulary of keys.\n"
    "Rules:\n"
    "- Use only keys from the vocabulary. If a statement fits no key, leave it out.\n"
    "- Extract a fact only if the document states it as a requirement or a current fact.\n"
    "- Ignore anything historical ('previously', 'used to', 'revision 1 allowed'), anything "
    "rejected or only considered, hypotheticals, and reports of mistakes.\n"
    "- 'value' must be copied exactly as written in the document: a short phrase, no extra words, "
    "no unit conversion, no rewording.\n"
    "- 'evidence' must be the shortest sentence or clause copied verbatim from the document that "
    "states the fact, and it must contain the value.\n"
    "- If you are not sure, omit the fact. An empty list is a valid answer.\n"
    "- Always answer by calling the record_facts tool exactly once, even when there are no facts."
)


@dataclass(frozen=True)
class ExtractedFact:
    subject: str
    predicate: str
    value: str
    evidence: str

    @property
    def key(self) -> str:
        return f"{self.subject}.{self.predicate}"


@dataclass(frozen=True)
class Rejected:
    key: str
    value: str
    reason: str


@dataclass
class Extraction:
    facts: list[ExtractedFact] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)


def load_vocabulary(path: str | os.PathLike) -> dict[str, str]:
    """Read ``{"subject.predicate": "description"}`` and validate the keys."""
    vocab = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(vocab, dict) or not vocab:
        raise ValueError(f"{path}: the vocabulary must be a non-empty JSON object")
    for key in vocab:
        if not re.fullmatch(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", key):
            raise ValueError(f"{path}: bad key {key!r}; use 'subject.predicate'")
    return vocab


def _norm(text: str) -> str:
    """Normalise for the evidence check: NFKC, straight quotes and dashes, collapsed whitespace, lower case."""
    text = unicodedata.normalize("NFKC", text)
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-"), ("‑", "-")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().casefold()


def validate(raw_facts: list[dict[str, Any]], text: str, vocabulary: dict[str, str]) -> Extraction:
    """Apply the guard rails to what the model returned. Pure and deterministic."""
    out = Extraction()
    body = _norm(text)
    seen: set[tuple[str, str]] = set()
    for item in raw_facts:
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        evidence = str(item.get("evidence", "")).strip()

        def reject(reason: str) -> None:
            out.rejected.append(Rejected(key, value, reason))

        if key not in vocabulary:
            reject("key is not in the vocabulary")
        elif not value or len(value) > MAX_VALUE_CHARS or "{{" in value or "}}" in value or "\n" in value:
            reject("value is empty, too long, multi-line or contains braces")
        elif not evidence or _norm(evidence) not in body:
            reject("evidence is not a verbatim quote from the document")
        elif _norm(value) not in _norm(evidence):
            reject("value does not appear in the evidence quote")
        elif (key, _norm(value)) in seen:
            reject("duplicate")
        else:
            seen.add((key, _norm(value)))
            subject, predicate = key.split(".", 1)
            out.facts.append(ExtractedFact(subject, predicate, value, evidence))
    return out


def _tool(vocabulary: dict[str, str]) -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": "Record the facts found in the document, using only vocabulary keys.",
        "input_schema": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "enum": sorted(vocabulary)},
                            "value": {"type": "string"},
                            "evidence": {"type": "string"},
                        },
                        "required": ["key", "value", "evidence"],
                    },
                }
            },
            "required": ["facts"],
        },
    }


def _client():
    try:
        import anthropic
    except ImportError:
        raise RuntimeError('extraction needs the optional SDK: pip install -e ".[llm]"') from None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("extraction needs ANTHROPIC_API_KEY in the environment (it is never stored)")
    return anthropic.Anthropic()


def extract_facts(text: str, vocabulary: dict[str, str], client: Any = None, model: str = DEFAULT_MODEL) -> Extraction:
    """Ask the model for facts, then keep only those that pass `validate`.

    `client` is anything with ``messages.create`` like the Anthropic SDK; tests pass a fake.
    """
    client = client or _client()
    listing = "\n".join(f"- {k}: {d}" for k, d in sorted(vocabulary.items()))
    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM,
        tools=[_tool(vocabulary)],  # a forced tool_choice is not supported by every model, so it is not used
        messages=[{"role": "user", "content": f"Vocabulary:\n{listing}\n\nDocument:\n<document>\n{text}\n</document>"}],
    )
    raw: list[dict[str, Any]] = []
    called = False
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", TOOL_NAME) == TOOL_NAME:
            called = True
            raw.extend(block.input.get("facts", []))
    if not called:  # an answer in plain text must not look like "no facts"
        raise RuntimeError(f"the model did not call {TOOL_NAME}; nothing was extracted")
    return validate(raw, text, vocabulary)


def annotate(document: str, extraction: Extraction, source: str = "<text>") -> str:
    """Append an 'Extracted facts' review section of ``{{key = value}}`` lines to the document."""
    header, body = split_document(document, source)
    lines = [
        "",
        "## Extracted facts (automatic; review before loading)",
        "",
        "Each line was extracted by a language model and checked against the text above. Delete or "
        "correct any that are wrong, then load this file with `python -m supersede.ingest`.",
        "",
    ]
    for f in extraction.facts:
        quote = f.evidence.replace("\n", " ").replace("{{", "{ {").replace("}}", "} }")
        lines.append(f"- {{{{{f.key} = {f.value}}}}}   evidence: \"{quote}\"")
    if not extraction.facts:
        lines.append("_No facts matched the vocabulary._")
    return header + body.rstrip("\n") + "\n" + "\n".join(lines) + "\n"


def extract_directory(raw_dir: str | os.PathLike, vocabulary: dict[str, str], out_dir: str | os.PathLike,
                      client: Any = None, model: str = DEFAULT_MODEL) -> dict[str, Extraction]:
    """Write a reviewable annotated copy of every ``*.md`` in `raw_dir` into `out_dir` (must not exist)."""
    files = sorted(Path(raw_dir).glob("*.md"))
    if not files:
        raise ValueError(f"no *.md documents found in {raw_dir}")
    if Path(out_dir).exists():
        raise ValueError(f"{out_dir} already exists; pass a new folder")
    client = client or _client()
    results: dict[str, Extraction] = {}
    for p in files:
        text = p.read_text(encoding="utf-8")
        parse(text, p.name)  # fail early on a bad header, before spending an API call
        _, body = split_document(text, p.name)
        results[p.name] = extract_facts(body, vocabulary, client, model)
    Path(out_dir).mkdir(parents=True)
    for p in files:
        (Path(out_dir) / p.name).write_text(annotate(p.read_text(encoding="utf-8"), results[p.name], p.name),
                                            encoding="utf-8")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract facts from unannotated Markdown into a reviewable copy.")
    ap.add_argument("raw_dir", help="folder with one *.md per document revision (header + plain prose)")
    ap.add_argument("--vocabulary", required=True, help='JSON file {"subject.predicate": "description"}')
    ap.add_argument("--out", required=True, help="new folder for the annotated copies to review")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    try:
        results = extract_directory(args.raw_dir, load_vocabulary(args.vocabulary), args.out, model=args.model)
    except (RuntimeError, ValueError) as exc:
        ap.error(str(exc))
    for name, r in results.items():
        print(f"{name}: {len(r.facts)} fact(s), {len(r.rejected)} rejected")
        for rej in r.rejected:
            print(f"    rejected {rej.key} = {rej.value!r}: {rej.reason}")
    print(f"\nReview the files in {args.out}, then: python -m supersede.ingest {args.out} --db STORE.relate")


if __name__ == "__main__":
    main()
