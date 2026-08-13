# ma-registry

A Claude Code plugin that finds the vesting deed for a Massachusetts property
in the county registry of deeds, pulls the legal description out of it, and
hands back paste-ready text — plus the title flags that tell you when *not*
to trust the result.

```
/ma-registry:legal-description 42 Example Road, Cohasset — seller Sample
```

**No API key required.** Every safety check in this plugin runs without one:
the grantee search, the deed selection, the registry-abstract wrong-parcel
guard, the auto-retarget, the grantor check and its classification. Without a
key, Claude reads the downloaded deed PDFs in your session — that is the
default mode, not a degraded one. An `ANTHROPIC_API_KEY` buys you a faster
single-shot run and nothing else.

---

## What it actually does

1. Searches the seller as **grantee** in the county registry and picks the
   vesting deed.
2. Confirms the deed is for **your** parcel, from the registry's own
   Document Abstract — the index record, not the PDF — so the check costs
   one HTTP GET and needs no model. If the address disagrees, the run
   **retargets** to the right instrument and says it did.
3. Downloads the deed PDF pages.
4. Extracts the verbatim legal description (API mode) or names the PDFs for
   Claude to read (claude-code mode).
5. Runs the **grantor check**: the seller — and every co-owner it can derive
   from the deed and the abstract — searched as grantor, to catch a deed
   *out* of the property recorded after they bought it. Hits are classified
   by parcel so a common surname's ninety hits collapse to the handful that
   need judgment.
6. Writes a markdown report draft, a three-form legal-description `.txt`
   (verbatim / paste-ready / with derivation clause), optionally a `.docx`,
   and the complete run JSON.

### This is not a title examination

The plugin finds a deed and reads it. It does **not** certify title, examine
the chain, verify discharges, or search probate, bankruptcy, tax takings, or
municipal liens. Cross-references it reports (`cross_references`) are the
registry's own index pointers — a discharge appearing there means such an
instrument exists, **not** that a mortgage was discharged. Every output is a
draft for a competent professional to review. Do not record a deed containing
a legal description this tool produced without reading the source instrument
yourself.

The design bias is toward **abstaining**: a wrong legal description in a
recorded deed is a malpractice event, so "not found, here is why, here is what
to try" always beats a plausible guess. Typed failures like
`registry_unavailable` and `results_truncated_at_cap` exist so that a
registry's nightly backup or a 1,000-row server cap can never be silently read
as "no deed exists."

---

## County support

Massachusetts registries run on several different software platforms, and
support tracks the platform, not the county line.

| Tier | Counties | How it runs | Typical run |
|---|---|---|---|
| **1** | **Norfolk**, **Barnstable** | Pure HTTP (`requests` + `beautifulsoup4`). No browser at all. Recorded Land *and* Land Court. | 10–65 s |
| **2** | **Plymouth** | Headless browser (Playwright/Chromium) against an ASP.NET WebForms site. | 1–3 min |
| **3** | **Middlesex South** | Browser, **headful required** — the site is behind Incapsula bot protection that 403s headless browsers on the search POST. A real Chrome window opens. | 2–4 min |
| — | Suffolk | Stub. Recognized, not implemented. | — |
| — | Everything else | **Refuses**, by design. A registry this tool has not been tested against is a wrong-parcel risk, not a feature request. | — |

Several counties have multiple registry districts (see
`data/ma-multi-registry-counties.md`); the wrong district is the wrong
database, so check before assuming a county name is enough.

Town-code tables cover the towns actually exercised in real runs. An
unrecognized town falls back to a county-wide search and emits a note asking
you to add the code — it does not silently narrow the search.

---

## Install

