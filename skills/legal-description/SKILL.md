---
description: Find the vesting deed for a Massachusetts property at the county Registry of Deeds and extract a paste-ready legal description. Use when asked for a legal description, a vesting deed, or a Registry of Deeds search for a MA property.
---

# Legal Description Search Workflow

Run the Massachusetts Registry of Deeds legal description search workflow for a residential real estate closing file.

**Arguments:** $ARGUMENTS

Parse the arguments above for:
- **Seller name** — the seller / purported current owner
- **Property address** — full address including city/town and state

If either is missing, ask the user before proceeding.

---

## CONFIGURATION

Configuration is handled by the plugin, not by editing this file. Claude Code
prompts for these values when the plugin is enabled; change them any time with
`/plugin`.

| Setting | Used for |
|---|---|
| `output_dir` | Where the report, legal-description text, and deed PDFs/images are written. Referenced below as `${user_config.output_dir}`. |
| `extraction_mode` | `auto` (default) uses the Anthropic API when `ANTHROPIC_API_KEY` is present and otherwise falls back to reading the deed PDF in this session — so a keyless install works with no setup. `claude-code` never calls the API; `api` forces it and errors if the key is missing. The registry search, the wrong-parcel guard and the grantor check need no API key in ANY mode. |
| `copy_to_clipboard` | Put the paste-ready legal description on the clipboard at the end of a successful run. |
| `write_docx` | Also write the legal description as a `.docx` for Word users. |
| `show_timings` | Record per-stage elapsed times and print a timing summary. Timings stay on this machine. |

The bundled script and data files are addressed with `${CLAUDE_PLUGIN_ROOT}`,
which resolves to wherever the plugin is installed. Never hardcode a path.

**One-time Chrome setup (recommended):** Go to Chrome Settings → Privacy and security → Site Settings → Additional content settings → PDF documents → select **"Download PDFs"**. This prevents the Acrobat extension from intercepting PDF navigations, allowing the preferred fetch-download + Read tool approach to work cleanly across all Browntech ALIS registries (Norfolk, Barnstable).

**This workflow is not a title certification.** It answers three narrow
questions (see *Scope discipline* below). Verify anything it produces before
relying on it in a recorded instrument.

---

## PURPOSE

Automate the Registry of Deeds search for a legal description as part of handling a residential real estate closing. Everything the workflow produces is written to `${user_config.output_dir}`: a markdown report, the legal description as paste-ready text, and the deed page images.

---

## OUTPUTS

### 1. Markdown Report (`.md`)
Named: `Legal Description - [Address] - [Seller Last Name].md`

Structure:
```
# Legal Description Report
Property: [Address]
Seller: [Name]
Generated: [Date/Time]
---
## LEGAL DESCRIPTION
[Legal description text — primary copy-paste target]
---
## Deed Metadata
- Registry: ...
- Section: Recorded / Registered (Land Court)
- Book: ...     ← Recorded only
- Page: ...     ← Recorded only
- Document #: ...
- Recorded Date: ...
- Signing Date: ... (if extractable)
- Grantees (current owners as shown on deed):
  - [Name(s)]
- Certificate of Title: ...  ← Registered only
- Deed Property Address: ...  ← address as shown on deed (left margin notation, granting clause, or cover sheet — use most complete source)
## Title Flags / Notes
[Flags, warnings, or notes]
## Screenshots Saved
- [filename_p1.jpg] — Page 1
- [filename_p2.jpg] — Page 2 (if applicable)
```

### 2. Deed Screenshots (`.jpg`)
Named: `[Address] - [Seller Last Name] - deed_p1.jpg`, `_p2.jpg`, etc.
Purpose: auditability — visual record of the actual deed.

### 3. Legal Description Text (`.txt`)
Named: `Legal Description - [Address] - [Seller Last Name].txt`

The paste target for Word, a document-assembly system, or a SaaS closing
platform. Contains three forms, clearly labelled:

1. **Verbatim** — exactly as recorded, line breaks preserved.
2. **Paste-ready** — the same text reflowed to a single clean paragraph.
   Whitespace, line-break hyphenation, and quote/dash characters are
   normalized. **Nothing else is changed** — no OCR correction, no spelling
   fixes, no re-punctuation. Archaic spelling and unusual punctuation in an
   old deed are the record; silently "improving" a metes-and-bounds call is
   invisible in review and wrong in a recorded instrument.
3. **Paste-ready + derivation clause** — the above followed by the "For
   title, see deed recorded at Book ___, Page ___" reference.

If `copy_to_clipboard` is on, form 2 is also placed on the clipboard. If
`write_docx` is on, the same three forms are written to a `.docx` alongside.

---

## WORKFLOW STEPS

### Step 1 — Record Start Time & Determine Registry

Record the start timestamp and persist it to disk so it survives context
compaction. Use Python rather than `date` — Python is already a hard
dependency of this workflow, while `date -u` and `/tmp` do not exist on a
Windows shell:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/run_clock.py" start
```

This writes the start time to the plugin's own data directory and echoes it.
Do this as your very first action; that file is the authoritative start time —
do not re-run a clock command as a substitute for it later.

Determine the correct Massachusetts Registry of Deeds from the property address.

**Registry Readiness Key:**
- ✅ **Ready** — fully documented, multiple runs completed, all known edge cases captured
- 🔶 **Ready (new)** — documented on first live run, technically complete but less battle-tested
- 🔷 **Next priority** — high-activity county, not yet documented; run supervised and document as you go
- 🟡 **Platform known** — search engine identified and entry point verified, but no fast path yet; adding it is a routing-table entry against an existing engine, not a new engine
- ⬜ **Low priority** — not yet validated; do not run unsupervised on a real closing file

**Registry Routing Table:**

| Registry | Covers | Search URL | System | Status |
|---|---|---|---|---|
| Plymouth County | All Plymouth County municipalities | https://titleview.org/plymouthdeeds/ | Avenu/20-20 (ASP.NET) | ✅ Ready |
| Norfolk County | See municipality list below | https://www.norfolkresearch.org/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N | Browntech ALIS | ✅ Ready |
| Barnstable County | See municipality list below | https://search.barnstabledeeds.org/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N | Browntech ALIS | ✅ Ready |
| Suffolk County | Boston, Chelsea, Revere, Winthrop | https://www.masslandrecords.com/suffolk/D/Default.aspx | Avenu/20-20 (ASP.NET) | ✅ Ready (v3.41 fast path — **both** Recorded Land and Registered Land/Land Court; consumes the registry's 1,000-record cap and 0-hit messages) |
| Middlesex South | Cambridge, Newton, Framingham, and most southern Middlesex municipalities (Lowell area = Middlesex North, separate registry) | https://www.masslandrecords.com/MiddlesexSouth/D/Default.aspx | Avenu/20-20 (masslandrecords, Incapsula WAF) | 🔶 Ready (new) |
| Essex North; Worcester North; Hampden | Essex North = Andover/Lawrence/Methuen/North Andover; Worcester North = Ashburnham/Fitchburg/Leominster/Lunenburg/Westminster; Hampden = whole county | `search.lawrencedeeds.com` / `fitchburgdeeds.com` / `search.hampdendeeds.com`, all `/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N` | Browntech ALIS — **same engine as Norfolk/Barnstable**, no WAF | 🟡 Platform known |
| Berkshire Middle/North/South; Dukes; Franklin; Hampshire; Middlesex North; Worcester | See the multi-district municipality list below | masslandrecords.com/`{BerkMiddle,BerkNorth,Berksouth,Dukes,Franklin,Hampshire,MiddlesexNorth,Worcester}`/D/Default.aspx | Avenu/20-20 — **same engine as Suffolk/Middlesex South**, Incapsula (headful Chrome) | 🟡 Platform known |
| Bristol Fall River | Fall River, Freetown, Somerset, Swansea | https://i2o.uslandrecords.com/MA/BristolFallRiver/D/Default.aspx | Avenu/20-20 on a different host — **no WAF**; may be pure-HTTP scriptable | 🟡 Platform known |
| Essex South; Bristol North; Bristol South | Essex South = 30 municipalities incl. Salem/Lynn/Peabody; Bristol North = Taunton area; Bristol South = New Bedford area | `salemdeeds.com` / `search.tauntondeeds.com` / `masearchsb.com` | Three **bespoke** platforms — a new engine each | ⬜ Low priority |
| Nantucket | Nantucket | *unresolved — no reachable registry domain found* | Unknown | ⬜ Low priority |

**Norfolk County municipalities:** Avon, Bellingham, Braintree, Brookline, Canton, Cohasset, Dedham, Dorchester, Dover, Foxborough, Franklin, Holbrook, Hyde Park, Medfield, Medway, Millis, Milton, Needham, Norfolk, Norwood, Plainville, Quincy, Randolph, Roxbury, Sharon, Stoughton, Walpole, Wellesley, West Roxbury, Westwood, Weymouth, Wrentham

**Barnstable County municipalities:** Barnstable (incl. Centerville, Cotuit, Hyannis, Marstons Mills, Osterville, West Barnstable, etc. — all use code `BARN`), Bourne, Brewster, Chatham, Dennis, Eastham, Falmouth, Harwich, Mashpee, Orleans, Provincetown, Sandwich, Truro, Wellfleet, Yarmouth

**Multi-district counties** (municipality-by-municipality breakdown ships with the plugin at `${CLAUDE_PLUGIN_ROOT}/data/ma-multi-registry-counties.md`): Berkshire (3), Bristol (3), Essex (2), Middlesex (2), Worcester (2). Any county NOT in that file has one registry for the whole county.

**Platform, entry-point URL and WAF status for all 21 districts** — including the three bespoke platforms, the Hampden session quirk, and the tested-and-negative `i2o` Incapsula bypass — are in `${CLAUDE_PLUGIN_ROOT}/skills/legal-description/references/registry-platform-triage.md`. Read it before adding a registry.

**First run in an undocumented registry (🔷, 🟡 or ⬜):** Do not run unsupervised on a real closing file. **A 🟡 Platform known district is not a supported district** — sharing an engine means the transport is written, not that the district behaves like its siblings. Every wrong-parcel and false-clean trap this workflow guards against was per-instance, not per-platform (a row cap applied before the date sort, a prefix-matching name box, filters that silently suppress rows, an office dropdown read before its postback lands), and each district needs its own town-code table harvested from its own search form. Treat the first run as a documentation run and verify those behaviours before trusting any result. The first run in any new registry is a documentation run — expect to encounter unfamiliar UI, blocked automation, or unexpected behavior. Take notes on search URL, field names, image viewer behavior, and any download quirks, and add them to the Technical Notes section at the bottom of this file before relying on the workflow for that registry.

**Non-Western name order:** For sellers with Chinese, Korean, Vietnamese, or similar names where cultural convention places the surname first, confirm the correct surname. Most MA registries index by legal surname as recorded on the deed. When in doubt, try both orderings.

**Section routing (Recorded vs. Registered/Land Court):** If the user already
knows which section the property is in — from a prior search, the title
commitment, an existing certificate of title, or the seller's own paperwork —
use it, and say so in the report:

- **Registered Land known** — **run the Step 1C Land Court search FIRST**, using the known Certificate of Title # to confirm the right parcel. Do not run the Recorded-first fast path as the primary search — a seller with parcels in both sections can return a wrong-parcel Recorded deed with exit 0 and no warning (Kilbride / 29 Fox Meadow Rd: exit 0 for Lot 26 / 7 Thornbury Lane while the subject was Ctf 174905).
- **Recorded Land known, with Bk/Pg** — pass `--book`/`--page` to the fast path to pin deed selection.
- **Unknown** — default behavior below.

Otherwise, start with the **Recorded** section (~75% of properties). Ask the user if there is any ambiguity about which registry applies.

---

### Step 1B — Script Fast Path (Plymouth, Norfolk, Barnstable, Middlesex South)

**What it is:** A single Python script that handles the entire registry interaction — grantee search, image download, and grantor check — and returns structured JSON. Always try this first. If it succeeds, skip Steps 2–5 and proceed directly to Step 6 with the returned metadata.

**The run writes its own JSON to disk (v3.30).** Every run saves the complete result to **`<output>\<base-name> - result.json`** and reports the path as `result_file`. If the JSON you see in the terminal is truncated — a long grantor check easily overflows the tool output limit, and the tail is where `book`, `page` and `needs_review` live — **Read that file instead of re-running the search.** Recovering by re-running used to cost a second full run (~6 minutes on a common surname). A re-run refreshes the file; an unsuccessful re-run will not overwrite a successful record, diverting to a timestamped sibling and saying so in the notes.

**Engines (v3.9):** Norfolk and Barnstable now run on a **pure-HTTP engine by default** (requests + BeautifulSoup, no browser) — runs complete in **~10–35 seconds** instead of ~3 minutes. `--engine {auto,http,playwright}` controls this: `auto` (default) uses HTTP and falls back to the old Playwright engine automatically on hard HTTP failure. Plymouth and Middlesex South remain Playwright-only. The result JSON's `engine` field reports which engine ran.

**Script:** `${CLAUDE_PLUGIN_ROOT}/scripts/legal_desc_fetch.py`

**Extraction mode (v3.27).** This user's setting — extraction_mode: `${user_config.extraction_mode}`. Append `--extraction ${user_config.extraction_mode}` to every ALIS invocation below.

- **`claude-code`** (default; no API key needed) — the script does everything except read the deed PDFs, then names them in a `READ THE DEED PDFs ...` note. **Read those PDFs yourself** with the Read tool to get the legal description, signing date, parties, tenancy and prior-deed reference, then continue at Step 6. `extraction_error` stays null: this is a mode, not a failure. Two things also fall to you: any candidate or grantor hit whose registry abstract carried no address (Read its `sample_file` page-1 PDF to answer which-parcel), and Step 7 delivery — write your transcribed legal description to a UTF-8 `.txt` and re-run the same command with `--deliver-text-file <that path>` (adding nothing else) so the script produces the standard three-form paste-out instead of you assembling it by hand.
- **`api`** — the script calls the Anthropic API and returns the extracted fields; skip the Read step. Requires `ANTHROPIC_API_KEY`; without it the run stops immediately with an actionable error and performs no search.
- **`auto`** — API when the key is present, otherwise `claude-code`.

**What never depends on the mode:** the grantee search and deed selection, the registry-abstract address check (the wrong-parcel guard and auto-retarget), the grantor check with its `needs_review` classification, and the cross-references. A keyless run keeps every one of those safety checks — it has been live-validated auto-retargeting to the correct deed and flagging a subject-parcel deed-out CRITICAL with no API key at all.

**Delivery flags (v3.19).** This user's settings — copy_to_clipboard: `${user_config.copy_to_clipboard}`, write_docx: `${user_config.write_docx}`. Append `--copy` to every invocation below when copy_to_clipboard is true, and `--docx` when write_docx is true. On success the script then performs Step 7 itself: it writes the three-form legal-description `.txt` (JSON `txt_file`), reflows the paste-ready text (`legal_description_paste_ready`), copies it to the clipboard (`clipboard_copied`), and optionally writes the `.docx` (`docx_file`). All delivery failures are notes, never run errors.

**If a `${user_config.…}` value below still reads as a literal placeholder** (you see the braces rather than a real path or `true`/`false`), the plugin was loaded without its configuration — normal when it is run from a directory with `claude --plugin-dir`. Do **not** pass the placeholder through to the script: it will refuse the run rather than create a folder with that literal name. Ask the user for the output folder, and treat the unset options as their defaults (`extraction_mode` = `auto`, `copy_to_clipboard` = true, `write_docx` = false, `show_timings` = true).

**Run timings (v3.31).** This user's setting — show_timings: `${user_config.show_timings}`. Append `--no-timings` to the invocations below when show_timings is false. Timings are recorded in the result JSON either way (`timings.total_seconds`, `timings.stages`, `timings.slowest`); the flag controls only the **Run Timings** table in the report draft. They are measured locally and never transmitted. Use `timings.slowest` when a run feels slow — on a common surname the grantor check legitimately dominates, and the fix is never to lower the pagination caps.

**Invocation — Plymouth County:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/legal_desc_fetch.py" \
  --registry plymouth \
  --last "DONNELLY" \
  --first "JEANMARIE" \
  --base-name "62 Halyard Way Plymouth - Donnelly" \
  --output "${user_config.output_dir}"
```
`--first` should be uppercase with no spaces between compound name parts (e.g., `JEANMARIE`).

