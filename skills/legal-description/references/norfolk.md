# Norfolk County — norfolkresearch.org

Registry mechanics for the `/legal-description` workflow.
Split out of SKILL.md; the workflow steps and every reporting rule live there, not here.

**System:** Browntech ALIS

**Playwright fast path (v3.0+):** Norfolk is supported by `legal_desc_fetch.py` — see Step 1B. Use the fast path first; only fall back to the manual notes below if the script returns exit 2 (deed not found) or exit 1 (script error). The fast path uses the same shared `_alis_*` helpers as Barnstable (Norfolk and Barnstable run identical Browntech ALIS software).

**Town codes:** Each Norfolk municipality has its own ALIS code (unlike Barnstable's BARN which covers all villages). Full list enumerated 2026-05-16 from the `W9TOWN` dropdown on the LC01D form — codes appear to be shared between Recorded and Land Court forms (✓ = confirmed on a live Recorded Land run):

| Code | Municipality | Code | Municipality |
|---|---|---|---|
| `AVON` | Avon | `NORF` | Norfolk |
| `BELL` | Bellingham | `NRWD` | Norwood |
| `BRAI` | Braintree ✓ | `PLNV` | Plainville |
| `BRKL` | Brookline | `QUIN` | Quincy ✓ |
| `CANT` | Canton | `RAND` | Randolph |
| `COHS` | Cohasset | `ROXB` | Roxbury |
| `DEDH` | Dedham | `SHRN` | Sharon |
| `DORC` | Dorchester | `STOU` | Stoughton |
| `DOVE` | Dover | `WALP` | Walpole |
| `FOXB` | Foxborough ✓ | `WELL` | Wellesley |
| `FRKL` | Franklin | `WROX` | West Roxbury |
| `HLBK` | Holbrook | `WSTD` | Westwood |
| `HYDE` | Hyde Park | | |
| `MEDF` | Medfield | `WREN` | Wrentham |
| `MDWY` | Medway | `WEYM` | Weymouth ✓ |
| `MILS` | Millis | | |
| `MLTN` | Milton | | |
| `NDHM` | Needham | | |

Weymouth: **`WEYM` confirmed live 2026-07-09** (Renwick run — `WEYB` returns zero rows *silently*, no error message). The script's `_NORFOLK_TOWN_CODES` already maps WEYMOUTH→WEYM; do not pass `WEYB`.

For any unlisted municipality, pass the ALIS code directly via `--town` and the script will use it as-is, or pass the town name and the script will fall back to `*ALL` with a NOTE.

**Recorded Land search URL:** `https://www.norfolkresearch.org/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N`

**Recorded Land form fields:**
- `W9SNM` — Last Name
- `W9GNM` — First Name
- `W9IXTP` — Party type: `A` = All, `R` = Grantors, `E` = Grantees
- `W9ABR` — Doc type: `*ALL` = all, `*DD` = deed group
- `W9TOWN` — Town code (see table above)
- `W9INQ` — Date range: `AY` = All Years

**Land Court search URL:** `https://www.norfolkresearch.org/ALIS/WW400R.HTM?WSIQTP=LC01D&WSKYCD=N`

**Land Court form fields (different from Recorded Land — use these field names for LC searches):**
- `W9SN8` — Last Name
- `W9GN8` — First Name
- `W9IXTP` — Party type: same values as Recorded Land
- `W9ABR` — Doc type: same values
- `W9TOWN` — Town code: same codes as Recorded Land
- Results page hidden fields: `WSHTNM=WW401L00`, `WSIQTP=LC01LP`

**Land Court direct search URL (name search):**
```
https://www.norfolkresearch.org/ALIS/WW400R.HTM?W9SN8=[LAST]&W9GN8=[FIRST]&W9IXTP=E&W9ABR=*ALL&W9TOWN=[TOWN]&W9FDTA=&W9TDTA=&WSHTNM=WW401L00&WSIQTP=LC01LP&WSKYCD=N&WSWVER=2
```

**Image viewer:** NOT a popup. Navigates to Document Image List page with links to individual page PDFs:
- Individual pages: prefix varies by recording batch — do NOT hardcode. Always read the actual href values from the Document Image List page links before fetching (e.g., `/WwwImg/DB3R0001.PDF`, `/WwwImg/DB3R0002.PDF` — prefix `DB3R` seen in February 2020 recording). The pattern is `[PREFIX]0001.PDF`, `[PREFIX]0002.PDF`, etc.
- **Exception — short/non-standard filenames:** Some deeds (observed on a 1988 Foxborough deed, Bk7906/Pg271) use a short filename with no page-number suffix (e.g., `/WwwImg/D1UJ.PDF`). The entire deed is in a single file with no `0001` suffix. **v3.1+ handles this automatically** via the permissive fallback in `_alis_get_pdf_hrefs` — when the `[PREFIX]NNNN.PDF` pattern matches 0 links, the script downloads any `.PDF` link found on the Document Image List page. The `notes` array confirms when the fallback fires. It is still unknown whether this naming applies broadly to older Norfolk deeds or is isolated to certain recording batches — note occurrences as discovered. If even the fallback fails, the JSON includes `image_list_url` and `all_pdf_hrefs_on_image_list` so Claude can recover by fetching directly.
- PDFs are image-based (no text layer); open in Chrome Acrobat extension which blocks automation tools

**USE the abstract page for the property address (v3.22) — this guidance was previously the opposite:** The Document Abstract page (`WSIQTP=LR09A`, `WSKYCD=B`, keyed by recording date + control number) carries a **`Town:` / `Addr:` field giving the property address as plain text**, which the results grid does not (its Document Desc is often just `SEE RECORD` or `LOT N`). The old rule here said to skip this page because Bk/Pg, date, parties and page count are available elsewhere — an enumeration that missed the address, the one field that answers the wrong-parcel question. The script now fetches it automatically for the selected row, every candidate, and every sampled grantor hit, and only falls back to downloading a page-1 PDF when `Addr:` is blank. Doing this by hand in a manual run is one navigation, and it is cheaper and more reliable than reading a scan: it is structured index data, so it has no null-address failure mode on deeds whose first page only says "SEE ATTACHED FULL LEGAL" (Keegan Bk 15978/412 — the v3.20 defect). The abstract also gives `Doc$` consideration, page count, full grantor/grantee lists, and `Ref By:` / `Refers to Book:` cross-references to later homesteads, discharges and deeds. **Caveats:** `Addr:` is frequently absent (an absent address means UNVERIFIED, never "a different parcel"); a multi-parcel deed lists several `Town:`/`Addr:` pairs and any of them may be the subject; some entries carry a street name with no number, which is the "possible subject" tier, not a dismissal; and it is staff-typed index data, so the deed image remains authoritative for the legal description itself. Land Court abstracts use the same date+ctl keying with `WSIQTP=LC09A&WSKYCD=D` (v3.25) — own label vocabulary (`Address:`/`Descr:`/`Grantor:`/`Grantee:`/`Consideration:`/`Ctf#:`, with `Address:` PRECEDING `Town:`), plus `Parent doc:`/`Related doc:` chain cross-refs.

**Capturing images — preferred method (fetch-download + Read tool):**
1. Stay on Document Image List page. Read the actual PDF hrefs from the page links, then fetch each page using the correct prefix. For each page PDF, download it to the output folder via browser JS:
```javascript
fetch('/WwwImg/[PREFIX]0001.PDF')
  .then(r => r.blob())
  .then(blob => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'MyAddress - SellerName - deed_p1.pdf';
    a.click();
  });
```
2. Use the `Read` tool on the saved `.pdf` file — Claude reads it natively as a multimodal model, extracting text and metadata directly. No rendering pipeline needed.
3. Repeat for page 2 (`DUIP0002.PDF`), saving as `deed_p2.pdf`.
4. After reading both pages via `Read`, save JPEG screenshots for auditability using the canvas approach only if needed (see PDF.js fallback below).

**"EST." suffix in the Name column — meaning unconfirmed:** Search results sometimes display a name as `SARNO, THOMAS (EST.&AL)` or `TURNER, JEAN (EST.&AL)` in the **Name** column. The meaning of this `EST.` suffix as displayed in the Norfolk ALIS name index is **not yet confirmed** — do not assume it indicates the named person is deceased or that it refers to their estate. Research is ongoing. Until the meaning is established, treat `EST.` in the Name column as an unknown qualifier and do not draw title conclusions from it alone. (Note: `EST.` appearing in the **Document Type** column — e.g., "ESTATE DEED" — is a separate matter and refers to the instrument type.)

**Grantor Check — direct URL (preferred over form submission):** Rather than navigating to the name search form and submitting it (which can redirect to the homepage on session timeout), run the Grantor Check by navigating directly to the results URL. For Norfolk County:
```
https://www.norfolkresearch.org/ALIS/WW400R.HTM?W9SNM=[LAST]&W9GNM=[FIRST]&W9IXTP=R&W9ABR=*ALL&W9TOWN=*ALL&W9INQ=AY&W9FDTA=&W9TDTA=&AYVAL=+1793&CYVAL=2006&WSHTNM=WW401R00&WSIQTP=LR01LP&WSKYCD=N&WSWVER=2
```
Replace `[LAST]` and `[FIRST]` with the URL-encoded name as indexed at the registry (e.g., `YOEST` and `PETER`). For Barnstable County, substitute the Barnstable domain and adjust `WSHTNM`/`WSIQTP` parameters to match their equivalent result page values.

**Chrome setting (recommended):** Chrome Settings → Privacy and security → Site Settings → Additional content settings → PDF documents → set to **"Download PDFs"**. This prevents the Acrobat extension from intercepting PDF navigations, making the download step trivial.

**Fallback — PDF.js (use only if fetch-download fails):**
1. Load PDF.js from CDN: `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js`
2. Set worker: `pdfjsLib.GlobalWorkerOptions.workerSrc = '[cdn]/pdf.worker.min.js'`
3. Fetch PDF via same-origin: `fetch('/WwwImg/DUIP0001.PDF')`
4. Render at `scale: 2.0`, store canvas data URL in `window._deedPage1DataUrl`
5. Page 1: trigger direct download; Page 2: use localStorage + fresh tab
6. **Note:** PDF.js rendering exceeds the 45s JS timeout — code continues in background. Always screenshot to confirm render completed before proceeding.
