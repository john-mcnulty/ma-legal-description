#!/usr/bin/env python3
"""
rule_inventory.py — gate against losing a guardrail when SKILL.md is split.

    python scripts/rule_inventory.py snapshot --skill <SKILL.md> --out <file.json>
    python scripts/rule_inventory.py verify   --snapshot <file.json> \
        --core <SKILL.md> [--refs <dir-or-file> ...]
    python scripts/rule_inventory.py list     --skill <SKILL.md>

Exit 0 = every rule still reachable where it must be, 1 = a rule was lost
or demoted.

WHY THIS EXISTS
---------------
The robustness of this workflow lives in two places, and they are guarded
very differently.

  * The SCRIPT (legal_desc_fetch.py) holds the earned behaviors — the *DD
    cap fallback, the town-scoped retry, the acquisition-date window, deep
    sampling of a null address, registry_unavailable, the
    extraction_unavailable latch. Twelve regression tests cover it.

  * SKILL.md holds the INTERPRETIVE guardrails — "never report clean title
    from an incomplete check", "a null sample address is missing
    information, not a non-match", "never report a surname-only row as the
    seller's own encumbrance". These are instructions to the model. Not one
    of the twelve tests reads this file. They have no coverage at all.

Splitting SKILL.md into a lean core plus on-demand reference files is a
token win, and it puts exactly the second group at risk — in a specific
way worth naming, because it is this codebase's recurring bug wearing a
new hat.

An on-demand file is loaded only if the model CHOOSES to load it. The
guardrails that matter most fire on rare failure paths: a capped search, a
blank abstract Addr:, a billing 400. Those arrive unannounced, in a run
that looked routine — precisely when nothing prompts a reach for "the
grantor-check reference". The rule is then silently absent, and an absent
guardrail is indistinguishable from a satisfied one. That is missing
information read as a negative answer, applied to the skill file itself.

So this gate enforces the rule that makes the split safe:

    Content may move out only if its ABSENCE IS SELF-ANNOUNCING.

Registry mechanics pass that test — without the ALIS parameter name you
visibly cannot proceed, so you go and fetch it. A conditional guardrail
fails it — without the rule you proceed confidently in the wrong
direction. Hence the two failure modes below are BOTH blocking, and the
second is the one this file was really written for:

    MISSING  — the rule is nowhere in the tree any more.
    DEMOTED  — the rule survives, but only in an on-demand reference file.

A DEMOTED finding is not a warning. It is the failure this gate exists to
catch, and it reports as a block.

ON MATCHING
-----------
The refactor rewords prose; it does not merely relocate it. A gate that
demanded byte-identical text would fire on every honest edit, and a gate
that fires constantly gets bypassed — so matching is done on a normalized
token fingerprint that survives rewording, reformatting and markdown
churn, but does not survive deletion. Anything below the match threshold
is reported for a human to read rather than being quietly resolved.

ON SNAPSHOTS AND CLIENT DATA
----------------------------
A snapshot holds text lifted verbatim out of a SKILL.md. Run against the
PRIVATE working copy, that text carries real client names and addresses
(the guardrail prose is full of the runs that produced it). Snapshots
therefore default to writing outside the repository, are matched by
.gitignore, and are blocked by scripts/scrub_check.py. Never commit one.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------- extraction

# Bias to RECALL, not precision. A missed rule is an unguarded workflow; a
# false positive is one extra line for a human to read once. Anything
# matched here is a CANDIDATE rule, to be confirmed by eye via `list`.
#
# BOTH patterns are case-INSENSITIVE, and that is load-bearing rather than
# lazy. The first draft spelled out the cases it expected — "NEVER" and
# "never", "DO NOT" and "do NOT" and "do not" — and so failed on the one
# case nobody thinks to write down: sentence-initial title case. "Never
# report a surname-only row as the seller's own encumbrance" is a HARD
# guardrail that classified as soft, meaning the gate would have allowed
# it to be demoted to a reference file without comment. A classifier that
# cannot fire looks exactly like one that fired and found nothing, which
# is the failure this whole gate is about.
MARKERS = [
    r"\bnever\b", r"\balways\b",
    r"\bcritical\b", r"\bwarning\b",
    r"\bmust not\b", r"\bmust never\b", r"\bmust\b",
    r"\bdo not\b", r"\bdon't\b",
    r"\bcannot\b", r"\bnot a\b", r"\bnot be\b", r"\brefuse", r"\brefusing\b",
    r"\bunverified\b", r"\bincomplete\b",
    r"\bstop and\b", r"\bstop\b",
    r"\bbefore\b.*\breport", r"\binstead of\b",
    r"\bonly\b", r"\bunless\b",
]
MARKER_RE = re.compile("|".join(MARKERS), re.IGNORECASE)

# Markers that make a sentence a HARD guardrail — one whose absence lets a
# run proceed confidently in the wrong direction. These are the ones that
# may never be demoted to an on-demand file. The softer markers above still
# get inventoried, but a soft rule moving out is a note, not a block.
HARD_RE = re.compile(
    r"\bnever\b|\bcritical\b|\bmust not\b|\bmust never\b"
    r"|\bdo not\b|\bdon't\b|\bunverified\b|\bincomplete\b"
    r"|\bstop and\b|\brefuse", re.IGNORECASE)

# Sentence splitting has to survive "v3.20.", "Bk 40928/96.", "e.g.",
# "i.e.", "Dr.", and version strings, all of which are dense in this file.
ABBREV = re.compile(
    r"(?:\b(?:e\.g|i\.e|cf|vs|etc|approx|no|No|Bk|Pg|Ctf|Dr|St|Ave|Rd)\.)"
    r"|(?:\bv\d+\.\d+\.)"
    r"|(?:\b[A-Z]\.)")

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on",
    "for", "with", "at", "by", "from", "as", "is", "are", "was", "were",
    "be", "been", "it", "its", "this", "that", "these", "those", "so",
    "than", "then", "there", "here", "which", "when", "what", "who",
    "you", "your", "we", "our", "they", "their", "them", "he", "she",
    "his", "her", "not", "no", "do", "does", "did", "has", "have", "had",
    "can", "will", "would", "should", "could", "may", "might", "one",
    "two", "also", "still", "now", "any", "all", "each", "every", "into",
    "out", "up", "down", "over", "under", "again", "once", "only", "own",
    "same", "s", "t",
}


def strip_markdown(text: str) -> str:
    """Reduce markdown to its words, so formatting churn cannot look like a
    lost rule."""
    text = re.sub(r"`+([^`]*)`+", r"\1", text)          # code spans
    text = re.sub(r"\*{1,3}([^*]*)\*{1,3}", r"\1", text)  # bold / italic
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links
    text = re.sub(r"^\s*[-*+]\s+", "", text)              # bullets
    text = re.sub(r"^\s*\d+\.\s+", "", text)              # ordered items
    text = re.sub(r"^#+\s*", "", text)                    # headings
    return text.strip()


def split_sentences(text: str) -> list:
    """Split on sentence enders, protecting the abbreviations this file is
    full of."""
    holes = {}

    def _hide(m):
        key = f"\x00{len(holes)}\x00"
        holes[key] = m.group(0)
        return key

    protected = ABBREV.sub(_hide, text)
    parts = re.split(r"(?<=[.!?;])\s+(?=[A-Z(\"'—])", protected)
    out = []
    for p in parts:
        for k, v in holes.items():
            p = p.replace(k, v)
        p = p.strip()
        if p:
            out.append(p)
    return out


def fingerprint(sentence: str) -> frozenset:
    """A token set that survives rewording but not deletion."""
    plain = strip_markdown(sentence).lower()
    plain = re.sub(r"[^a-z0-9\s/_-]+", " ", plain)
    toks = [t for t in plain.split() if t and t not in STOPWORDS and len(t) > 1]
    return frozenset(toks)


def rule_id(fp: frozenset) -> str:
    return hashlib.sha1(" ".join(sorted(fp)).encode("utf-8")).hexdigest()[:12]


def extract_rules(path: Path) -> list:
    """Every candidate guardrail sentence in a skill file, with provenance."""
    lines = path.read_text(encoding="utf-8").split("\n")
    section, rules, seen = "(top)", [], set()

    for lineno, raw in enumerate(lines, 1):
        if re.match(r"^#{1,6}\s", raw):
            section = strip_markdown(raw)
            continue
        if not raw.strip() or raw.lstrip().startswith(("|", "```")):
            continue
        for sent in split_sentences(raw):
            if not MARKER_RE.search(sent):
                continue
            fp = fingerprint(sent)
            # Very short fragments carry no distinguishing content and
            # would match almost anything; they cannot be verified either
            # way, so they are not inventoried.
            if len(fp) < 5:
                continue
            rid = rule_id(fp)
            if rid in seen:
                continue
            seen.add(rid)
            rules.append({
                "id": rid,
                "hard": bool(HARD_RE.search(sent)),
                "section": section,
                "line": lineno,
                "text": strip_markdown(sent)[:400],
                "tokens": sorted(fp),
            })
    return rules


# ---------------------------------------------------------------- matching

EXACT = 0.98
STRONG = 0.80


DEFAULT_ALLOW = Path(__file__).resolve().parent / "rule_allow.json"

WINDOW = 3


def _corpus(path: Path) -> list:
    """The haystack: every sentence of a file, PLUS every run of up to
    WINDOW adjacent sentences, as fingerprints.

    The windows are not padding. Distillation rewrites punctuation as
    freely as wording — a rule written as one semicolon-joined sentence
    routinely comes back as two, and two short rules come back merged into
    one. Matching sentence-against-sentence scores that preserved rule in
    the seventies and reports it MISSING, which is worse than useless: a
    gate that fires on honest edits is a gate that gets switched off, and
    then the real demotion sails through. Windowing models the split/merge
    directly, and containment against a larger host is already the
    behaviour this matcher wants (see _best).
    """
    sents = []
    for raw in path.read_text(encoding="utf-8").split("\n"):
        sents.extend(split_sentences(raw))

    out = []
    for i, sent in enumerate(sents):
        fp = fingerprint(sent)
        if len(fp) >= 3:
            out.append(fp)
        # Adjacent runs, capped at WINDOW. Left uncapped this would
        # eventually match a deleted rule from tokens scattered across
        # unrelated prose, so the cap is what keeps MISSING meaningful.
        acc = set(fp)
        for j in range(i + 1, min(i + WINDOW, len(sents))):
            acc |= fingerprint(sents[j])
            out.append(frozenset(acc))
    return out


def _best(rule_tokens: frozenset, corpus: list) -> float:
    """Containment of the rule in its best-matching sentence.

    Containment, not Jaccard: distillation SHORTENS prose around a rule and
    often merges two sentences into one. Jaccard would penalise a longer
    host sentence that fully preserves the rule, which is the outcome we
    actually want to allow.
    """
    if not rule_tokens:
        return 0.0
    best = 0.0
    for fp in corpus:
        if not fp:
            continue
        score = len(rule_tokens & fp) / len(rule_tokens)
        if score > best:
            best = score
            if best >= EXACT:
                break
    return best


def _iter_ref_files(paths: list) -> list:
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.is_file():
            files.append(p)
    return files


def verify(snap_path: Path, core: Path, refs: list, allow: set) -> int:
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    rules = snap["rules"]

    core_corpus = _corpus(core)
    ref_files = _iter_ref_files(refs)
    ref_corpora = {f: _corpus(f) for f in ref_files}

    present, reworded, demoted, missing, allowed = [], [], [], [], []

    for r in rules:
        toks = frozenset(r["tokens"])
        score = _best(toks, core_corpus)
        if score >= EXACT:
            present.append(r)
            continue
        if score >= STRONG:
            reworded.append((r, score))
            continue

        where = None
        best_ref = 0.0
        for f, corpus in ref_corpora.items():
            s = _best(toks, corpus)
            if s > best_ref:
                best_ref, where = s, f

        if r["id"] in allow:
            allowed.append((r, where))
        elif best_ref >= STRONG:
            demoted.append((r, where, best_ref))
        else:
            missing.append((r, score))

    total = len(rules)
    print(f"rule-inventory — {total} rule(s) from {snap_path.name}")
    print(f"  core:  {core}")
    for f in ref_files:
        print(f"  ref:   {f}")
    print()
    print(f"  present in core (verbatim)   {len(present)}")
    print(f"  present in core (reworded)   {len(reworded)}")
    if allowed:
        print(f"  moved out, ACKNOWLEDGED      {len(allowed)}")

    if reworded:
        print("\nReworded but still in core — read these once:")
        for r, s in sorted(reworded, key=lambda x: x[1]):
            tag = "HARD" if r["hard"] else "soft"
            print(f"  [{tag}] {r['id']}  {s:.0%}  {r['text'][:96]}")

    if allowed:
        print("\nACKNOWLEDGED as reference, not guardrail (moved out on "
              "your explicit say-so):")
        for r, where in allowed:
            name = where.name if where else "not found anywhere"
            print(f"  {r['id']}  -> {name}  {r['text'][:88]}")

    if demoted:
        print("\nDEMOTED — survives only in an on-demand reference file.")
        print("This is the failure this gate exists to catch: the rule is")
        print("present only if the model chose to load that file, and the")
        print("rules that matter fire on paths nothing prompts you to")
        print("prepare for.")
        for r, where, s in demoted:
            tag = "HARD" if r["hard"] else "soft"
            name = where.name if where else "?"
            print(f"  BLOCK [{tag}] {r['id']}  -> {name} ({s:.0%})")
            print(f"        {r['text'][:150]}")
            print(f"        was: {r['section']} (line {r['line']})")

    if missing:
        print("\nMISSING — not found in core or in any reference file:")
        for r, s in missing:
            tag = "HARD" if r["hard"] else "soft"
            print(f"  BLOCK [{tag}] {r['id']}  best {s:.0%}")
            print(f"        {r['text'][:150]}")
            print(f"        was: {r['section']} (line {r['line']})")

    failed = bool(demoted or missing)
    print("\n" + ("BLOCKED — a guardrail was lost or demoted. Put it back in "
                  "the core skill file before shipping the split."
                  if failed else
                  "RULE INVENTORY INTACT — every inventoried rule is still "
                  "in the core skill file."))
    return 1 if failed else 0


# -------------------------------------------------------------------- main

def _warn_if_inside_repo(out: Path) -> None:
    repo = Path(__file__).resolve().parent.parent
    try:
        out.resolve().relative_to(repo)
    except ValueError:
        return
    print("  ! WARNING: this snapshot is being written INSIDE the repository.")
    print("    A snapshot quotes SKILL.md verbatim; taken from the private")
    print("    working copy it carries real client names. .gitignore and")
    print("    scrub_check.py both block it, but write it elsewhere.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="inventory the rules in a skill file")
    s.add_argument("--skill", required=True)
    s.add_argument("--out", required=True)

    l = sub.add_parser("list", help="print the inventory without saving it")
    l.add_argument("--skill", required=True)
    l.add_argument("--hard-only", action="store_true")

    v = sub.add_parser("verify", help="check a split against a snapshot")
    v.add_argument("--snapshot", required=True)
    v.add_argument("--core", required=True)
    v.add_argument("--refs", nargs="*", default=[])
    v.add_argument("--allow", nargs="*", default=[], metavar="RULE_ID",
                   help="rule ids you have consciously judged to be "
                        "reference, not guardrail. Use sparingly and never "
                        "for a rule that changes what you REPORT.")
    v.add_argument("--allow-file", nargs="*", default=None, metavar="PATH",
                   help="JSON {rule_id: reason} files of acknowledged "
                        f"relocations. {DEFAULT_ALLOW.name} beside this "
                        "script is always loaded when present; paths given "
                        "here are layered on top. Use an out-of-repo overlay "
                        "for ids derived from a private copy — a rule id is "
                        "a hash of the sentence's words, so an id taken from "
                        "unscrubbed text is a hash of a real name and must "
                        "not be committed (see scrub_check.py on why hashed "
                        "name lists are not safe to publish).")
    args = ap.parse_args()

    if args.cmd == "snapshot":
        skill = Path(args.skill)
        rules = extract_rules(skill)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": skill.name,
            "source_bytes": skill.stat().st_size,
            "rule_count": len(rules),
            "hard_count": sum(1 for r in rules if r["hard"]),
            "rules": rules,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"snapshot: {len(rules)} rule(s) "
              f"({payload['hard_count']} hard) from {skill.name}")
        print(f"  -> {out}")
        _warn_if_inside_repo(out)
        return 0

    if args.cmd == "list":
        rules = extract_rules(Path(args.skill))
        shown = [r for r in rules if r["hard"]] if args.hard_only else rules
        section = None
        for r in shown:
            if r["section"] != section:
                section = r["section"]
                print(f"\n=== {section}")
            tag = "HARD" if r["hard"] else "soft"
            print(f"  [{tag}] {r['id']}  L{r['line']}  {r['text'][:140]}")
        print(f"\n{len(shown)} rule(s) "
              f"({sum(1 for r in rules if r['hard'])} hard of {len(rules)})")
        return 0

    allow = set(args.allow)

    # The default file is optional (a fork may not have one). Any file named
    # explicitly is NOT — a configured overlay that does not resolve means
    # the gate is running with less acknowledgement than the operator thinks,
    # which is the failure mode this codebase keeps re-fixing.
    layers = [(DEFAULT_ALLOW, False)]
    layers += [(Path(p), True) for p in (args.allow_file or [])]

    for path, required in layers:
        if not path.is_file():
            if required:
                print(f"  ! allow-file not found: {path}\n"
                      "    It was named explicitly, so treating its absence "
                      "as 'nothing acknowledged' would silently change the "
                      "gate's answer. Refusing to run.")
                return 1
            continue
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ! {path.name} could not be read ({e}). Refusing to run "
                  "with an unreadable acknowledgement list — an unparsed "
                  "allow-file is indistinguishable from an empty one.")
            return 1
        allow |= {k for k in entries if not k.startswith("_")}

    return verify(Path(args.snapshot), Path(args.core), args.refs, allow)


if __name__ == "__main__":
    sys.exit(main())