**`--town` is optional for Plymouth (v2.7+).** The script auto-detects the town from the last word of the address portion of `--base-name` (e.g., `"155R Seabright Road Scituate - Marston"` → `"SCITUATE"`). Pass `--town` explicitly only if the auto-detected value would be wrong (e.g., the last address word is a unit or building suffix rather than a town name). Street numbers like `"155R"` (rear-lot suffix) are also handled automatically.

**Town abbreviation matching (v2.9+).** Plymouth County's grid displays town names as short abbreviations. Most match via substring check (e.g. `SCIT ⊂ SCITUATE`). A few do not — those are in `_PLYMOUTH_TOWN_ABBREVS`. As of v2.9 the dict is only needed for sellers with **multiple Plymouth County properties**: if there is exactly one name-search result and its abbreviation isn't in the dict, the script accepts it and logs a `NOTE` prompting the addition rather than firing a retry. If a `NOTE` appears, add the entry to the dict for correctness in future multi-property cases.

**Invocation — Barnstable County:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/legal_desc_fetch.py" \
  --registry barnstable \
  --last "FENWICK" \
  --first "ELEANOR" \
  --base-name "39 Larkspur Road Unit 17C Osterville - Fenwick" \
  --output "${user_config.output_dir}"
```
**`--town` is optional for Barnstable (v3.2+).** The script auto-detects the town from the last alphabetic word of the address portion of `--base-name` (e.g., `"190 Ridgemont Rd Unit 6 Dennis - Bennett"` → `"DENNIS"` → resolves to ALIS code `DENN`). Pass `--town` explicitly only if the auto-detected value would be wrong. Falls back to `BARN` (Barnstable villages) if the town is unrecognized. `--first` is passed as-is (no concatenation needed for Barnstable's separate first-name field).

**Invocation — Norfolk County:**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/legal_desc_fetch.py" \
  --registry norfolk \
  --last "SARNO" \
  --first "ROSA" \
  --base-name "11 Halverson Drive Braintree - Sarno" \
  --output "${user_config.output_dir}"
```
`--town` is **optional for Norfolk (v3.0+).** The script auto-detects the town from the last alphabetic word of the address portion of `--base-name` (e.g., `"11 Halverson Drive Braintree - Sarno"` → `"BRAINTREE"` → resolves to ALIS code `BRAI`). You can also pass an ALIS code directly (e.g. `--town BRAI`, `--town QUIN`, `--town WEYM`) or a town name (e.g. `--town Braintree`). Unknown town names fall back to `*ALL` (all Norfolk towns) with a NOTE in the output — add the entry to `_NORFOLK_TOWN_CODES` in the script when discovered. `--first` is passed as-is (no concatenation needed).

**Norfolk & Barnstable v3.9–v3.28 behaviors (HTTP engine):**

1. **Multi-candidate deed selection (wrong-parcel guard) + auto-retarget (v3.14).** When the grantee search yields more than one distinct conveyance instrument (seller owns multiple same-town properties), the JSON includes `multiple_deed_candidates` — every candidate's index metadata (`book`/`page`, `doc_type`, `recorded_date`, `town`, `doc_desc`, `grantor`, `grantee`, `selected`) plus a downloaded **page-1 sample PDF** per non-selected candidate (`sample_file`) with its extracted address in `sample_extraction`. The script selects the most recently recorded deed, then **v3.14 verifies that pick's extracted address against the street parsed from `--base-name` and fixes a mismatch itself**: if exactly one candidate's `sample_extraction.property_address` matches the subject street, the script re-downloads and re-extracts that instrument in the same invocation, sets `auto_retargeted: true`, demotes the wrong pick back into `multiple_deed_candidates`, and emits an `"AUTO-RETARGETED (v3.14): ..."` note. A `"Address verified: ..."` note means the heuristic pick already matched (single-candidate runs get the same note-only check). **A manual `--book NNNNN --page NNN` (Recorded Land) or `--book <doc number>` (Land Court) re-run is only needed when the notes say zero candidates matched, multiple matched with missing/tied dates, the retarget download failed, no street parsed from the base name, or a candidate remains UNVERIFIED (v3.20)** — in those cases pick via the `sample_extraction` addresses as before. (v3.20: multiple address matches now auto-resolve by recorded date — see item 6.) The retargeted deed's PDFs are saved under `deed_Bk<b>_Pg<p>` (Land Court `deed_Doc<n>`); the wrong pick's files stay on disk. (References: Renwick / 72 Cloverfield Ave Weymouth — heuristic picked the seller's condo Bk 35507/244 over subject Lot 38 Bk 34918/103; v3.14 live-validated 2026-07-16, one-invocation auto-retarget. Brandt Investments LLC / 80 Linden Terrace Marstons Mills 2026-07-13 — 3-way candidate set, would have auto-retargeted but for the manual `--book 37179 --page 69` re-run.)

2. **Inline PDF extraction (v3.10).** On by default: the script sends the downloaded deed PDFs to the Claude API (`claude-opus-4-8`, structured outputs) and returns the extracted fields in the JSON — `legal_description` (verbatim), `signing_date`, `grantors_full`/`grantees_full` (full names + capacity), `tenancy`, `prior_deed_reference`, `title_flags`, `deed_property_address_pdf`, `recording_stamp`, plus fills for `consideration`/`document_number`/`certificate_of_title`. Full detail is under `pdf_extraction.fields`. Candidate page-1 samples get `sample_extraction` (address/lot/grantees) so the wrong-parcel check needs no Read calls. **On success, skip the Read-the-PDFs step entirely** — verify `recording_stamp` matches the selected Bk/Pg and `deed_property_address_pdf` matches the subject property, then go to Step 6. If `extraction_error` is set (missing `ANTHROPIC_API_KEY`, API failure), fall back to Reading the PDFs as before. Opt out with `--no-extract-pdf-text`. Requires `anthropic` pip package + `ANTHROPIC_API_KEY` env var.

3. **Grantor check: paginated + full-name variants + co-owner names from the deed (v3.14).** ALIS paginates results and groups them by the exact indexed name string ("RENWICK, MICHELE D" sorts after every "RENWICK, MICHELE"), so the old page-1-only surname search missed deeds out. The v3.9 check walks pagination (30 rows/page, 5 pages per search; **v3.20:** a capped county-wide search auto-retries scoped to the subject town — see item 6) and runs **multiple searches**: the user-supplied full name, the exact indexed grantee name from the selected deed row (carries middle initial), **every co-owner name parsed from the deed's extracted `grantees_full` (v3.14** — the check now runs *after* PDF extraction; catches a co-owner with a different surname conveying alone, and same-surname co-owners on Land Court where the index shows only one grantee + "(&AL)"; entity/trust grantee names and pairs already covered by an existing search are skipped), and — Recorded Land only — the broad surname-only search (catches same-surname joint owners; e.g. it caught the Fenwick estate deed out indexed under the co-owner's name). On Land Court the broad search is skipped (it buries the seller under namesake noise — Kowalczyk 2026-05-22). **Broad-search hits are filtered to conveyance types only (v3.11)** and to instruments recorded on/after the acquisition date; full-name and co-owner hits are kept regardless of type or date. Each hit in `grantor_check.deeds` ends with `| via: <search>`. (v3.14 live-validated 2026-07-16: Kowalczyk — `KOWALCZYK, MARTA (co-owner from deed)` searched automatically, same-day Mortgage/Homestead correctly deduped, still clean.)

4. **Grantor-hit samples + targeted verification (v3.15).** Grantor-check hits are now fetchable instead of index-strings only. **Auto-sample:** every conveyance-type hit (up to 5, truncation note if more) gets a page-1 sample PDF and a light extraction into `grantor_check.samples` (`property_address`, `lot_or_unit`, `grantors`, `grantees`, plus `sample_file`), and each sampled address is compared to the subject street from `--base-name` — a match emits `"CRITICAL: grantor hit ... conveys the SUBJECT property"` (a real deed-out; stop and report it), a non-match emits a "likely a different parcel" note (assess, don't auto-flag), and **a hit whose sampled address could not be extracted at all emits `"WARNING: grantor hit ... UNVERIFIED"` (v3.20) — never treat that as a different parcel; re-run with the suggested `--verify-grantor-hit` to read the full instrument.** **Targeted verification:** `--verify-grantor-hit BOOK/PAGE` (Land Court: document number) fully downloads and extracts one hit into `grantor_hit_verification` (all pages, full field set incl. legal description, consideration, `prior_deed_reference`) — use it to confirm a suspected deed-out in one invocation instead of ad hoc scripting; combine with `--book/--page` to keep the main deed selection pinned. The hit must appear in the grantor check's own results; if it doesn't, a note lists the hits that were found. (References: Brandt Investments LLC / 80 Linden Terrace Marstons Mills — Bk 36890/431 deed-out to Almeida confirmed via `--verify-grantor-hit`, live 2026-07-16; Renwick — all 5 DEED hits sampled, the 2020 Cardoso deed-out Bk 39044/162 auto-flagged CRITICAL as subject-parcel, the Selkirk St/Tara Dr/Tarrant Dr hits correctly identified as other parcels.)

5. **Speed + report draft (v3.16).** Four latency changes, live-validated 2026-07-16: **(a)** page-1 samples (candidates + grantor hits) extract on a fast model (`claude-haiku-4-5`), with the main model (`claude-opus-4-8`) kept for the main deed and `--verify-grantor-hit`; a sample whose street NAME matches the subject but whose number can't be confirmed is automatically re-extracted with the main model, and the address note has a middle tier — `"POSSIBLE SUBJECT PROPERTY"` — that is never dismissed as a different parcel (treat it as a likely deed-out until verified). **(b)** Pre-acquisition conveyance hits are no longer sampled (they can't convey the subject away; still listed in `grantor_check.deeds`). **(c)** The user-name and broad-surname grantor searches prefetch on a worker thread during extraction (notes say "prefetched during extraction"). **(d)** On success with a populated `legal_description`, the script writes the Step 6 markdown report itself — `report_file` in the JSON points to `Legal Description - [base_name].md` with a DRAFT banner. **Claude's Step 6 job becomes: read the draft, review/adjust the Title Flags section (judgment calls are tagged "review"), remove the DRAFT banner, then proceed to Step 7** — do not compose the report from scratch. An existing report file is never overwritten; if the note says so, update the existing file manually as before.

