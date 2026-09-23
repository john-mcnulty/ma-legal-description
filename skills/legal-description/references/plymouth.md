# Plymouth County — titleview.org/plymouthdeeds/

Registry mechanics for the `/legal-description` workflow.
Split out of SKILL.md; the workflow steps and every reporting rule live there, not here.

**System:** Avenu/20-20 Perfect Vision Land Records I2 (ASP.NET `__doPostBack`)

**Name format:** Last name first, no comma, no space between compound first name parts.
- Example: `DONNELLY JEANMARIE`

**Form field IDs:**
- Last name: `SearchFormEx1_ACSTextBox_LastName1`
- First name: `SearchFormEx1_ACSTextBox_FirstName1`
- Party type (SELECT): `SearchFormEx1_ACSRadioButtonList_PartyType1` — values: `""` = Both, `"D"` = Grantor, `"I"` = Grantee
- Search button: `SearchFormEx1_btnSearch`

**Image viewer:** Opens as a **popup window** (`ImageViewerEx.aspx`). The popup is frequently blocked by Chrome and lands in a separate browser window outside the MCP tab group.

**Popup workaround — two options (use Option A first):**

Option A — Navigate directly (Plymouth County only): After clicking View Images, simply navigate your current tab to `https://titleview.org/plymouthdeeds/ImageViewerEx.aspx`. No parameters needed — the server session holds the document context. The image viewer will load with the correct deed.

Option B — Monkey-patch `window.open` (general, works for any registry): Inject this JS *before* clicking View Images, then read the captured URL after:
```javascript
window._popupUrl = null;
const _origOpen = window.open;
window.open = function(url, name, features) {
  window._popupUrl = url;
  return _origOpen.call(this, url, name, features);
};
```
After clicking View Images: `window._popupUrl` contains the exact URL. Navigate your tab there.

**Image viewer elements (once loaded in any tab):**
- Deed image element: `ImageViewer1_docImage` (NOT `ImageViewer1_WaterMarkImage`)
- Page nav buttons: `ImageViewer1_BtnNext`, `ImageViewer1_BtnPrevious`, `ImageViewer1_BtnFirst`, `ImageViewer1_BtnLast`
- Page label: `ImageViewer1_lblPageNum`

**Capturing images:** Use canvas API — `ctx.drawImage(img, 0, 0)` on `ImageViewer1_docImage`. Store in `window._deedDataUrl_pN`.

**Download limitation:** Chrome blocks bulk blob/data-URL downloads after the first per tab session.
- Page 1: trigger direct download, move to output folder via Bash
- Page 2+: store in `localStorage`, create a new tab, navigate to same origin, read and download from new tab, then `localStorage.removeItem(key)`

**Document types seen:** `UNIT DEE` = Condo Unit Deed, `TR CRTF` = Trustee's Certificate, `DCLN HMS` = Declaration of Homestead, `MLC` = Mechanics Lien Certificate, `TAX LIEN` = Massachusetts tax lien (often "SEEBK" — attaches to all real property), `PR` = Probate-related instrument

**Multi-property sellers (v2.7):** When a seller owns multiple Plymouth County properties, the grantee name search returns results for all of them. The v2.7 script handles this automatically via Python date sort + town-aware selection + address-search retry. If the script's JSON shows `"deed_property_address"` for the wrong town and `"found_via_address_search": false`, the town filter found no match and fell through to the most recent deed regardless of town — read the deed image to confirm before proceeding. The `notes` array will contain a `"WARNING: no name-search result matched town"` entry in this case.

**Non-monotonic book numbers:** Plymouth County's digitized old records can have book numbers that don't increase monotonically with date (e.g. a 1978 deed at Bk32450, a 2002 deed at Bk22572). The v2.7 Python date sort handles this correctly; the prior browser-side book-number sort validation (v2.6 and earlier) was unreliable in this scenario. **v3.13:** the same broken proxy was still being used to validate the *Rec Date sort direction* (`ctl02 book < ctl03 book` ⇒ "still ascending") — it is now validated by reading the Rec Date column itself.

**Results grid pagination (v3.13) — registry mechanics:**
- Default page size is **20 rows/page**. Page-size controls are `__doPostBack` targets: `DocList1$PageView2Btn` (20), `DocList1$PageView5Btn` (50), `DocList1$PageView100Btn` (100). The anchor for the *active* size loses its `href`, which makes "already at 100" easy to detect.
- The pager is **not** a standard ASP.NET `Page$N` GridView pager. It is a single **`DocList1$LinkButtonNext`** (plus `DocList1$LinkButtonPrev`). On the last page the **Next link is absent** and Previous appears — that is the termination signal.
- The site caps results at **1000 rows** ("Your search results have been limited to the first 1000 records"), i.e. 10 pages at 100/page. **The cap is server-side and applied BEFORE the Rec Date sort**, so a capped set is the *oldest* 1000 rows, not the newest — and page 10 has no Next link, making a truncated walk indistinguishable from a complete one by pager signals alone. Detected since v3.18 via `results_truncated_at_cap` (see 4f above).
- **Every one of these controls is an UpdatePanel postback, and the OLD grid stays in the DOM until the re-render lands.** Waiting on `wait_for_selector('ctl02 …')` or `networkidle` returns immediately against the stale grid — the cause of several silent wrong-data bugs. Wait for the rendered row content to actually change instead.
- **Order matters: set the page size BEFORE sorting.** The 100/Page postback re-renders from the default index order and discards the Rec Date sort.
- `ctl` numbers are unique only **within** a pager page. After walking pages the grid is parked on the last one, so a row read from page 1 must be re-located (and its ctl re-derived by book/doc identity) before its Book link can be clicked — otherwise the click opens a different deed.