Requires **Python 3.9+** and [Claude Code](https://claude.com/claude-code).

**1. Install the plugin.** In Claude Code:

```
/plugin marketplace add john-mcnulty/ma-legal-description
/plugin install ma-registry@ma-registry
```

You will be asked for the settings in the next section; the output folder is
the only required one. From a terminal instead:

```bash
claude plugin marketplace add john-mcnulty/ma-legal-description
claude plugin install ma-registry@ma-registry \
  --config "output_dir=/path/to/your/closings" \
  --config "extraction_mode=claude-code" \
  --config "copy_to_clipboard=true" \
  --config "write_docx=false" \
  --config "show_timings=true"
```

**2. Install the Python dependencies.** The plugin is installed under
`~/.claude/plugins/`; `pip` needs the requirements from this repository:

```bash
python -m pip install requests beautifulsoup4          # required
python -m pip install playwright                       # Plymouth / Middlesex South
python -m playwright install chromium                  #   ...and its browser
python -m pip install anthropic python-docx            # optional, see below
```

From a clone, `pip install -r requirements.txt` gives you the required pair
(a complete Norfolk/Barnstable setup on its own), and
`pip install -r requirements-full.txt` adds the rest.

**3. Check the environment** before the first real run:

```bash
python ~/.claude/plugins/*/ma-registry/scripts/legal_desc_fetch.py --doctor
```

`--doctor` reports dependencies, whether Chromium is actually installed (the
step people skip — `pip install playwright` does not fetch a browser), whether
API credentials resolve, whether your output folder is writable, and whether
each registry is reachable. It distinguishes a registry serving its
maintenance page from one that is genuinely down, and it exits 0 for a
keyless, browser-less install because that is a supported configuration, not a
broken one.

### Settings the plugin asks for

Configured once when you enable the plugin:

| Option | What it does |
|---|---|
| `output_dir` | Where reports, `.txt`/`.docx`, PDFs and the run JSON are written. Runs never write anywhere else. |
| `extraction_mode` | `claude-code` (default, no key), `api`, or `auto`. |
| `copy_to_clipboard` | Put the paste-ready description on the clipboard on success. |
| `write_docx` | Also write a Word file. |
| `show_timings` | Include the per-stage timing table in the report. |

**Set all five, even though four have defaults.** An option you leave unset is
not filled in from its default — it reaches the skill as a literal
`${user_config.…}` placeholder. Nothing silently goes wrong if that happens
(the skill falls back to the documented defaults, and the script hard-refuses
a placeholder rather than creating a folder named after one), but configuring
them is one command and removes the guesswork. Re-run
`/plugin configure ma-registry@ma-registry` any time to change them.

### Developing on it

To work on a clone rather than an installed copy:

```bash
claude --plugin-dir /path/to/ma-legal-description
```

That loads it for **one session only** and does **not** collect the settings
above, so every `${user_config.…}` arrives unsubstituted — expected, and
handled. Use `/reload-plugins` to pick up edits without restarting.

### One undeclared dependency

Steps 2–5 of the workflow — the manual fallback used when the script path
does not cover a registry — drive a browser through the **Claude in Chrome**
extension. If you never leave the script fast path (Norfolk, Barnstable,
Plymouth, Middlesex South), you will not need it.

If you do use the browser path, set Chrome to **download** PDFs rather than
open them in the built-in viewer (`chrome://settings/content/pdfDocuments` →
"Download PDFs"). Otherwise the deed opens in a viewer the automation cannot
read and the run stalls on a page that looks fine to you.

---

## Privacy

**Nothing is transmitted anywhere.** There is no telemetry, no analytics, no
usage reporting, no crash reporting, and no "anonymous" statistics. The
plugin talks to exactly two kinds of host: the county registry you are
searching, and — only in `api` extraction mode — the Anthropic API, to read
the deed PDF you downloaded.

This is not incidental. A run's metadata *is* client data: the seller's name,
the property address, the book and page. Run timings, the result JSON and the
report all stay in your `output_dir`.

---

## Being a good citizen at the registry

These are small public systems, several of them decades old, and they have no
API. A popular plugin hammering one gets it rate-limited or blocked — and the
block lands on every user of that registry, including a conveyancer trying to
close a purchase that afternoon.

The plugin is therefore deliberately unhurried: requests are throttled,
searches are paginated with hard caps rather than fetched exhaustively, and
concurrency is bounded to a handful of workers. **Please do not raise those
limits.** If a search hits its cap the tool tells you so — a truncated
grantor check is reported as `INCOMPLETE`, never quietly presented as clean.

The HTTP engine currently sends a browser User-Agent string. That is honest
about the *traffic* (it is the same requests a browser makes against the same
public search forms) but not about the *client*, and a registry cannot
distinguish this plugin from a person clicking. If you operate one of these
registries and want that changed, or want this traffic identified or
throttled differently, please open an issue — that is a change worth making
and easy to make.

---

## Development

Regression tests live alongside the private working copy rather than in this
repository, because their fixtures are real recorded instruments and real
party names. The repository copy of the script is pseudonymized: names,
street addresses and book/page citations in comments and docstring examples
are substitutes. The substitution touches only comments and example strings —
no identifier, registry field name, or town code — so it cannot change
behavior.

If you fork this and want the test suite, open an issue and it can be
reconstructed against synthetic fixtures.

### The commit gate

`scripts/scrub_check.py` runs before every commit and refuses any that
would publish client data:

```bash
python scripts/scrub_check.py --install-hook   # once, after git init
python scripts/scrub_check.py                  # or run it by hand
```

It checks for client data by **shape** — recorded instruments, deed images,
run logs, result JSON, absolute home-directory paths, stray credentials — so
it carries no confidential list and works in a fork. On the maintainer's
machine it additionally delegates to a private name-identity verifier that
never enters this repository. If that verifier is configured but missing, the
gate **blocks**; it does not quietly fall back to the weaker half.

---

## License

MIT — see [LICENSE](LICENSE).

Author: John McNulty <john.mcnulty80@gmail.com>

Not affiliated with, endorsed by, or connected to Avenu Insights & Analytics,
Browntech, or any Massachusetts registry of deeds. "MassLandRecords" is their
product name, not this one's.