6. **Unverifiable candidates + capped grantor searches (v3.20).** Two fixes from the Keegan / 402 Sedgefield St Weymouth run (2026-08-10), where the script reported a **superseded** deed at exit 0. **(a) A null sample address is missing information, not a non-match.** The operative 2002 re-vesting deed's page 1 read only "SEE ATTACHED FULL LEGAL" — its address was on an exhibit page the page-1 sample never saw, so the v3.14 retarget silently dropped it and selected the 1998 purchase deed. Now a candidate with no sampled address is **deep-sampled** (first 4 pages, note: `"Candidate ... deep-sampled N page(s); address now: ..."`); if it *still* has no address it is flagged `WARNING`/`CRITICAL` (`"could NOT be address-verified ... NOT ruled out"` — CRITICAL when it is recorded later than the selected deed and could supersede it) — **on that CRITICAL, verify the named candidate with `--book/--page` before reporting anything.** When **multiple** candidates match the subject address they are the same parcel's chain, and the script now selects the **most recently recorded** match (note: `"ADDRESS MATCH xN"`) instead of demanding a manual pick; a candidate whose grantor and grantee are the **same party** gets a re-vesting-deed note (self-conveyance after marriage/trust/tenancy change — routinely supersedes the purchase deed, and the reason a "most recent deed = nominal consideration" pick can be *correct*). **(b) Town-scoped retry when the grantor check caps.** On a common name (Keegan: 150/132/149 rows) every county-wide (`town=*ALL`) grantor search hit the 5-page cap, and a truncated check cannot support a clean-title statement. A capped search now auto-retries scoped to the subject town (cap 20 pages) and **merges** both result sets — the `*ALL` pass is kept (it catches a seller who moved within the county). A complete scoped pass closes the subject-parcel question (a deed-out of the subject parcel is indexed under the subject town); the note says so. If the scoped retry also caps or fails, the JSON gains `grantor_check.incomplete_searches`, the notes say **`"grantor check is INCOMPLETE"`**, and a zero-hit check renders as **CRITICAL — Grantor check INCOMPLETE** in the report instead of "Clean" — **never report clean title from an incomplete check; finish the capped search manually first** (town-scoped `_alis_search_http` via `importlib`, or narrower name variants).

7. **Document Abstract address resolution (v3.22).** The registry's own abstract page carries the property address as text, and the script now consults it **before** any PDF work — for the selected row, every candidate, and every sampled grantor hit. When it names an address, the page-1 download and its vision-model call are both skipped; when `Addr:` is blank, the run falls through to page-1 sampling and, if needed, v3.20 deep sampling. Two consequences worth knowing. **(a) The wrong-parcel guard no longer requires the Claude API** — it was gated on PDF extraction succeeding and now runs whenever any address is available, so it survives `--no-extract-pdf-text`, a missing `ANTHROPIC_API_KEY`, and extraction failure. **(b) Read `deed_property_address_abstract` and `abstract.addresses`** alongside `deed_property_address_pdf`; when both exist they should agree, and a disagreement is worth investigating before closing. The `abstract` object also carries `Doc$` consideration (which fills `consideration` when the index and PDF did not), page count, and `refs` — the `Ref By:` / `Refers to Book:` cross-references to later homesteads, discharges and deeds, which are genuine title signal. Candidates and grantor-hit samples each gain `abstract_addresses` + `abstract_url`. **Caveats:** an absent `Addr:` means UNVERIFIED, never "a different parcel"; multi-parcel deeds list several addresses and any may be the subject; a street name with no number is the "possible subject" tier; Land Court is supported since v3.25 (see item 9). (Live-validated 2026-08-12 on the Keegan run: Bk 15978/412 selected correctly, 4 of 6 candidates and 4 of 5 grantor hits resolved from abstracts with no downloads.)

8. **Grantor-hit classification + parallel searches (v3.23).** The Plymouth v3.21 classifier, ported to ALIS now that v3.22 abstracts supply per-hit addresses (fetched **in parallel**, cap 250 — far beyond the 5-hit PDF-sampling cap, which now only bounds page-1 sampling for blank-`Addr:` rows). The JSON gains **`grantor_check.needs_review`** and **`grantor_check.summary`** in exactly the Plymouth shape — **read `needs_review` first**; `grantor_check.deeds` still lists every hit (nothing is dropped), ordered most-relevant first, each line carrying the abstract address and a parcel tag (`SUBJECT PROPERTY`, `possible subject — ...`, `parcel unknown (no address indexed) — subject town`, `other street, subject town`, `other parcel`, `other town, no address indexed`, plus `| pre-acquisition`). The same v3.20 rules hold: a hit with no abstract address is **parcel-unknown, never "a different parcel"**, and stays in `needs_review` when its town matches or it is a post-acquisition conveyance; the index `Desc` cell can only *escalate* a hit to possible-subject, never dismiss one. A conveyance at the subject parcel emits the same `"CRITICAL: grantor hit ... conveys the SUBJECT property"` note as before; a non-conveyance at the subject parcel emits an encumbrance note (a Homestead is not a deed-out). Entity sellers (no street parseable from `--base-name`): classification is skipped, everything lands in `needs_review`, `summary` is `null`, and a note says so. **Speed:** the v3.20 regression is fixed — capped county-wide grantor searches and their town-scoped retries now run in parallel. **Availability:** a hard-down registry (TCP connection refused) now returns status `registry_unavailable` exactly like the nightly-backup page, on both engines.

9. **Land Court abstracts (v3.25).** The Document Abstract now works for Registered Land: same recording-date + control-number keying, just `WSIQTP=LC09A&WSKYCD=D` (the earlier "keyed by document number" theory was wrong — the ABS icon's href on the results page had the answer all along; the href's extra `W9IMID`/`W9ABR` params are optional). Everything v3.22/v3.23 gate on the abstract simply turns on for Land Court: selected-row address verification (closing the wrong-parcel-guard gap for Registered Land), candidate resolution, grantor-hit parcel checks, and needs_review classification. The LC abstract also carries **`Ctf#`** (fills `certificate_of_title` when the index row lacked it), `Doc date`, consideration, and **`Parent doc:`/`Related doc:` cross-refs** — the parcel's chain, including the prior certificate. Caveats: `Ctf#:` can be non-numeric ("See parent list" on COCs) and is then left null; an absent `Address:` still means UNVERIFIED, never "a different parcel". (Live-validated 2026-08-12 on a Registered Land seller: the post-closing deed-out was auto-flagged CRITICAL from its LC abstract, 4/4 grantor hits abstract-resolved, 29 s.)

10. **Cross-references consumed + abstract-vs-PDF address check (v3.26).** Four code paths collected the registries' cross-reference lists and nothing consumed them; all four now normalise into one top-level **`cross_references`** list — ALIS Recorded `Ref By:`/`Refers to Book:`, ALIS Land Court `Parent doc:`/`Related doc:`, the Plymouth detail-panel References table, and Middlesex South's. Each entry is `{kind, instrument, book, page, doc_number, certificate, date, direction, source, raw}`. **`direction` is the part to act on:** `later` = a subsequent instrument references this deed (the homesteads/discharges/deeds recorded against the parcel afterwards), `earlier` = this deed's prior deed or Land Court parent certificate, `related` = lateral. `kind` buckets the instrument (discharge / homestead / deed / mortgage / death_cert / probate / assignment / lien / plan / taking / notice / other). A line that will not parse is still returned with `raw` set — a dropped cross-reference is the same "missing information read as absence" mistake as v3.20's null addresses. The report gains a **Recorded Cross-References** table. **SCOPE, unchanged and stated in the output: this workflow does not verify discharges.** A discharge-type cross-reference is the index saying such an instrument exists — NOT proof a mortgage was discharged; hand it to a full title rundown. Also new: an abstract-vs-PDF property-address **disagreement** now emits a `WARNING` (both have been reported since v3.22 and always agreed; a disagreement means a misindexed abstract or a wrong-parcel PDF and must not pass silently because one of the two matched).

12. **Deed-group (`*DD`) fallback for a capped grantor search (v3.28).** v3.20 answers a capped search by re-running it scoped to the subject town — but that has nowhere to go when the search is *already* town-scoped, which is the normal case on Barnstable. The check then reported **INCOMPLETE with no path forward**, the exact outcome the v3.20 machinery exists to prevent (Salgado / 87 Marchmont St Hyannis, 2026-08-12: broad surname-only `SALGADO` capped at 150 rows). Document type is the other axis, so a capped search with no usable town retry — or whose town retry also capped — now re-runs restricted to `*DD` (deed group), merged not substituted. **A complete `*DD` pass RESOLVES the cap for a broad surname-only search** (that search keeps conveyance types only, so nothing it would have kept is missing) and the pair leaves `incomplete_searches`. For a **full-name** search it closes only the DEED-OUT question: the pair stays in `incomplete_searches` because that party's mortgages/homesteads/liens may still be truncated, and the note says exactly that. New `grantor_check.deed_group_retries`. Live: capped/150 → complete 36 rows.

13. **Co-owner search names from the registry abstract (v3.28).** The v3.14 co-owner check reads `grantees_full`, i.e. the PDF extraction — so it **silently never ran when extraction failed**, and worse, a co-owner *removed* by the vesting deed is named only on its **grantor** side, where `grantees_full` could never have found them. Salgado: grantee `SALGADO, MARIA TERESA`; grantors `DESALGADO, MARIA ISABEL` + `SALGADO, MARIA TERESA` — the departing party is indexed under a **different surname**, so neither the full-name nor the broad surname-only `SALGADO` search could reach a deed-out by her, and the mortgages she signed on this parcel were invisible too. The abstract lists every party on both sides in index format, needs no API, and is already fetched: grantees are always searched; grantors only when some party appears on **both** sides (the re-vesting / co-owner-removal pattern), so an arm's-length seller is never searched. `result["abstract"]` now carries `grantors`/`grantees`.

14. **Extraction degrades after a failure that will recur (v3.28).** A valid key on an account with **no credit** returns HTTP 400 `"Your credit balance is too low"` for every call. v3.27's pre-flight probe passes — the credentials are fine — so the run made the same doomed call for the main deed and for every candidate sample. **A present key is not a usable key.** The first account/credential-class failure (401/402/403/404, or a 400 naming billing) now latches **`extraction_unavailable`** on the result, and the later extraction sites — the auto-retarget's re-extraction, the grantor-hit page-1 samples, `--verify-grantor-hit` — skip their calls and name the PDFs to Read instead. Transient failures (rate limit, timeout, 5xx) and per-document ones do **not** latch. `extraction_mode` still reports what was resolved pre-flight and `extraction_error` stays set, because this one IS a failure rather than the chosen mode. **When you see `extraction_unavailable`, read the named PDFs — the run's safety output (wrong-parcel guard, auto-retarget, grantor check, classification) is unaffected, exactly as in `claude-code` mode.**