**Property (address) search is COUNTY-WIDE — no town filter (v3.42).** The search form has a Towns dropdown and the script no longer touches it. Until v3.42 it tried to, but both attempts missed the real markup — the options are labelled UPPERCASE (`HINGHAM`) while the code sent Title case, and their values are numeric (`100080`) while the code sent the town name — so the filter was never once applied and execution fell through to a bare `pass`. It was removed rather than repaired, matching the Suffolk v3.40 decision where the Towns and Recorded Date filters were measured silently suppressing rows. Plymouth's dropdown carries the same hazard: besides the 27 towns it has `MULTIPLE TOWNS` (100000), `NONE` (100180), `SEE BOOK` (100260) and `PLYMTH COLONY` (100300), and a deed conveying parcels in more than one town is indexed under `MULTIPLE TOWNS` — invisible to a town-scoped search. **Do not add the filter back.** Town scoping is done after the fact by `_town_matches_filter()` against the results grid, where a non-matching row is visible and reportable rather than silently absent. Consequence to keep in mind: county-wide results are larger, so Plymouth's 1000-row cap (applied BEFORE the date sort) is the constraint that matters — watch `results_truncated_at_cap`.

**Full Towns dropdown values** (harvested 2026-08-21; `titleview.org` is not WAF-protected, so a plain GET returns the whole form): ABINGTON=100010, BRIDGEWATER=100020, BROCKTON=100030, CARVER=100040, DUXBURY=100050, EAST BRIDGEWATER=100060, HALIFAX=100070, HINGHAM=100080, HANSON=100090, HANOVER=100100, HULL=100110, KINGSTON=100120, LAKEVILLE=100130, MIDDLEBORO=100140, MARION=100150, MARSHFIELD=100160, MATTAPOISETT=100170, NORWELL=100190, PLYMOUTH=100200, PLYMPTON=100210, PEMBROKE=100220, ROCHESTER=100230, ROCKLAND=100240, SCITUATE=100250, WEST BRIDGEWATER=100270, WHITMAN=100280, WAREHAM=100290. Note the dropdown says `MIDDLEBORO` where the grid says `MIDDLEBOROUGH`. These are the *form* values and are a different namespace from the grid abbreviations below.

**Town abbreviations (v2.9):** Plymouth County's grid uses short abbreviations that mostly match via substring check. Known non-substring cases in `_PLYMOUTH_TOWN_ABBREVS`: `HLFX` (Halifax), `DXBY` (Duxbury), `HNGHM` (Hingham), `PLMTH` (Plymouth), `CRVR` (Carver — confirmed 2026-05-14 from failed run), `KGSTN` (Kingston — confirmed 2026-06-19), `MSHFD` (Marshfield — confirmed 2026-07-08), `WHTMN` (Whitman — confirmed 2026-09-16), `LKVL` (Lakeville) and `MRION` (Marion) — both confirmed 2026-07-08 by the town harvest, added v3.51 after the Lakeville gap returned a Marion deed at exit 0. As of v2.9, an unrecognized abbreviation only matters for sellers with multiple Plymouth County properties (multi-result name search). Single-result runs: script accepts any abbreviation and logs a `NOTE` — add the entry to the dict when you see one. Multi-result runs: a `WARNING` appears (since v3.51 it names the unknown code as a probable DICTIONARY GAP) and the address-search retry fires; add the entry to fix it permanently. Since v3.51 that retry is scoped to the subject town, then to rows the seller's own grantee search also returned, so a missing entry no longer lets it pick a same-numbered address in another town; a selection indexed to another known town sets `selected_row_town_mismatch`. Codes still unharvested: Abington, Bridgewater, Brockton, East Bridgewater, Hanover, Hanson, Hull, Mattapoisett, Norwell, Pembroke, Plympton, Rochester, Rockland, Wareham, West Bridgewater (many may match by substring and need no entry).

**Book Search (v3.50) — registry mechanics.** Recorded Land "Book Search" is `__doPostBack('Navigator1$SearchCriteria1$LinkButton01','')`; its form fields are `SearchFormEx1_ACSTextBox_Book` and `SearchFormEx1_ACSTextBox_PageNumber`, submitted with the usual `SearchFormEx1_btnSearch`. The results grid has the same columns as a name search (Party | Name | Reverse Party | Doc. # | Book | Page | Type | Rec Date | Street | Town) and lists the instrument once per indexed party — on an `OR` row the Name cell is the GRANTOR and Reverse Party the grantee, the reverse of a grantee search. The banner reads `Recorded Land Book Search Book: N Page Number: P`; accept rows only once it names the Bk/Pg you asked for. **A zero-hit search shows `Search criteria resulted in 0 hits.` and NO Book banner.** Sequential Book Searches in one browser session were measured timing out intermittently (5 of 11) and succeeded in a fresh session, so the script retries once in a new context. Registered Land has a separate Certificate Search (`LinkButton11`), not used by the script.

**Detail panel References grid (v3.50).** `DocDetails1_GridView_Document_Refs`: 10 data rows per page (each with a `ButtonRow` link; cells Book/Page | Type | Year), and a standard ASP.NET numeric pager — `__doPostBack('DocDetails1$GridView_Document_Refs','Page$N')`. The panel text carries the total as `References - N`. Paging the grid does not disturb the session's document context: View Images afterwards still serves the same instrument.
