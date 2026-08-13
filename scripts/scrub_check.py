#!/usr/bin/env python3
"""
scrub_check.py — pre-commit gate against committing client data.

    python scripts/scrub_check.py                 # check the working tree
    python scripts/scrub_check.py --staged        # check only staged files
    python scripts/scrub_check.py --install-hook  # wire it to git pre-commit

Exit 0 = clean, 1 = something must not be committed.

WHY THIS FILE CANNOT CONTAIN THE THING IT CHECKS FOR
----------------------------------------------------
The obvious gate is a list of real client names to grep for. That list is
exactly the confidential data the gate exists to protect, and this file is
public — so shipping it here would publish the names in the act of trying
not to. Hashing them is barely better: surnames and street names are
low-entropy, and a hash list is brute-forced against a dictionary in
seconds. Neither is acceptable, and git history survives a private->public
flip, so a mistake here is not fixable by a later commit.

So the gate has two halves:

  1. STRUCTURAL checks (this file, always run). These look for client data
     by SHAPE, not by identity: recorded instruments and downloaded
     images, run logs, absolute paths naming a user's home directory,
     stray credentials. No name list required, so they are safe to publish
     and they work for anyone who forks this.

  2. IDENTITY checks (delegated). If the private verifier is present on
     this machine — pointed at by MA_REGISTRY_SCRUB_TOOLS, or found at its
     conventional location beside the repo — it is executed and its result
     folded in. It holds the name map and never enters this repository.

The two halves fail differently ON PURPOSE. Missing structural checks are
a hard failure for everyone. A missing private verifier is a hard failure
only for the repository OWNER, who is identified by the presence of a
local marker; for a fork, it is a note. A gate that silently downgrades
itself when its strongest check is unavailable is the same
missing-information-read-as-a-negative-answer failure this codebase keeps
fixing elsewhere.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------- structural

# Files that are client data by their very existence in this tree. The
# original working copy of this tool sits inside a folder holding ~200
# recorded deed PDFs, 60+ generated reports, and a run log with a seller
# name and property address on every line. None of that may ever be here.
FORBIDDEN_GLOBS = [
    ("*.pdf",  "a recorded instrument"),
    ("*.jpg",  "a deed page image"),
    ("*.jpeg", "a deed page image"),
    ("*.png",  "a screenshot (deed images and registry pages are client data)"),
    ("*.docx", "a generated deliverable"),
    ("*result.json", "a run result (holds seller name, address, book/page)"),
    ("*run_log*", "the run log (seller + address on every entry)"),
    ("*registry_profile.json", "a per-client registry profile"),
    ("*namemap*", "THE NAME MAP — this must never be in the repository"),
    ("*scrub_inventory*", "a scrub tool carrying real names"),
    ("*verify_scrub*", "a scrub tool carrying real names"),
    ("*apply_scrub*", "a scrub tool carrying real names"),
    (".env", "credentials"),
    ("*.pem", "credentials"),
    ("*.key", "credentials"),
]

# Content patterns that are client-identifying by shape.
CONTENT_PATTERNS = [
    (re.compile(r"[A-Za-z]:\\+Users\\+(?!<)[A-Za-z0-9._-]+", re.I),
     "an absolute Windows user path (names the operator and their layout)"),
    (re.compile(r"/(?:home|Users)/(?!<)[a-z0-9._-]{2,}/", re.I),
     "an absolute POSIX home path"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
     "what looks like an Anthropic API key"),
    # These two lines carry the allow marker because the pattern text
    # matches itself — the first thing this gate ever flagged was its own
    # definition.
    (re.compile(r"OneDrive", re.I),                      # scrub-check: allow
     "a synced-folder path; the private working copy lives in one"),  # scrub-check: allow
]

# The author's own address is published deliberately in the README and
# plugin manifest; every OTHER address is a finding.
ALLOWED_EMAILS = {"john.mcnulty80@gmail.com"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

SCAN_SUFFIXES = {".py", ".md", ".json", ".txt", ".toml", ".yml", ".yaml", ".cfg"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}

# Lines carrying this marker are exempt from the content patterns. Some
# documentation legitimately has to SHOW a path shape.
ALLOW_MARKER = "scrub-check: allow"


def _iter_files(staged: bool):
    if staged:
        try:
            out = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                cwd=REPO, capture_output=True, text=True, check=True).stdout
        except Exception as e:
            print(f"  ! could not list staged files ({e}); checking the tree")
            return _iter_files(False)
        for rel in out.split("\n"):
            rel = rel.strip()
            if rel:
                p = REPO / rel
                if p.is_file():
                    yield p
        return
    for p in sorted(REPO.rglob("*")):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.parts):
            yield p


def structural_check(staged: bool) -> list:
    findings = []
    files = list(_iter_files(staged))

    for p in files:
        rel = p.relative_to(REPO).as_posix()
        for pat, why in FORBIDDEN_GLOBS:
            if p.match(pat) or p.name.lower().endswith(pat.strip("*").lower()):
                findings.append(f"{rel}: {why} — must not be committed")
                break

    for p in files:
        if p.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = p.relative_to(REPO).as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARKER in line:
                continue
            for rx, why in CONTENT_PATTERNS:
                m = rx.search(line)
                if m:
                    findings.append(f"{rel}:{i}: {why} — {m.group(0)!r}")
            for m in EMAIL_RE.finditer(line):
                if m.group(0).lower() not in ALLOWED_EMAILS:
                    findings.append(f"{rel}:{i}: an email address — {m.group(0)!r}")
    return findings


# ----------------------------------------------------------------- identity

def _private_dir() -> Path:
    """
    Convention: the private tools sit one level ABOVE the repo root, so git
    inside the repo cannot see them.
    """
    return REPO.parent / f"{REPO.name}-PRIVATE-scrub-tools"


def _private_verifier() -> Path:
    """Locate the private verifier without ever naming its contents."""
    env = os.environ.get("MA_REGISTRY_SCRUB_TOOLS")
    if env:
        p = Path(env)
        # Resolve by SHAPE, not by existence: a configured path that does
        # not exist must stay pointing where it was configured, so the
        # caller is told it is missing rather than being silently sent
        # somewhere else.
        return p if p.suffix == ".py" else p / "verify_scrub.py"
    return _private_dir() / "verify_scrub.py"


def _is_owner_machine() -> bool:
    """
    Is this a machine where the private verifier is EXPECTED to exist?

    Deliberately independent of whether the verifier path resolves. An
    earlier version derived this from the resolved path's parent, so
    pointing MA_REGISTRY_SCRUB_TOOLS at a missing file made the parent
    directory not-a-directory, which read as "this must be a fork" — and
    the gate downgraded itself to a note and printed "safe to commit".
    That is the exact missing-information-read-as-a-negative-answer bug
    this file's docstring warns about, reproduced inside the gate itself.

    Two independent signals, either of which means "owner":
      * the operator explicitly configured a location — configuring one is
        a statement that a verifier is supposed to be there;
      * the conventional private directory exists beside the repo.
    """
    if os.environ.get("MA_REGISTRY_SCRUB_TOOLS"):
        return True
    return _private_dir().is_dir()


def identity_check() -> tuple:
    """Returns (status, detail) where status is ok|fail|skip."""
    v = _private_verifier()
    if not v.is_file():
        if _is_owner_machine():
            return ("fail",
                    f"the private verifier is expected at {v} but is missing. "
                    "On this machine that is a broken gate, not an absent "
                    "one — refusing to pass.")
        return ("skip",
                "no private verifier on this machine (expected for a fork). "
                "Structural checks only; the name-identity check did not run.")
    try:
        r = subprocess.run([sys.executable, str(v)],
                           capture_output=True, text=True, timeout=300)
    except Exception as e:
        return ("fail", f"the private verifier could not be executed: {e}")
    if r.returncode == 0:
        return ("ok", "private verifier reports ALL CHECKS PASSED")
    tail = (r.stdout or "").strip().splitlines()
    return ("fail", "private verifier FAILED:\n    "
            + "\n    ".join(tail[-25:] or ["(no output)"]))


# --------------------------------------------------------------------- hook

HOOK = """#!/bin/sh
# Installed by scripts/scrub_check.py --install-hook
exec python "$(git rev-parse --show-toplevel)/scripts/scrub_check.py" --staged
"""


def install_hook() -> int:
    hooks = REPO / ".git" / "hooks"
    if not hooks.is_dir():
        print(f"No git hooks directory at {hooks} — run `git init` first.")
        return 1
    path = hooks / "pre-commit"
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
        if "scrub_check.py" in existing:
            print(f"Already installed: {path}")
            return 0
        backup = path.with_suffix(".pre-scrub-check")
        backup.write_text(existing, encoding="utf-8")
        print(f"Existing hook backed up to {backup}")
    path.write_text(HOOK, encoding="utf-8")
    try:
        path.chmod(0o755)
    except Exception:
        pass
    print(f"Installed pre-commit hook: {path}")
    return 0


# --------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--staged", action="store_true",
                    help="check only files staged for commit")
    ap.add_argument("--install-hook", action="store_true",
                    help="install this as the git pre-commit hook")
    args = ap.parse_args()

    if args.install_hook:
        return install_hook()

    print(f"scrub-check — {'staged files' if args.staged else 'working tree'}\n")

    findings = structural_check(args.staged)
    print("Structural checks")
    if findings:
        for f in findings:
            print(f"  BLOCK  {f}")
    else:
        print("  clean — no client documents, run logs, absolute home paths, "
              "or stray credentials")

    status, detail = identity_check()
    print("\nName-identity check")
    print(f"  {'ok' if status == 'ok' else status.upper()}  {detail}")

    failed = bool(findings) or status == "fail"
    print("\n" + ("BLOCKED — do not commit. git history survives a "
                  "private-to-public flip, so this must be clean at the "
                  "FIRST commit."
                  if failed else "OK — safe to commit."))
    if status == "skip" and not failed:
        print("Note: the strongest check did not run. See the module "
              "docstring for what that does and does not cover.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