15. **Server-side date window + all-years lien sweep (v3.29).** Every grantor search used to pull the party's **complete index history** and throw the pre-acquisition rows away in Python. Both ALIS registries filter by recorded date server-side (`W9FDTA`, MMDDYYYY, labelled "Date Range (optional)" and **independent of** the `W9INQ=AY` year-index radio, which stays AY), so those rows are no longer fetched at all. The window starts at the acquisition date **less a 7-day lookback**, never at the deed date itself — the purchase-money mortgage and the homestead record the same day, and a recording batch can straddle a day boundary. It applies to the county-wide pass, the v3.20 town-scoped retry and the v3.28 `*DD` retry alike. **This is a cap fix as much as a speed fix:** the broad surname-only search that capped at 150 rows / 5 pages / 33 s on the Salgado name now returns 33 rows / 2 pages / 8.7 s **and is not truncated**, so the INCOMPLETE outcome the `*DD` fallback exists to rescue largely stops arising. What a date window would hide — liens against the **person** that can reach after-acquired property (tax liens, executions, attachments, bankruptcy) — is recovered by a separate **LIEN SWEEP**: document group `*LN`, **no date restriction**, full-name pairs only (the broad surname search keeps conveyance types anyway). Sweep hits are labelled `| via: … (lien sweep, all years)`. New JSON: **`grantor_check.search_window`** (from / lookback_days / basis) and **`grantor_check.lien_sweep_truncated`** — a capped sweep is tracked **separately from `incomplete_searches`** on purpose, because it asks a narrower question than the deed-out check and must not flip a clean report to CRITICAL. An unknown acquisition date disables the window entirely (all years) rather than guessing one. **Also fixed here: a grantor search that ERRORED used to append a note and drop through, so a run in which every search failed reported "no subsequent instruments found — clean title" at exit 0.** Errored searches now land in `incomplete_searches` with a note saying the name was not searched.

16. **Ownership can change with NO deed — and three things used to hide it (v3.39, item 22).** A **death certificate** vests a survivor by operation of law; a **trustee certificate** changes who signs; a **taking** or **decree** can divest or vest. v3.38 added `_instrument_significance` to surface exactly these, and on ALIS it could not see them, because **ALIS Land Court indexes a GENERIC document type — `CERTIFICATE`, `AFFIDAVIT`, `DOCUMENT` — and puts the instrument's real nature in the `Desc` cell** ("DEATH OF <name>", "AFFIDAVIT NO DIVORCE"). Significance now reads **type + Desc** (substrings only; the exact-code vocabulary stays keyed on the type, since Desc is staff-typed text that may ESCALATE a hit but never dismiss one). Two more fixes landed with it. **(a) A placeholder address is NOT an address.** The registry writes a literal **`Addr: N/A`** rather than leaving the field blank, and that string was being consumed as a real, non-matching address — silently demoting a row from `parcel unknown` (kept) to `other street, subject town`. `N/A`, `NONE`, `UNKNOWN`, `SEE RECORD` and friends now read as *no address*, which is the v3.20 rule applied one layer out. **(b) On Registered Land the Certificate of Title number is an EXACT parcel key, and it now outranks every address.** A grantor hit whose `Ctf#` equals the selected deed's `Ctf#` is tagged **SUBJECT PROPERTY** with no abstract fetch at all; a *different* certificate is positive evidence of a different parcel; a **missing** certificate on either side asserts nothing and falls through to the address/town logic. **What this means when you read a Land Court run:** the `Ctf#` on each hit line is the parcel answer — trust it over the `Addr:` field, and treat a subject-certificate hit as at the subject parcel even when its address is absent or reads `N/A`. (Live origin: a Norfolk Land Court run where the named seller had **died**, title had passed to his spouse by entirety survivorship with no deed recorded, the deed-out check was correctly clean, and the death certificate was demoted out of `needs_review` by all three defects at once.)

**How to read the kinds of hit — this is where a false flag gets made:**
- `via: <LAST>, <FIRST>` — **the seller.** These are her instruments; her own mortgages, homesteads, and liens come through here (they are *not* type-filtered).
- `via: <LAST>, <FIRST> (co-owner from deed)` (v3.14) — **a co-owner named on the vesting deed itself.** Their subsequent instruments affect this parcel's title exactly like the named seller's (a co-owner can convey or encumber their interest alone); assess them the same way, not as strangers.
- `via: <LAST>, <FIRST> (co-owner from abstract)` (v3.28) — the same thing, sourced from the registry abstract instead of the deed PDF, so it is present even when extraction failed or was never enabled. Assess identically.
- `via: <LAST>, <FIRST> (prior co-owner from abstract)` (v3.28) — **a co-owner the vesting deed REMOVED** (named on its grantor side, often under a variant or maiden surname). Only emitted when the deed is a partial self-conveyance, so this is not the arm's-length seller. Their post-acquisition instruments still matter: an encumbrance they signed while on title runs with the parcel, and a conveyance by them before the removal deed is a genuine title question.
- `via: <LAST>, <I>* (deed-out net, deed group)` (v3.38) — **the deed-out net.** Surname + first INITIAL, restricted server-side to the deed group, run for EVERY known owner. It exists to catch a conveyance indexed under an initial (`SMITH, J`) or a misspelled first name — both platforms prefix-match, so a full-name search reaches `PENN`→`PENNE` but never `PENN`→`P`. Its hits **may be same-surname strangers** — verify the grantor's first name before flagging one. It replaced the old always-on surname-only pass, which returned 150-190 rows to keep ~25 and was essentially the whole grantor-check runtime. **What it does NOT rescue: a misspelled SURNAME** (use the address search) or an unknown same-surname co-owner with a different initial.
- `via: <LAST> (surname only — FALLBACK: ...)` (v3.38) — the **full** surname-only pass, fired **only** when no owner first name was available (no abstract, extraction failed, entity seller). Read it like the net above, but expect more strangers.
- `via: ... (surname only)` — **a deed-out safety net, nothing else.** Its only job is to catch a conveyance indexed under a co-owner's or name-variant's spelling (Fenwick: the estate deed out was indexed under the co-owner). Since v3.11 these are conveyance types only, but they **may still be same-surname strangers** — verify the grantor's first name and the property description before flagging one. **Never report a surname-only row as the seller's own encumbrance.** (Reference: 11 Halverson Dr, Braintree, 2026-07-12 — a Citizens Bank MORTGAGE at Bk 43196/88 belonging to *Louis* Sarno was reported as a critical open mortgage on seller *Rosa* Sarno. The v3.11 type filter now drops it at the source, but the first-name check is still yours to make.)

Since v3.23 the classification (item 8) does most of this assessment for you — the parcel tag on every hit line answers the which-parcel question and `needs_review` collects the rows that need judgment; the v3.15 `grantor_check.samples` extractions still answer the stranger-vs-seller question for the sampled subset (the sampled grantor names). The checks above remain yours for `parcel unknown` rows and wherever a name, not a parcel, is the question.

**Scope discipline.** This workflow answers exactly three questions: (1) the legal description from the latest deed *to the named seller*, (2) that the seller is the latest grantee / current owner of record, (3) that the seller has not deeded the property out as grantor. Discharges are **not** verified here — do not present the seller's pre-acquisition mortgages/liens as cleared or as flags; report them as out of scope for this workflow, to be resolved by a full title rundown. This applies equally to the v3.26 `cross_references`: a discharge-type entry is a registry index cross-ref, i.e. a LEAD, and reporting it as a discharged mortgage would be exactly the overreach this rule exists to prevent.

**Invocation — Middlesex South (v3.8):**
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/legal_desc_fetch.py" \
  --registry middlesex-south \
  --last "TREVISAN" \
  --first "CLAUDIA" \
  --base-name "55 Verona Street Medford - Trevisan" \
  --output "${user_config.output_dir}"
