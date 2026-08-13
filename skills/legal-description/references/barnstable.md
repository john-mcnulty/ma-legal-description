# Barnstable County — search.barnstabledeeds.org

Registry mechanics for the `/legal-description` workflow.
Split out of SKILL.md; the workflow steps and every reporting rule live there, not here.

**System:** Browntech ALIS — **identical to Norfolk County** (shares the `_alis_*` helpers in `legal_desc_fetch.py`)

**Playwright fast path (v2.3+):** Barnstable is supported by `legal_desc_fetch.py` — see Step 1B. The manual notes below apply only when the script returns exit 2 or exit 1.

**Search URL:** `https://search.barnstabledeeds.org/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N`

**PDF file prefix (Recorded Land):** Varies by recording batch — do NOT hardcode. Always read the actual href values from the Document Image List page links before fetching. Known prefixes seen: `DX26`, `DN6D`. The pattern is `[PREFIX]0001.PDF`, `[PREFIX]0002.PDF`, etc.

**PDF file prefix (Land Court / Registered Land):** `D05D` (e.g., `/WwwImg/D05D0001.PDF`, `/WwwImg/D05D0002.PDF`). Land Court search URL: `https://search.barnstabledeeds.org/ALIS/WW400R.HTM?WSIQTP=LC01D&WSKYCD=N`. Always try Recorded Land first; if no results, switch to Land Court.

**Common town codes:** `BARN` = Barnstable — and since v3.28 the **village names themselves** (Hyannis, Hyannisport, Centerville, Osterville, Cotuit, Marstons Mills, West Barnstable, Cummaquid) resolve to `BARN` directly, so a Hyannis address no longer emits an "unrecognised town" NOTE on a run that was correctly scoped all along. `BOUR` = Bourne, `BREW` = Brewster, `CHAT` = Chatham, `DENN` = Dennis ✓, `EAST` = Eastham, `FALM` = Falmouth ✓, `HARW` = Harwich, `MASH` = Mashpee ✓, `ORLE` = Orleans, `PROV` = Provincetown, `SAND` = Sandwich ✓, `TRUR` = Truro, `WELL` = Wellfleet, `YARM` = Yarmouth ✓. **`--town` auto-detection (v3.2+):** `legal_desc_fetch.py` now resolves Barnstable towns from `--base-name` automatically (same as Norfolk). Omit `--town` and the script derives the code from the last town word in the address. Falls back to `BARN` if unrecognized. For unlisted towns, use the JS query `Array.from(document.querySelector('[name="W9TOWN"]').options).map(o=>o.value+'='+o.text)` on the search form page.

**USE the abstract page for the property address (v3.22) — this guidance was previously the opposite:** The Document Abstract page (`WSIQTP=LR09A`, `WSKYCD=B`, keyed by recording date + control number) carries a **`Town:` / `Addr:` field giving the property address as plain text**, which the results grid does not (its Document Desc is often just `SEE RECORD` or `LOT N`). The old rule here said to skip this page because Bk/Pg, date, parties and page count are available elsewhere — an enumeration that missed the address, the one field that answers the wrong-parcel question. The script now fetches it automatically for the selected row, every candidate, and every sampled grantor hit, and only falls back to downloading a page-1 PDF when `Addr:` is blank. Doing this by hand in a manual run is one navigation, and it is cheaper and more reliable than reading a scan: it is structured index data, so it has no null-address failure mode on deeds whose first page only says "SEE ATTACHED FULL LEGAL" (Keegan Bk 15978/412 — the v3.20 defect). The abstract also gives `Doc$` consideration, page count, full grantor/grantee lists, and `Ref By:` / `Refers to Book:` cross-references to later homesteads, discharges and deeds. **Caveats:** `Addr:` is frequently absent (an absent address means UNVERIFIED, never "a different parcel"); a multi-parcel deed lists several `Town:`/`Addr:` pairs and any of them may be the subject; some entries carry a street name with no number, which is the "possible subject" tier, not a dismissal; and it is staff-typed index data, so the deed image remains authoritative for the legal description itself. Land Court abstracts use the same date+ctl keying with `WSIQTP=LC09A&WSKYCD=D` (v3.25) — own label vocabulary (`Address:`/`Descr:`/`Grantor:`/`Grantee:`/`Consideration:`/`Ctf#:`, with `Address:` PRECEDING `Town:`), plus `Parent doc:`/`Related doc:` chain cross-refs.

**Capture method — preferred (fetch-download + Read tool):** Stay on the Document Image List page. Read the actual PDF hrefs from the page links, then fetch each page using the correct prefix. Save each page as a `.pdf` to the output folder, then use the `Read` tool to extract content. Registry authentication is preserved via the page session.

**CRITICAL — blob worker required if using PDF.js fallback:** barnstabledeeds.org blocks cross-origin Web Worker scripts. CDN-based `workerSrc` silently fails — `page.render().promise` never resolves. Required fix before calling `getDocument()`:
```javascript
const wr = await fetch('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js');
const wt = await wr.text();
pdfjsLib.GlobalWorkerOptions.workerSrc = URL.createObjectURL(new Blob([wt], {type:'text/javascript'}));
```
NEVER set `workerSrc = ''` — runs PDF.js on main thread, permanently blocks JS event loop. Only run one render per tab; multiple pending renders share the worker and may deadlock.

**Unique:** Barnstable County charges both Massachusetts State Excise Tax AND a Barnstable County Excise Tax — unique among MA counties.

**Corporate/LLC search:** Enter full or partial LLC name in `W9SNM` (Last Name/Corporation field), leave `W9GNM` blank.