```
- `--first` is passed as-is (separate first-name field, like ALIS registries — no Plymouth-style concatenation).
- No `--town` needed or used: the Middlesex South grid has **no Town column**. The street number/name auto-parsed from `--base-name` stands in for town when disambiguating multi-property sellers (grid's Street # cell holds the full street, e.g. `"10 ASHGROVE PL"`).
- **A visible Chrome window opens during the run.** masslandrecords.com sits behind Incapsula bot protection, which 403s all headless browsers (the GET succeeds; the search POST is blocked). The script auto-launches headful real Chrome (`channel="chrome"`) regardless of the headless default. Don't interact with the window while the run is in progress.
- Entity sellers: same pattern as Plymouth — full entity name in `--last`, `--first ""`.

*Middlesex South fields (v3.8; grantor check v3.32):*
- `book`, `page`, `recorded_date`, `deed_type` — from results grid; `deed_type` is spelled out (DEED / MORTGAGE / DISCHARGE), so the non-conveyance filter uses the ALIS substring vocabulary
- `document_number`, `consideration`, and page count — from the detail panel. **Caveats for pre-computerization records (~pre-1986):** consideration is often blank (read the excise stamp on the deed image instead) and Doc # may be a synthetic index number — cite Bk/Pg, not Doc #, for old records
- `deed_property_address` — the grid's Street # cell (street only; no town)
- `grantor_check.deeds` — **no Reverse Party column on this registry**, so the counterparty is blank in every hit; assess by type/date/street, and open the deed image or detail panel for the grantee of any DEED-type hit
- **`grantor_check.searches` + `incomplete_searches` (v3.32)** — the same per-search accounting as ALIS/Plymouth, and read it the same way: `rows_returned > 0, rows_new: 0` = searched, all duplicates; `rows_returned: 0` = searched, nothing indexed; `status` starting `ERROR` = **that name was NOT searched** — it lands in `incomplete_searches`, the notes say the check is **INCOMPLETE**, and you must never report clean title from that run. Co-owner searches come from the detail panel's grantee list, labelled `(co-owner from detail panel)` — assess their hits exactly like the named seller's. Co-owner first names are searched as their first token only (the first-name field is a prefix match, so the bare token is a strict superset; the first live run of this fix surfaced 40 instruments under the co-owner's name that the full first-name query could never have returned). **Still no classification on this platform:** every hit arrives unclassified and unordered — the parcel and stranger questions are yours, and the seller/co-owner searches prefix-match, so same-name strangers appear even in named-seller hits
- `notes` includes a `"Detail panel references"` line — the registry's cross-reference list (discharges, death certificates, related deeds), which often pre-answers discharge-verification questions
- Registered Land (Land Court) is NOT searched — on `deed_not_found`, check Middlesex South Registered Land manually before concluding no deed exists

`--base-name` uses the standard file-naming format: `[Address] - [Seller Last Name]`.

**Exit codes and fallback behavior:**

| Exit code | Meaning | Action |
|---|---|---|
| `0` | Success — deed found and files downloaded | Use JSON output; run Step 1C address check before proceeding to Step 6 |
| `2` | Deed not found in Recorded Land | Run Step 1C (Land Court check) before falling back to manual Steps 2–5 |
| `1` + status `registry_unavailable` | Registry offline — nightly backup / periodic maintenance page (v3.17) **or hard-down, connection refused (v3.23)** — Norfolk & Barnstable | **STOP — do not fall back to anything.** See "Registry maintenance window" below |
| `1` (any other status) | Error (script failure, selector mismatch, etc.) | Check the JSON `status` field first, then fall back to manual Steps 2–5; if those also find no deed, run Step 1C |

**Registry maintenance window (`registry_unavailable`) — stop, don't fall back:** The ALIS registries go offline during a nightly backup window and serve a tiny HTTP 200 maintenance page ("...currently unavailable due to nightly backup or periodic maintenance") in place of every page — search results, Land Court, image lists, PDFs. **v3.23:** the same status now also covers a **hard-down registry** — TCP connection refused/failed on the final retry (previously a generic exit-1 `error`) — because the handling is identical: retry later, conclude nothing. Before v3.17 both engines parsed this as zero rows and returned a **false `deed_not_found`** (reference: Laura Bennett / 190 Ridgemont Rd Dennis Port, 2026-07-16 ~11:30 PM ET — seller's deed Bk 37211/188 exists but every search variation returned exit 2). When you see this status:

1. **Stop the search entirely.** Do NOT run the Step 1C Land Court check, manual Steps 2–5, or the Barnstable fallback URL — every path hits the same maintenance page, and the dangerous outcome is a plausible-looking "no deed found for the named seller" conclusion on a real closing file. Never report "no deed found" from a run that saw this status.
2. **Tell the user and let them choose:** defer (rerun the skill when the registry is back — morning ET is the reliable answer), or poll — re-run the script every ~10–15 minutes, capped at ~3 attempts, then give up and defer. Never poll silently past the cap.
3. **Still log the run (Step 8)** with `deed_found: null` and an issue like `"registry offline — nightly backup window, run aborted"`. Over time these entries map each registry's actual backup window.
4. **Timing:** MA registry nightly backups fall somewhere in the ~11 PM–6 AM ET band (Barnstable confirmed ~11:30 PM ET, 2026-07-16). Runs started late evening should expect this status.

**Fallback for Barnstable (Steps 2–5):** Navigate directly to the grantee search results URL rather than filling the form:
```
https://search.barnstabledeeds.org/ALIS/WW400R.HTM?W9SNM=[LAST]&W9GNM=[FIRST]&W9IXTP=E&W9ABR=*ALL&W9TOWN=[TOWN]&W9INQ=AY&W9FDTA=&W9TDTA=&AYVAL=%2B1742&CYVAL=2015&WSHTNM=WW401R00&WSIQTP=LR01LP&WSKYCD=N&WSWVER=2
```

**On exit 0 — reading the JSON output:**

*Plymouth fields (v2.8):*
- `book`, `page`, `document_number`, `recorded_date`, `deed_type`, `consideration` — use directly
- `deed_property_address` — street + town as indexed in the registry results grid; use to confirm the correct property was selected
- `found_via_address_search` — `true` if the deed was located via property address search (either as the primary method or as an automatic town- or street-mismatch retry); `false` if found via grantee name search
- `found_via_compound_surname` — `true` if the deed was located via the v3.5 hyphenated/compound-surname retry (surname-only search after the combined name search returned nothing). When `true`, confirm the selected grantee's surname is the full hyphenated name (e.g. `WHITFIELD-BARROW`) and that the first name matches.
- **`selected_row_is_not_a_deed` (v3.12; ALSO ON NORFOLK/BARNSTABLE SINCE v3.36)** — `true` when the finally-selected instrument is NOT a conveyance deed (e.g. an ASSIGNMENT or MORTGAGE), meaning no DEED-type row for the property was found in either the grantee name index or the address index. **When `true`, STOP: do not extract a legal description and do not report the instrument as the vesting deed.** Check Registered Land (Land Court) and check for a misindexed grantee name. A matching `"CRITICAL: ..."` note is also emitted. **v3.36 adds two things:** the ALIS registries now set this flag too — they never had the guard, and their row selector falls back to the unfiltered rows when everything is excluded, so a non-conveyance could be reported as the vesting deed there with no warning at all; and an **UNRECOGNISED** type now trips the flag on every platform (previously an unknown type was assumed to be a conveyance and sailed through). The two cases are worded differently — `"is a 'MORTGAGE', NOT a conveyance deed"` vs `"has an UNRECOGNISED type '...' — the script cannot confirm it is a conveyance deed"` — because they call for different follow-up: the first means look elsewhere, the second means read the instrument.
- **`results_truncated_at_cap` (v3.18)** — `true` when the registry truncated the search at its **1000-row server-side cap**. **The cap is applied BEFORE the Rec Date sort**, so the rows the script read are *not* the most recent ones and any newer instrument — including the vesting deed — never reached the browser. **When `true`, treat the run as UNVERIFIED regardless of the exit code: do not report a deed selected from that result set.** The script still returns exit 0 and still populates `book`/`page` (flagging was kept separate from selection deliberately), so this flag is the only thing standing between you and a plausible wrong-parcel deed. The flag is sticky — it stays `true` even if a later address-search retry ran clean. A matching `"CRITICAL: the registry TRUNCATED this search ..."` note is also emitted. See the municipality-seller section below.
- **`detail_references` (v3.24)** — the detail panel's References cross-ref list (later homesteads, discharges, death certificates, related deeds recorded against the selected deed). Same data as Middlesex South's detail-panel References and the ALIS `abstract.refs`; genuine title signal — surface it in the report's notes and hand it to the discharge workflow. Also echoed as a `"Detail panel references"` note.
- `notes` — contains raw result row text and detail panel text; read to verify address and extract names. Includes:
  - `"Name search: filtered N non-deed row(s) before selection: [...]"` — non-conveyance types stripped before row selection
  - `"CRITICAL: the registry TRUNCATED this search at its 1000-row server-side cap"` (v3.18) — see `results_truncated_at_cap` above
  - `"WARNING: no name-search result matched town '...'"` — seller owns multiple Plymouth County properties (multiple result rows); address-search retry was triggered
  - `"WARNING: name-search selected row street '...' does not match expected street '...'"` (v3.12) — town matched but the street did not; seller owns multiple properties **in the same town**; street-mismatch address-search retry was triggered
  - `"NOTE: town abbreviation '...' not yet in _PLYMOUTH_TOWN_ABBREVS"` — single result, unknown abbreviation, accepted without retry; add entry to dict
  - `"Address search (town mismatch retry): selected ..."` / `"Address search (street mismatch retry): selected ..."` — confirms which deed the retry chose and which signal fired
  - `"CRITICAL: the selected instrument is a '...', NOT a conveyance deed"` (v3.12) — see `selected_row_is_not_a_deed` above
- **`grantor_check.needs_review` (v3.21; membership rule refined v3.37)** — the short set of grantor hits that actually need judgment, pulled out of a list that runs to the dozens on a common name. A hit is here when it is at (or cannot be excluded from) the subject parcel, **or** when it is a conveyance-type instrument recorded on/after the acquisition date **that could not be positively located at another parcel**. **Read this first.** `grantor_check.deeds` still contains every hit — nothing is dropped — now ordered most-relevant first with a parcel tag appended to each line.
  - **What v3.37 changed and why it is narrow:** a post-acquisition conveyance used to enter the review set regardless of parcel, so on a common surname the broad surname-only pass filled it with other people's property (one live run: 47 of 48 rows). A hit is now held back **only on a TOWN mismatch, and only when a town was actually indexed.** Everything else stays: **same-town rows are never demoted** (same-town is exactly where the wrong-parcel traps in this workflow live — a seller with two properties in one town, or a street whose suffix the index ignores), and a row with **no address and no town is never demoted** — that is missing information, not evidence of a different parcel.
  - **Nothing is hidden.** Demoted rows stay in `grantor_check.deeds` with their parcel tag, are counted in **`summary.demoted_located_elsewhere`**, and the summary note states how many were held back and why. **If that count is high and the review set is small, the check did more work, not less** — but you can still read the full list. Treat a small `needs_review` as trustworthy only alongside `grantor_check.searches` (which names the searches behind it).
- **`grantor_check.summary` (v3.21)** — counts by parcel tier: `total`, `needs_review`, `pre_acquisition`, `subject`, `possible_subject`, `unknown_same_town`, `other_same_town`, `other_parcel`, `other_town`. `null` when classification was skipped (no street parsed from `--base-name`, e.g. an entity seller) — in that case `needs_review` contains every hit and a note says so.
- **Instrument classification is THREE-WAY (v3.36)** — every hit carries `classification.instrument_class`: `conveyance` | `non_conveyance` | `unknown`. This is the tier that decides which note you get, and the middle one is new:
  - `conveyance` at the subject parcel, post-acquisition → the **CRITICAL deed-out** note. Unchanged; this is still the finding the whole check exists for.
  - `non_conveyance` at the subject parcel → the **encumbrance** note. If the type is a **TAKING**, the note now adds that a taking *can divest title* (tax taking / eminent domain) — do not treat it as a mere encumbrance like a mortgage or homestead.
  - `unknown` → **`WARNING: … has UNRECOGNISED type '<TYPE>' at the SUBJECT property — not classified`**. The script does not know this type and says so instead of guessing. **Read the named instrument and decide yourself** — it is one line to read rather than the browser verification trip a false CRITICAL used to force. Unknown hits stay in `needs_review` and are never dropped. When you resolve one, the type belongs in the script's vocabulary so the next run classifies it.
  - **Why it matters for what you REPORT:** an unrecognised type is no longer reported as a deed-out (it used to be — a solar UCC-continuation was flagged as a possible sale of the subject parcel), and equally it is never silently dropped from the deed-out check. `unknown` means *unclassified*, not *harmless* and not *dangerous*.
- **`grantor_check.searches` (v3.30)** — one entry per search actually run: `{name, rows_returned, rows_new, status}` (Plymouth adds `label`; ALIS adds the skipped-row counts). **This is the evidence behind a "clean" verdict, and you need it before writing one.** Hits are de-duplicated across search names and tagged with the *first* search that found them, so on a co-owned parcel where both owners signed everything, every hit line reads `via: <named seller>` and the co-owner's pass leaves no trace in the hit list at all. Read the three outcomes literally:
  - `rows_returned > 0, rows_new: 0` — the name **was** searched; every row was already found under an earlier name. Clean for that name.
  - `rows_returned: 0` — searched, nothing indexed under that name.
  - `status` starting `ERROR` — the search **did not run**. That name is an OPEN question; never report it as clean. It also appears in `incomplete_searches`.

  If a co-owner you expect to see is absent from this list entirely, the name was never derived — say so in the report rather than implying it was checked.
- `total_pages_in_viewer` — total deed pages
- `files` — list of downloaded JPG paths

**v2.7–v2.8 — Key behaviors (Plymouth name search path):**

1. **Python-based date sort.** After reading result rows, the script sorts them by recorded date descending in Python — replacing the prior book-number sort validation, which was unreliable for Plymouth County's digitized old records (where book numbers are non-monotonic with date, e.g. a 1978 deed at Bk32450 alongside a 2002 deed at Bk22572).

2. **Town-aware row selection.** `_select_best_row` now applies the town filter even when results are date-sorted (previously, `prefer_first=True` skipped the filter entirely). If a seller owns multiple Plymouth County properties, the most recently recorded deed for the *correct town* is selected rather than the most recently recorded deed overall.

3. **Auto town detection.** `--town` is auto-populated from `--base-name` if not passed (last alphabetic word before ` - `, e.g. `"Scituate"`). The script uses this for both row selection and the mismatch retry below.

4. **Town-mismatch address-search retry.** If the name search selects a deed whose town doesn't match the expected town AND street info is available (auto-parsed from `--base-name`), the script automatically retries using the property address search — without requiring a second manual invocation.

4b. **(v3.12) Street-mismatch address-search retry — same-town multi-property sellers.** The town filter cannot disambiguate a seller who owns **several properties in the same town**: every candidate row matches the town, so the most-recently-recorded deed wins regardless of which parcel it conveys. v3.12 adds a street-level check on top of the town check. `_select_best_row()` now takes a `street_filter` (the street-name word parsed from `--base-name`) and prefers rows whose Street cell names that street; if the finally-selected row still names a different street while the town matches, the script fires the **same** address-search retry as the town-mismatch path and notes `"street mismatch"` as the trigger. Unlike the town check, this fires even on a single-row result (one row naming a different street is a real wrong parcel, not an unknown-abbreviation artifact). Falls back safely: if no row names the expected street, the town-only set is used, so this can only disambiguate, never zero out a result. Only active when a street name parses from `--base-name` — entity/trust sellers behave exactly as before. (Reference: Peter Grant, 2026-07-13 — subject property 18 Kestrel Ave, Hingham; the name search selected a DEED for 23 Harrowgate Dr, Hingham, both town `HNGHM`, so the v2.7 town check never fired and the wrong parcel was returned with exit 0 and no warning.)

4d. **(v3.13) Pagination — the results grid was only ever page 1.** The Avenu grid defaults to **20 rows/page**, and every Plymouth read stopped after the first page, so on a busy seller or busy street the older instruments — including the vesting deed — were simply invisible. Live proof 2026-07-13: a grantee search for `GRANT PETER` reports **122 rows**; the script saw **20**. (The v3.7 "pager walk" that was supposed to prevent this never ran — it looked for standard ASP.NET `Page$N` GridView links, which this grid does not use. Its real controls are `DocList1$PageView100Btn` and `DocList1$LinkButtonNext`.) The grantee search, both address-search retries, and the grantor check now switch to 100 rows/page and follow **Next** to the last page. Two order-of-operations rules were learned the hard way and are now enforced: **(a) set page size BEFORE sorting** — the 100/Page postback re-renders from the default index order and discards the Rec Date sort; **(b) wait on grid CONTENT, not on selectors** — every control is an UpdatePanel postback and the *old* grid keeps satisfying `ctl02 exists`/networkidle, so the previous waits returned while stale rows were still on screen. Expect a `"Pager walk: read N row(s) across M page(s)"` note. **The grantor check is now complete rather than truncated, so it can return many more hits for a common name** (the Grant run went from 37 to 213) — assess them by grantor first name, date, and property as the workflow already requires.

4e. **(v3.13) Rec Date sort is server-side and global — and its direction is now validated correctly.** Clicking the "Rec Date" header sorts the **entire result set** on the server, not just the visible page (confirmed live: with the sort applied, page 1 is strictly newer than page 2). That makes it a genuine tool for reaching the newest or oldest instrument in a large result set. Note the prior direction check compared **book numbers** (`ctl02 < ctl03`) to infer asc/desc — but Plymouth book numbers are **non-monotonic with date** (v2.7's own finding), so it could not tell the two apart and reported "descending applied" on an ascending grid. Direction is now validated by reading the **Rec Date** column itself.

4c. **(v3.12) Final-selection conveyance guard.** The v3.3 misindexed-name fallback only guards the *name*-search path, so any row reached via an address search (the new street-mismatch retry, `--force-address-search`, or the trust/LLC fallback) could report a non-conveyance instrument as the vesting deed with exit 0 and no warning — the address-row filter falls back to "using all rows" when the address has no DEED-type row. A path-independent check now runs on the final selection and sets `selected_row_is_not_a_deed: true` plus a `CRITICAL` note. **Honor it — do not extract a legal description from a flagged instrument.** (Same Grant run: the retry correctly reached 18 Kestrel Ave, but the address index held only MTG/DISCHARGE/ASSIGNMENT rows — no DEED — so an ASSIGNMENT was selected. A vesting deed absent from *both* indexes usually means Registered Land or a misindexed grantee name.)

4f. **(v3.18) Server-side truncation — the municipality-seller trap.** The registry caps a search at **1000 rows server-side**, and applies the cap **before** the Rec Date sort. The date sort therefore only reorders the *oldest* 1000 rows, and every newer instrument is invisible. Because the cap is applied server-side, page 10 legitimately has no **Next** link, so the pager walk terminates by exactly the same signal as a genuine last page — the pre-existing `capped` warning only fires when Next *still exists* at max_pages, so it stayed silent. The script now sets **`results_truncated_at_cap: true`** plus a `CRITICAL` note on either the site's own banner ("limited to the first 1000 records") or a row count reaching 1000. The flag is **sticky** across a later address-search retry.

   **This is the failure mode with no other guard.** The town filter, street filter, and `selected_row_is_not_a_deed` all test rows that were *returned* — none can see that the set was truncated before sorting, and old municipal rows have an empty `addr` cell so the street check has nothing to compare. (Reference: Town of Hingham / 319 Halstead Street, 2026-07-28 — a grantee search on the Town returned exactly 1000 rows whose newest was from **1981**, ~870 of them town-wide `TKG`/`TAKING`/`NOTC`/`ESMT`. From the remainder the script selected a genuine DEED, Bk 4102/519, Bouvé family → Hingham Town Of, 6/27/1980 — an unrelated parcel — at exit 0 with no warning of any kind.)

   **When the seller is a municipality, city, town, housing authority, or any other high-volume party, do not trust the name-search path at all.** Note also that a town is typically indexed under **both** orderings (`TOWN OF HINGHAM` *and* `HINGHAM TOWN OF`); neither form alone is sufficient. Go straight to `--force-address-search --street-number N --street NAME`. If the address index yields no DEED row (Plymouth's address index only covers recently e-indexed instruments, so a pre-2000s chain often has none), **trace from the prior record owner instead**: an MLC, tax lien, or 6(d) certificate recorded at the address names the then-owner and usually cites the prior deed Bk/Pg on its face — run *that* party as the search name and read its grantor check. Then check Plymouth Registered Land (Land Court), which the fast path does not search.

5. **"155R" street number support.** `_parse_street_from_base_name` now accepts rear-lot street numbers like `"155R"`, `"12A"` (regex `^\d+[A-Za-z]{0,2}$` instead of `.isdigit()`), enabling the address-search fallback for rear-lot properties.

6. **(v2.8) Town abbreviation dictionary.** `_town_matches_filter()` replaces the bare `tf in t or t in tf` substring check. Handles vowel-stripped abbreviations like `HLFX` (Halifax) and `DXBY` (Duxbury) that are not substrings of the full town name. Dictionary (`_PLYMOUTH_TOWN_ABBREVS`) is extensible — add new entries as observed from live runs.

7. **(v2.9) Single-result mismatch no longer triggers retry.** If the name search returns exactly one result and its town abbreviation isn't in the dict, the script accepts the row and logs a `NOTE` rather than firing the address-search retry. The retry is now gated on `len(all_rows) > 1` — it only fires when there is genuine multi-property ambiguity. This eliminates false retries caused by unknown-but-correct abbreviations (e.g. `PLMTH` before it was added to the dict).

8. **(v3.5) Hyphenated / compound-surname retry.** Plymouth's name search uses a single combined `LASTNAME FIRSTNAME` field with prefix matching, so a partial surname on a hyphenated name fails: `"WHITFIELD ALAN"` does not prefix-match the index entry `"WHITFIELD-BARROW ALAN D"`. When the combined name search returns 0 results, the script now retries with the **surname only** (blank first name) — `"WHITFIELD"` prefix-matches `"WHITFIELD-BARROW ..."` — then filters the returned rows by the seller's first-name token so an unrelated same-prefix surname is not selected. Runs *before* the trust/LLC address-search fallback and sets `found_via_compound_surname: true`. **Limitation:** this only recovers the case where the supplied last name is the **leading** component of the hyphenated surname. Supplying a **trailing** component (e.g. `"Barrow"` for `Whitfield-Barrow`) still cannot be found via the name index — and may silently match an *unrelated* person with that exact name — so if unsure which part is the leading surname, confirm the full surname or run an address search. (Reference: 14 Fernwold St, Hingham — Alan Whitfield-Barrow, Bk 58120/377.)

9. **(v3.21) Grantor-hit classification — the common-name pile.** The Plymouth grantor check ran unfiltered and unordered, so a common seller name buried the rows that mattered. (Reference: James Merrick / 52 Kingsbury Rd, Hingham, 2026-08-12 — `MERRICK JAMES` returned **93 instruments**, roughly forty of them 1870s Hull deeds belonging to a 19th-century namesake, spanning 1762–2026; exactly three touched the subject parcel and none was a conveyance. All 93 had to be read by hand.) The ALIS conveyance-type and pre-acquisition-date filters (v3.11/v3.16) are now ported here — and are **stronger on Plymouth**, because this grid carries a street + town cell per row, so the parcel question is answered straight from the index with no PDF sampling (the ALIS index has no address at all, which is why v3.15/3.16 must download page-1 samples to ask the same thing).

   **Nothing is dropped.** Plymouth runs full-name searches only (named seller + each grantee off the deed), and per the ALIS rule a full-name hit is kept regardless of type or date — the seller's own mortgages, homesteads and liens arrive through exactly those searches. Hits are classified and ordered instead. Each line in `grantor_check.deeds` gains a parcel tag: `SUBJECT PROPERTY`, `possible subject — street name matches, number unconfirmed`, `parcel unknown (no address indexed) — subject town`, `other street, subject town`, `other parcel`, `other town, no address indexed`, plus `| pre-acquisition` where applicable. **A row with no indexed address is never treated as a different parcel on that basis alone** — it is only deprioritised when its *town* also differs (the v3.20 Keegan lesson: missing information is not a non-match).

   **What to read:** `grantor_check.needs_review` first (5 rows instead of 93 on the Merrick set), then the tagged full list if anything looks off. A conveyance at the subject parcel recorded on/after acquisition emits **`"CRITICAL: grantor hit ... is a conveyance-type instrument at the SUBJECT property"`** — that is the deed-out this check exists to find, so stop and verify it. A non-conveyance at the subject parcel emits an encumbrance note instead, so a Declaration of Homestead is not mistaken for a deed-out. Entity/trust sellers with no street parseable from `--base-name` fall back to pre-v3.21 behaviour: everything unclassified in `needs_review`, with a note saying so.

10. **(v3.29) Server-side date window + all-years lien sweep.** The same change as ALIS item 15 above, with Plymouth's own mechanics. The **Recorded Date From/To** boxes and the **Document Types** listbox live on the **Advanced** panel (`SearchFormEx1_BtnAdvanced`): they exist in the DOM and are posted either way (`ACSTextBox_DateFrom` is prefilled with the index floor, `8/6/1686`), but Playwright will not fill a hidden input, so the panel is opened on demand. **Only the grantor check uses them — the grantee search is untouched.** Live result: `GRANT PETER` went from **218 rows reaching back to 1704** to **41**, with `grantor_check.needs_review` **byte-identical at 19 rows**, and the windowed pass runs 3× faster (6.9 s → 2.2 s) of which the sweep gives back about half. **The lien sweep needs BOTH of Plymouth's parallel document-type vocabularies.** The `100xxx` range holds the terse codes the results grid actually displays; the `301xxx` range holds spelled-out names for the same concepts; they are *different options* and selecting one does not select the other. The first cut of `_PLYMOUTH_LIEN_DOC_TYPES` took `301058 BANKRUPTCY` and missed **`100021 BKCY`** — the code this seller's four bankruptcy filings (1990/1995/1999/2001) are actually indexed under — so the sweep ran, returned two attachments, and silently no bankruptcies. **A sweep that quietly misses the thing it exists to find is worse than no sweep:** pair every concept across both ranges when extending the list, and check a live name known to have the instrument type.

**v2.6/v3.6 — Non-conveyance type filter (name search path):** Plymouth County indexes some instruments (notably DIS — discharge of mortgage) with the homeowner as grantee, so a grantee name search can return discharges alongside deeds. The script strips these before selecting the best row. Excluded types: `DIS`, `MTG`, `REL`, `ASST`, `TKG`, `NOTC`, `BKCY`, `DCLN HMS`, `ASSIGN`, `LIEN`, `ATTACH`. **v3.6 additions:** `REL` (release), `ASST` (assignment), `TKG` (taking), plus compound terse codes like `DIS REL` — a multi-token code is non-conveyance when every token is a known non-conveyance code. (Reference: KDM Realty Corp, 545 Whitmore St Marshfield, 2026-07-08 — a Rockland Trust `REL` was selected as the "deed" before this fix.) If all rows are excluded (rare), the script falls back to the unfiltered set rather than returning exit 2.

**v3.6 — Atomic grid snapshot (fixes chimera rows).** The results grid is now read in a single `page.evaluate()` call, repeated until two consecutive snapshots match. The prior per-cell `query_selector` loop (~90 round trips) could interleave with the ASP.NET UpdatePanel re-render triggered by the date-sort header click, producing a "chimera" row — Book/Page cells from the pre-sort grid glued to Type/Date/Doc# cells from the post-sort grid. (Reference: same KDM run — DEED Doc#41886 was reported at Bk46013/Pg9; actual Bk8827/Pg315, confirmed against the recording stamp on the deed image.) The grantor check uses the same atomic reader. **Always sanity-check the reported Book/Page against the deed image stamp** — the image margin/stamp is authoritative.

**v3.6 — Grantor check improvements.** (1) Rows are deduplicated per (book, doc#) instead of per book, so multiple instruments in one recording batch (e.g. MTG + MLC + assignments recorded together) are all reported. (2) The original-deed skip now requires a doc-number match when available — the old book-only skip hid a same-day purchase-money mortgage recorded in the same book as the vesting deed. (3) **v3.7:** the row reader now captures all rendered grid rows (up to 50, was capped at 10) and walks ASP.NET `Page$N` pager links if the registry paginates larger result sets — previously the oldest instruments on long-held properties were silently dropped (KDM Realty Corp, held since 1989: the 1989 purchase-money MTG, 1994 assignment, 1995 Commonwealth taking, and a 1997 NOTC were all beyond row 10 and invisible until this fix; live run 2026-07-08 confirmed 14 hits). Note: the Avenu grid renders ≥14 rows on one page with no pager, so the pager walk is defensive — no pager has been observed live yet.

*Barnstable fields (v2.3):*
- `book`, `page`, `ctl_num`, `recorded_date`, `deed_type` — use directly; `document_number` and `consideration` are `null` (extract from PDFs via Read tool)
- `grantors`, `grantees` — from results table (grantee name may include `(&H)`, `(&W)`, `(&O)` suffixes indicating joint ownership — flag for closing)
- `deed_property_address` — the Document Description field from the results table (e.g. "UNIT 17-C BLDG D"); use as a secondary address check, not primary
- `land_court` — true if deed was found in Land Court rather than Recorded Land
- `grantor_check.has_subsequent_deed` + `grantor_check.deeds` — v3.9: paginated, full-name variants + broad surname search with pre-acquisition date filter; see the v3.9 behaviors above
- `total_pages_in_deed` — number of PDF pages downloaded
- `files` — list of downloaded PDF paths (not JPGs — Barnstable serves PDFs)

*Norfolk fields (v3.0):*
- Same shape as Barnstable — Norfolk runs identical Browntech ALIS software and shares the same `_alis_*` helpers internally.
- `book`, `page`, `ctl_num`, `recorded_date`, `deed_type` — use directly; `document_number` and `consideration` are `null` (extract from PDFs via Read tool — `document_number` appears as `#NNNN` on the recording cover-sheet header)
- `grantors`, `grantees` — from results table (single value each in the Norfolk index; suffixes like `(TR &AL)` indicate trustee with additional parties — flag for closing and read PDFs for full party detail)
- `deed_property_address` — the Document Description field; often just `"SEE RECORD"` rather than a real address. Treat as low-signal — but see `deed_property_address_abstract` below, which usually *does* carry a real address.
- **`deed_property_address_abstract` + `abstract` (v3.22)** — the address (and `Doc$` consideration, page count, grantor/grantee lists, and `refs` cross-references) read off the registry's Document Abstract page. This is structured index data, available with no PDF download and no API call. Cross-check it against `deed_property_address_pdf`; they should agree.
- `land_court` — true if deed was found in Land Court rather than Recorded Land
- `grantor_check.has_subsequent_deed` + `grantor_check.deeds` — Norfolk's grantor check uses `town=*ALL` (catches subsequent deeds even if seller moved to another Norfolk municipality). v3.9: paginated, full-name variants + broad surname search with pre-acquisition date filter (see the v3.9 behaviors above); Claude must still assess each hit by grantor name, date, and property description.
- `total_pages_in_deed` — number of PDF pages downloaded
- `files` — list of downloaded PDF paths
- `notes` — town-resolution note appears at index [0] if the user-supplied town was unrecognized and fell back to `*ALL`.

**Shared ALIS PDF link behavior (v3.1) — Barnstable and Norfolk:**
- **Primary path:** Document Image List is scanned for the numbered-page pattern `[PREFIX]NNNN.PDF` (e.g., `DUIP0001.PDF`, `DB3R0001.PDF`). Multi-page deeds use this pattern.
- **Permissive fallback (v3.1+):** If the numbered pattern matches 0 links but other `.PDF` links exist on the page, the script downloads them instead. This handles non-standard short single-file naming (e.g., `/WwwImg/D1UJ.PDF` observed on a 1988 Foxborough deed, Bk7906/Pg271) where the entire deed is in one PDF with no page-number suffix. When the fallback is used, the `notes` array includes a line starting with `"Document Image List: numbered-page pattern matched 0 links; using permissive fallback"`.
- **Exit-1 recovery fields (v3.1+):** If the script cannot download any PDFs (no links found, or all downloads failed), the JSON output adds two top-level keys:
  - `image_list_url` — the full URL of the Document Image List page the script reached
  - `all_pdf_hrefs_on_image_list` — every `.PDF` href found on that page (even ones that don't match the numbered pattern)
  These let Claude fetch the PDFs directly via the browser without re-navigating from the search results — typically saves 6–8 browser tool calls per recovery.

**After a successful Barnstable or Norfolk run:** If the JSON has populated `legal_description`/`pdf_extraction` (v3.10 inline extraction succeeded), use those fields directly — no Read calls needed; just sanity-check `recording_stamp` against the selected Bk/Pg and confirm `deed_property_address_pdf` matches the subject property (v3.14 does this address check itself — look for the `"Address verified"` / `"AUTO-RETARGETED"` / `"ADDRESS MISMATCH"` note and the `auto_retargeted` field, and only intervene on a MISMATCH note). Only if `extraction_error` is set (or the run used the Playwright engine): Read all PDFs with the Read tool to extract the legal description, document number, consideration, signing date, and full grantee names. The Read tool handles ALIS PDFs natively (multimodal). **v3.28: if `extraction_unavailable` is also set, the API failed in a way that would recur (no credit, bad key, revoked model access), so the run deliberately stopped calling it — the notes name every PDF that went unextracted, including candidate and grantor-hit samples. Read those too; nothing else about the run is degraded.**

**Address match check (required before proceeding to Step 6):** After reading the deed PDFs, confirm that the address in the granting clause or left-margin notation matches the expected property address. If they do not match — or if the deed is clearly for a different parcel (different lot number, different street, etc.) — **run Step 1C before producing any output.** Do not proceed to Step 6 with a mismatched deed. This check is especially important for Norfolk County, where `deed_property_address` in the JSON is the Document Description field (often `"SEE RECORD"` or `"LOT N"`), which gives no address confirmation until the PDF is read.

**Supported registries:** Plymouth (v3.29, with grantor-hit classification and the server-side date window + lien sweep), Barnstable + Norfolk (v3.29 HTTP engine with inline PDF extraction, auto-retarget by extracted address incl. deep-sampled/recency-ranked candidates, co-owner grantor check **sourced from the registry abstract's party lists on both sides** with parallel town-scoped **then deed-group** cap retries **and needs_review classification**, grantor-hit samples/verification, and script-generated report draft; Playwright fallback), Middlesex South (v3.8), and **Suffolk (v3.41)**. Suffolk is the only fast path that searches **Registered Land (Land Court) as well as Recorded Land** — it switches the site's Office dropdown and selects across the combined candidates, because a Land Court parcel's vesting deed is invisible to a Recorded Land search. It is browser-only (Incapsula blocks scripted requests), applies **no town filter and no date window** (both were measured silently suppressing rows — see the script's Suffolk module note), and cites Land Court instruments by Document No. + Certificate of Title, never Book/Page. It also falls back automatically to an **address (Property) search in both offices** when the name search finds no conveyance on the subject street — the answer to a misindexed seller name and to the registry's prefix-matched First Name box; `--force-address-search` skips the name pass entirely. An address hit carries no party name, so it is reported as NOT name-verified and the grantee must be confirmed on the deed image.

**Suffolk v3.41 — the registry's own messages, and what they mean for what you report.** Two of them, both previously discarded, both landing on the same wrong answer:

- **`"limited to the first 1,000 records"` = the search was CAPPED and returned ZERO rows.** Read literally by code waiting for a grid, that is indistinguishable from "this party has nothing indexed" — which in a grantor check is the difference between *no deed out* and *we never looked*. **Never report clean title from a capped search.** The run says so itself: the office's status is `capped`, a `CRITICAL` note names it, and the search lands in `grantor_check.incomplete_searches`.
- **The cap has a second, SILENT shape.** A search landing exactly on the limit returns **1,000 rows and no message**, caught only by the row-count check that sets `results_truncated_at_cap`. Both shapes were seen on one name in one run. **`results_truncated_at_cap: true` means the rows you were given are a partial set** — the same rule as Plymouth v3.18.
- **`"Search criteria resulted in 0 hits"` = genuinely nothing indexed**, and is now believed immediately instead of after a 45-second wait. This is the one case where zero rows really does mean zero.

**The grantee and grantor searches are now ONE search per office** (`Party Type = Both`), with each row tagged `GT`/`GR`. Consequences when reading the JSON: `offices_searched[].mode` reads `name (Both)` and carries a `grantor_rows` count, and the seller's own entry in `grantor_check.searches` shows `"ok (from combined name search)"` per office. **That is a search that ran, not one that was skipped** — its rows are the `GR` half of the combined result. A `capped` or failed office is never prefetched this way; it is searched again and reported as incomplete if it still caps.

**`--deliver-text-file` no longer re-runs the search (v3.41).** It reads the run's own `result.json`, applies your transcribed text, and writes the three paste forms — about 2.5 s instead of a second full registry pass. The result carries `delivery_only_reentry: true` and a note saying every registry field came from the earlier run. If you actually need fresh registry data, re-run without the flag.

---

### Step 1C — Land Court Check (Norfolk & Barnstable)

**When to run:**
0. **Registry Profile says `"section": "registered"`** (see Step 1 profile check) → run FIRST as the primary search, before any Recorded Land fast path; verify the result against the stored Certificate of Title #
1. **Fast path exit 2** — no deed found in Recorded Land → run immediately before trying manual Steps 2–5
2. **Fast path exit 0, address mismatch** — deed PDFs read in Step 6 preparation show a different street address than the expected property address → run before producing any output
3. **Fast path exit 1 + manual Steps 2–5 also find no deed** → run as a last check

**Why this is needed:** The Playwright fast path searches Recorded Land only. Roughly 10–20% of Massachusetts properties are Registered Land (Land Court). When a seller owns both a recorded and a registered parcel in the same town, a grantee name search will return the recorded parcel — successfully, with exit 0 — while the registered parcel goes undetected. The address mismatch in the deed PDF is the only signal. (Reference: Kilbride / 29 Fox Meadow Road, Norfolk County, 2026-06-02 — script returned exit 0 for Lot 26 / 7 Thornbury Lane; the correct property was Land Court Ctf 174905.)

**Norfolk County — Land Court grantee search (navigate directly to this URL):**
```
https://www.norfolkresearch.org/ALIS/WW400R.HTM?W9SN8=[LAST]&W9GN8=[FIRST]&W9IXTP=E&W9ABR=*ALL&W9TOWN=[TOWN_CODE]&W9FDTA=&W9TDTA=&WSHTNM=WW401L00&WSIQTP=LC01LP&WSKYCD=N&WSWVER=2
```
Use the same town code as the Recorded Land search (e.g., `COHS`). If no results, retry with `W9TOWN=*ALL`.

**Barnstable County — Land Court grantee search:**
```
https://search.barnstabledeeds.org/ALIS/WW400R.HTM?W9SN8=[LAST]&W9GN8=[FIRST]&W9IXTP=E&W9ABR=*ALL&W9TOWN=[TOWN_CODE]&W9FDTA=&W9TDTA=&WSHTNM=WW401L00&WSIQTP=LC01LP&WSKYCD=N&WSWVER=2
```

**Reading Land Court results:**
- Results grid shows: Certificate #, Town, Date Recvd, Document Type, Document Desc, Doc #
- Click the **ABS** icon on the most recent DEED row — the abstract shows the full street address, grantor/grantee names, and consideration
- Confirm the abstract address matches the expected property address before proceeding
- If it matches, click **View/Prt** to open the Document Image List

**Downloading PDFs:**
- Get PDF hrefs from the Document Image List via JavaScript (same fetch-download approach as Recorded Land — see Norfolk technical notes)
- Land Court PDF prefix varies by recording batch (`DM5N`, `D05D`, etc.) — always read actual href values from the page; do not hardcode
- Use the Read tool on downloaded PDFs to extract the legal description, which appears in full on page 1

**If no deed found in Land Court either:** Confirm the property is truly Recorded Land and proceed with manual Steps 2–5 for the Recorded Land index.

**After a confirmed Land Court deed:** Proceed to Step 6 with these metadata values:
- Section = `Registered Land`
- Book/Page = N/A
- Certificate of Title = certificate number from abstract
- Document # = document number from abstract
- All other fields as extracted from the deed PDF

---

### Step 2 — Search for Seller as Grantee

Search the Registry for the Seller as **Grantee** (the person who received ownership). Goal: find the deed by which the Seller acquired the property.

Match results against the property address. If multiple results, select the most recent deed where the Seller is Grantee and the address matches.

---

### Step 3 — Grantor Check (Title Flag)

After finding the Seller-as-Grantee deed, check whether the Seller subsequently conveyed the property as Grantor.

**Shortcut on ALIS systems (Norfolk, Barnstable) — name search path only:** If the deed was found via a Grantee name search, the results page shows a "Reverse Party" column (the Grantor for each result row). Scan the full results list — if the Seller appears as Grantor in any later deed for the same property, that is visible right on the Grantee results page. In that case, the Grantor check is already complete and no separate Grantor search is needed. Only run a separate Grantor search if the Grantee results do not clearly show a subsequent conveyance.

**If the deed was found via address search:** The Grantee name search results page was never shown, so the Reverse Party shortcut is not available. A separate Grantor name search is always required in this case.

- **If Seller appears as Grantor in a later deed for the same property:**
  - Third-party grantee → **Critical flag** — potential serious title issue, report prominently
  - Trust or LLC the Seller controls → less critical, but note it
  - Co-owner added (self-transfer for nominal consideration, typically one dollar) → flag: additional party must sign at closing
- No subsequent deed → clean, note it

---

### Step 4 — Extract Legal Description

From the identified deed, extract the full legal description text (typically follows the granting clause, precedes the signature block). When in doubt, capture more text rather than less.

**Registered Land (Land Court) — required index fields:** For any deed found in the Registered Land / Land Court section, you must capture both of the following from the deed or the search results index:
- **Certificate of Title** — the primary index identifier under the land registration system; this is the more important of the two fields. It typically appears as "Certificate of Title No. XXXXX" on the deed face or in the registry index.
- **Document Number** — the document number assigned by the Land Court to this deed (distinct from Book/Page, which does not apply to registered land).

Both fields appear in the Deed Metadata section of the markdown report. Do not leave either blank for a registered land deed.

**Property address from deed:** In addition to the legal description, capture the property address as it appears on the deed. Check these locations in order, and use the clearest and most complete version found:
1. **Left margin notation** — the address is frequently written vertically (bottom-to-top) in the left margin of the first deed page. Read this from the deed image (screenshot or PDF) since it is a handwritten or stamped notation outside the main body text.
2. **Granting clause** — language such as "situated at [address]," "known and numbered as [address]," or "known as [address]" in the body of the deed.
3. **Cover sheet or header** — electronically recorded Suffolk deeds (both offices) open with a recording cover sheet (page 1) that carries Document Number, Book/Page or "Noted on Certificate", and consideration; older paper filings have none. Never assume page 1 is or is not a cover sheet — read it. Some registries stamp the address at the top or bottom of the first page.

If multiple sources agree, record the address once. If they conflict, record the most specific version and note the discrepancy.

---

### Step 5 — Capture Deed Screenshots

Save deed page images as `.jpg` to the output folder. See registry-specific technical notes below for capture methods.

---

### Step 6 — Save Markdown Report

Write the `.md` file to the output folder using the structure above.

**Fast-path shortcut (v3.16, Norfolk/Barnstable HTTP engine):** if the script JSON contains `report_file`, the report draft already exists — Read it, review/adjust the Title Flags section (items tagged "review" are judgment calls; verify grantor-hit assessments against the `via:` guidance above), remove the DRAFT banner, and save. Do not write a new file from scratch.

---

### Step 7 — Deliver the Legal Description

**Fast-path shortcut (v3.19):** on a successful script run this step is
already done. The JSON's `txt_file` points to the three-form `.txt`
(verbatim / paste-ready / paste-ready + derivation clause),
`legal_description_paste_ready` holds the reflowed text, and — per the
delivery flags — `clipboard_copied` / `docx_file` report the clipboard and
Word copies. Your job shrinks to: report the paste-ready text in the
conversation so it can be copied without opening a file, and mention the
file paths (and that it is on the clipboard, if it is). An existing `.txt`
is never overwritten; if a note says so, update the existing file manually
only if the selected deed actually changed.

**Write the `.txt` yourself only when the script didn't** — the manual
Steps 2–5 path, or a "delivery failed (non-fatal)" note in the JSON. It
contains the three forms described under **Outputs**, and is what the user
actually pastes into a deed, an affidavit, or their closing platform, so it
is the deliverable that matters most.

Reflow rules for the paste-ready form (**conservative — whitespace only**):

- Join hard-wrapped lines into one paragraph; collapse runs of spaces.
- Rejoin words split by a line-break hyphen (`prop-\nerty` → `property`).
  Keep genuine hyphens inside words.
- Normalize curly quotes/dashes to plain ASCII equivalents.
- Preserve every word, number, bearing, distance, and abbreviation exactly as
  recorded. Do **not** correct spelling, expand abbreviations, fix apparent OCR
  errors, or re-punctuate. If something looks wrong, flag it in the report and
  leave the text alone.

Then report the paste-ready text in the conversation so it can be copied
without opening a file. If `copy_to_clipboard` is on, it is already on the
clipboard; if `write_docx` is on, mention the `.docx` path.

---

### Step 8 — Log the Run

Record the end timestamp:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/run_clock.py" end
```

This prints the elapsed time against the Step 1 start file.

**Log aborted runs too.** A run that ends early because the registry was offline (`registry_unavailable`) still gets an entry: `deed_found: null`, no output files, and an issue like `"registry offline — nightly backup window, run aborted"` with the time observed. These entries accumulate into a map of each registry's real backup window, which informs when unattended runs are safe to schedule.

Append a new entry to `${user_config.output_dir}/legal_description_run_log.json`. If the file does not exist, create it with the structure `{"log_description": "Legal Description Search Workflow run log", "runs": []}` before appending. Check existing entries to find the next run number for today (`YYYY-MM-DD-NNN`); if no runs exist for today, start at `001`.

The log never leaves this machine. It contains property addresses and seller
names, so it is written only to `output_dir` and is never transmitted anywhere.
Logging is optional — skip this step entirely if it isn't wanted.

```json
{
  "run_id": "YYYY-MM-DD-NNN",
  "data_source": "live",
  "date": "YYYY-MM-DD",
  "timestamp_start": "ISO-8601 UTC",
  "timestamp_end": "ISO-8601 UTC",
  "elapsed_minutes": 0.0,
  "property_address": "...",
  "seller_name": "...",
  "entity_type": "individual | LLC | trust | other",
  "registry": "...",
  "registry_system": "...",
  "registry_url": "...",
  "deed_found": true,
  "book": "...",
  "page": "...",
  "document_number": "...",
  "certificate_of_title": "...",
  "deed_property_address": "...",
  "deed_type": "...",
  "consideration": "...",
  "title_flag": false,
  "title_flag_description": null,
  "outputs": {
    "markdown_report": true,
    "page1_image": true,
    "page2_image": true,
    "legal_description_txt": true,
    "pages_total_in_deed": 0,
    "pages_auto_saved": 0,
    "pages_not_saved_note": null
  },
  "browser_tool_calls": 0,
  "issues": [],
  "notes": "..."
}
```

---

## TECHNICAL NOTES BY REGISTRY

Per-registry mechanics — form field names and POST shapes, town codes, PDF
href patterns, pager behaviour, WAF and viewer quirks — live in one reference
file per registry, listed below.

**Read the file for the registry you are working before any manual or
fallback step in that registry.** The script fast path (Step 1B) does not
need them; they matter when you are driving a registry by hand, debugging a
failure, or working a registry the fast path does not cover.

They are split out because they are *lookup* detail: needed only once you are
already in that registry, and their absence is self-announcing — without the
field name or town code you visibly cannot proceed, so you come and get it.

**What is deliberately NOT in them:** anything that changes what you
*report* or *conclude*. Those rules stay in this file. If you ever find
yourself reaching for a reference file to decide whether a title is clean,
whether a parcel matches, or whether a search was complete, stop — that
answer belongs here, and its absence here is a bug.

| Registry | Reference file |
|---|---|
| Plymouth County — titleview.org/plymouthdeeds/ | `${CLAUDE_PLUGIN_ROOT}/skills/legal-description/references/plymouth.md` |
| Suffolk County — masslandrecords.com/suffolk/D/Default.aspx | `${CLAUDE_PLUGIN_ROOT}/skills/legal-description/references/suffolk.md` |
| Middlesex South District — masslandrecords.com/MiddlesexSouth/D/Default.aspx | `${CLAUDE_PLUGIN_ROOT}/skills/legal-description/references/middlesex-south.md` |
| Norfolk County — norfolkresearch.org | `${CLAUDE_PLUGIN_ROOT}/skills/legal-description/references/norfolk.md` |
| Barnstable County — search.barnstabledeeds.org | `${CLAUDE_PLUGIN_ROOT}/skills/legal-description/references/barnstable.md` |
| *All 21 districts* — platform / entry point / WAF triage (not a per-registry mechanics file) | `${CLAUDE_PLUGIN_ROOT}/skills/legal-description/references/registry-platform-triage.md` |

### Registry facts that change what you REPORT — these stay here

Three rules were pulled back out of the reference files above, because each
one ends in a conclusion about title or parcel rather than in a mechanical
step. They are registry-specific but they are not lookup detail: you would
need them at exactly the moment nothing prompts you to open a reference file.

**Plymouth — multi-property sellers (v2.7):** When a seller owns multiple
Plymouth County properties, the grantee name search returns results for all
of them. The v2.7 script handles this automatically via Python date sort +
town-aware selection + address-search retry. If the script's JSON shows
`"deed_property_address"` for the wrong town and `"found_via_address_search":
false`, the town filter found no match and fell through to the most recent
deed regardless of town — **read the deed image to confirm before
proceeding.** The `notes` array will contain a `"WARNING: no name-search
result matched town"` entry in this case.

**Norfolk — "EST." suffix in the Name column, meaning unconfirmed:** Search
results sometimes display a name as `SARNO, THOMAS (EST.&AL)` or `TURNER,
JEAN (EST.&AL)` in the **Name** column. The meaning of this `EST.` suffix as
displayed in the Norfolk ALIS name index is **not yet confirmed** — do not
assume it indicates the named person is deceased or that it refers to their
estate. Research is ongoing. Until the meaning is established, treat `EST.`
in the Name column as an unknown qualifier and do not draw title conclusions
from it alone. (Note: `EST.` appearing in the **Document Type** column —
e.g., "ESTATE DEED" — is a separate matter and refers to the instrument
type.)

## PERFORMANCE NOTES

- **Typical elapsed time (Playwright fast path):** 3–5 minutes on Plymouth, Norfolk, and Barnstable; **~16 seconds on Suffolk** (v3.41, measured; was ~70 s at v3.40 — the difference is almost entirely the empty-search timeout, not the searches themselves). Manual fallback paths run 15–30 minutes on well-behaved registries. The old 45–70+ minute Suffolk figure described the manual browser path and no longer applies to `--registry suffolk`.
- **Playwright fast path (Plymouth, Norfolk, Barnstable):** When the script succeeds, Steps 2–5 run in ~60–180 seconds of unattended Playwright automation instead of 15–20 minutes of browser tool calls. Expected end-to-end time: 3–5 minutes (Step 1 + Playwright + Step 6 + Step 7 + Step 8). For Plymouth, the town-mismatch retry adds ~30–60 seconds when the seller owns multiple Plymouth County properties. Norfolk and Barnstable both use shared `_alis_*` helpers and behave identically performance-wise.
- **Browser tool calls (token proxy):** Target under 50 per run on ✅ Ready registries. First runs on new registries will exceed this. Playwright runs consume ~0–5 browser tool calls total (the Playwright script itself does not count — it's invoked via Bash) vs. 30–60 for the full manual path.
- **Image resolution (Suffolk):** the ~217×281 px figure described the on-page render, not what the fast path saves. The script rewrites the `ACSResource.axd` request to `CNTHEIGHT=2000` and saves a **1542×2000** JPEG per page (measured 2026-08-18) — fully legible.

**Benchmark runs (as of May 2026):**

| Registry | Runs | Avg. Elapsed | Notes |
|---|---|---|---|
| Plymouth County | 6 | ~20 min (manual); ~35 min (v2.7 two-pass); ~13 min (v2.8 two-pass); ~3–5 min (single-pass) | v2.7 two-pass (155R Seabright Rd, Scituate): wrong deed selected, script updated mid-run. v2.8 two-pass (192 Silver Birch Dr, Halifax): HLFX abbreviation bug triggered false mismatch on first run; re-run with `--town HLFX` workaround; script fixed to v2.8 resolves automatically. Normal single-pass: ~3–5 min. Latest single-pass run (11A Talbot Dr, Hull): 2.7 min. |
| Norfolk County | 5 | ~18.5 min avg (manual: 25 min run 1; 11.9 min run 2); **3.05 min (v3.0 fast path, run 3)**; run 4: exit 0 wrong deed + 17 min Step 1C correction; **v3.10 HTTP engine + inline extraction: 25–65 s single-shot** (Kowalczyk Land Court 25 s; Renwick multi-candidate 65 s incl. candidate address extraction; targeted --book re-run 55 s) | Run 3 (11 Halverson Dr Braintree, Sarno): first live test of `--registry norfolk`, exit 0, auto-derived `BRAI`, 4 PDFs. Run 4+5 (29 Fox Meadow Rd Cohasset, Kilbride): fast path exit 0 returned Lot 26 / 7 Thornbury Lane (different Kilbride parcel); Step 1C Land Court check found correct property as Ctf 174905 / Doc 1183426. Reference case for Step 1C address-mismatch trigger. |
| Barnstable County | 3 | ~15 min (runs 1, 3); ~50 min active (run 2); **v3.10 HTTP engine + inline extraction: 28 s single-shot** (Fenwick live test 2026-07-11) | Run 2: Land Court, PDF.js hung. Run 3: fetch-download + Read tool, no abstract page, 12.9 min — current best manual. v3.9 HTTP test also surfaced the 2026-06-17 Fenwick→Ashcroft deed out (Bk 38025/396) via the broad-surname grantor search. |
| Suffolk County | 3 | ~66 min (run 1, manual); **~60-70 s (v3.40, run 2)**; **~16 s (v3.41, run 3)** | Run 2 (15 Larkspur Road, Boston — Hollister): first live `--registry suffolk`, **Registered Land**, exit 0, Doc 812445 noted on Ctf 198332, 3 hi-res pages; grantor check surfaced the same-day purchase-money mortgage (Doc 812446) and homestead (Doc 812447). This run also caught three defects: a prefix-matched first name (`JULIAN`→`HOLLISTER JULIANA`) selecting another party's parcel, a silent Office-switch race returning Recorded Land rows labelled as Land Court, and the town/date filters suppressing rows. Run 3 (Recorded Land condo unit, 2026-08-20): v3.41 — the combined `Party Type = Both` search halved the registry searches (4 to 2) and the grantor check consumed the `GR` rows with no extra query, but the real cost was elsewhere: an EMPTY search sat out the full 45 s grid timeout, so a seller with no Land Court records paid ~28 s per search averaged over four. Consuming the registry's own "0 hits" dialog took the run from ~70 s to ~16 s with identical findings. The same probe also found the 1,000-record cap returning zero rows and being read as "nothing indexed". |
| Middlesex South | 1 | **3.3 min (v3.8 fast path, first live run)** | Run 1 (531 Fieldstone Brook, Acton — Ostrander): exit 0 first try, 3 hi-res pages, detail-panel References surfaced a 2022 death cert + 2024 complaint automatically. Headful Chrome (Incapsula) worked unattended. |
