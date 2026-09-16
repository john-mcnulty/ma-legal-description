# Suffolk County — masslandrecords.com/suffolk/D/Default.aspx

Registry mechanics for the `/legal-description` workflow.
Split out of SKILL.md; the workflow steps and every reporting rule live there, not here.

**System:** Avenu/20-20 Perfect Vision Land Records I2 (ASP.NET) — the same build as Middlesex South, with identical form field IDs.

**Fast path:** `--registry suffolk` (v3.41). Verified live 2026-08-18 and 2026-08-20. Typical run ~16 s.

---

## The Office dropdown — Suffolk searches TWO indexes

`SearchCriteriaOffice1_DDL_OfficeName` switches the whole page between:

| Option value | What it searches |
|---|---|
| `Recorded Land` | Recorded Land (Book/Page) — the default |
| `Registered Land (Land Court)` | Registered Land — Document No. + Certificate of Title |
| `Plans` / `Registered Land Plans` / `Virtual Books` | not used by this workflow |

**A Land Court parcel's vesting deed is invisible to a Recorded Land search, and vice versa.** Suffolk holds a great deal of Registered Land, so `--office auto` (the default) searches **both** and selects across the combined candidates. `--office recorded` / `--office registered` pin one index.

### The Office switch is a postback, and the dropdown lies about it

Changing the select fires `__doPostBack`. `select_option` sets the dropdown's value in the DOM **immediately**, roughly 0.5 s before the server actually switches — so "read the Office dropdown back" is not a check, it is a race that always passes.

The reliable, server-rendered signal is the Search Type dropdown, `SearchCriteriaName1_DDL_SearchName`, whose value becomes `"<office> Name Search"` (e.g. `Registered Land (Land Court) Name Search`). The on-page banner (`… Name Search Last Recorded Doc#: …`) says the same thing.

Getting this wrong is not a slow search but a **wrong** one: a run that searched Recorded Land and then "Registered Land" got the Recorded Land grid back both times and reported those rows as Land Court hits. Because the Land Court column map finds no `Doc. #` column on a Recorded Land grid, they arrived as document-less rows that still looked like ordinary Land Court results, and the parcel's real Land Court deed was never seen. The script now also asserts the grid's **shape** matches the office it asked for (Recorded Land has a Book column; Land Court does not) and discards the rows if it does not.

---

## Grid columns differ by office

| Office | Columns |
|---|---|
| Recorded Land | Type \| Name/ Corporation \| **Book** \| **Page** \| Type Desc. \| File Date \| Street # \| Property Descr |
| Registered Land | Type \| Name/Corporation \| **Doc. #** \| Type Desc. \| File Date \| Street # \| Property Descr |

No Town, no Doc # (on Recorded Land), and **no Reverse Party column on either** — the counterparty must come from the detail panel or the image. Land Court has no Book/Page at all, so any row reader anchored on a Book cell returns zero rows against it; the Land Court paths anchor on `Type Desc` instead.

**The leading `Type` column is the PARTY ROLE, not the document type** — `GT` = grantee, `GR` = grantor (the document type is the separate `Type Desc.` column). Both grids carry it. It is what makes a single `Party Type = Both` search usable, since every row says which side of the instrument the searched party was on. Verified live 2026-08-20 against separate Grantee and Grantor searches on the same name: the roles matched the searches that produced them.

Reading it needs care in the column map: the row reader matches a column name as a **substring** of the cell link's href, and bare `Type` also matches `ButtonRow_Type Desc._N`. The map therefore uses **`Type_`** (with the row-index separator) so it can only hit the role column.

---

## Name search

Same fields as Middlesex South: `SearchFormEx1_ACSTextBox_LastName1`, `_FirstName1`, `_Middle1`, and `_ACSRadioButtonList_PartyType1` (a **select**, values `''`=Both, `D`=Grantor, `I`=Grantee), submitted with `SearchFormEx1_btnSearch`. Businesses, condominiums and trusts go entirely in the Last Name field with First Name left blank.

**`Party Type = Both` (`''`) is the default search since v3.41.** It returns the grantee rows and the grantor rows in one postback, each tagged `GT`/`GR` in the `Type` column, so the vesting-deed lookup and the deed-out lookup are one search instead of two. Measured exactly equal to the union of the separate `I` and `D` searches on the same name (2026-08-20). Every search costs a full page navigation plus the Office-switch race, so this halves the scaffolding — and the grantor check consumes the `GR` rows directly rather than re-querying the seller's name.

Because Both returns the union it reaches the 1,000-record cap sooner than either half; the fallback is the split itself (see below).

**The First Name box is a PREFIX match.** A search for `JULIAN` also returns `JULIANA`, `JULIANNE` and `JULIANO`. Live 2026-08-18 this is exactly how a run for *Julian Hollister* at 15 Larkspur Road selected **Hollister Juliana's** 2020 deed for **52 Bayard St** — a different person and a different parcel. The script now warns whenever the selected row's indexed first name only starts with the requested one; treat that warning as a stop, not a footnote.

---

## Property (address) search — both offices

Reached from the **Search Criteria** hover menu, or by setting the Search Type dropdown directly. Each office offers its own set:

| Office | Search types |
|---|---|
| Recorded Land | Name, Document, Book, **Property**, Recorded Date, Unindexed Property, 1951-1960 Grantee Index, 1951-1960 Grantor Index |
| Registered Land | Name, Document, Book, **Property**, **Certificate**, Recorded Date |

`SearchCriteriaName1_DDL_SearchName` holds values of the form `"<office> <kind>"` — e.g. `Registered Land (Land Court) Property Search`. **Switching Office resets Search Type to `"<office> Name Search"`**, so set the office first and the search type second. The switch is the same postback race as the Office dropdown: wait for the server-rendered value, never for the select you just set.

The property form fields are `SearchFormEx1_ACSTextBox_StreetNumber` and `SearchFormEx1_ACSTextBox_StreetName` (Street Name is the only required one), plus a `_Description` box, submitted with the same `btnSearch`.

### The property grid is a different shape — and the same in both offices

`Street Name | File Date | Book/Page | Type Desc. | # of Pgs`

Three consequences, each of which broke something on the way in:

1. **No party name and no `Doc. #` — not even on Land Court.** An address hit carries no grantee and no document number until its detail panel is opened. An address hit is therefore **not name-verified**, and the run says so in `needs_review`: nothing about the row itself confirms it belongs to the named seller.
2. **The office cannot be told from the grid's shape here**, because both offices render the same columns — and the combined `Book/Page` column contains the substring `Book`, so the name-grid shape test (`ButtonRow_Book`) matches on *both* and misfires. The office check for a property search is the server-rendered Search Type. (The shape assertion is kept as an extra, independent check on the *name* grid, where it is what caught the Office-switch race.)
3. **Relocating a row needs its own key.** The name-search relocation matches on document number + party name, neither of which exists here; the property path matches on office + Book/Page + File Date + Type Desc.

The combined `Book/Page` cell means different things per office: on Recorded Land it is the real citation and is split into `book`/`page`; on Land Court it is the **Land Court registration** book/page and is deliberately *not* put in `book`/`page`, so nothing can print it as a Recorded Land citation.

### When it runs

Automatically, whenever the name search produces no conveyance on the subject street — which covers both ways a name search misses: the seller indexed under a different spelling, and the prefix-match trap. `--force-address-search` skips the name pass entirely.

Live 2026-08-18: a deliberately misspelled seller ("Watsen") recovered the correct Land Court deed through the automatic fallback. Note the cost — every fruitless name search pays a 40 s wait, so that run took ~255 s against ~60 s for the name path.

### Certificate Search (not yet used)

Registered Land also offers a Certificate Search. Nothing in this workflow calls it yet; it is the natural way to pull the certificate of title itself rather than inferring its number from a deed.

---

## Two narrowing controls that must NOT be used

Both exist on the form, both were built into the fast path, and both were removed after being measured doing the wrong thing:

- **Towns** (`SearchFormEx1_ACSDropDownList_Towns` — BOSTON / CHELSEA / REVERE / WINTHROP). The option values are read off the Recorded Land form and **do not survive an Office switch**: a Registered Land search submitted with `town=BOSTON` returned **zero rows** for a party with 17 indexed Land Court instruments. Boston also swallows every one of its neighbourhoods, so the filter never bought much. `--town` is accepted and explicitly ignored.
- **Recorded Date From/To** (`ACSTextBox_DateFrom` / `_DateTo`). Only honoured through the **Advanced** panel. Filled on the basic form, a `1/1/2020` window returned 1987 rows in one search and appeared to zero another. A date filter that silently does not apply is worse than none.

Both are the Plymouth municipality-cap failure mode: a control that hides rows without saying so. The grantor check therefore searches every year in both offices and triages the unrelated same-name hits by street.

**This is not a ban on the Advanced panel — it is a ban on the basic form's copies of these boxes.** `ACSTextBox_DateFrom` / `_DateTo` are prefilled with the index floor and today (`12/13/1972`–present) and are posted either way, but Playwright will not fill a hidden input, so they only take effect once **Advanced** (`SearchFormEx1_BtnAdvanced`) is opened — exactly the Plymouth v3.29 mechanic. When a search caps, Advanced is the documented way to narrow it: it exposes the date range and a 78-entry **`SearchFormEx1_ACSDropDownList_DocumentType`** (`-2` = Search All Document Types), plus a second party (`LastName2` / `FirstName2` / `PartyType2`).

---

## The message dialog — the cap and the 0-hit answer

The registry answers some searches with a modal instead of a grid, and **both of its messages were being thrown away**. Selectors: text in `#MessageBoxCtrl1_ErrorLabel1`, dismiss button `#MessageBoxCtrl1_buttonmbatCLIENTOK`.

| Message | What actually comes back | Was read as |
|---|---|---|
| "Your search results have been limited to the first 1,000 records. Please narrow your search criteria by clicking on the 'Advanced' button" | **zero grid rows** | "nothing indexed" |
| "Search criteria resulted in 0 hits. Please verify the search criteria and try again." | zero rows (genuinely) | "nothing indexed", after burning the full 45 s grid timeout |

Since v3.41 the post-submit wait races the grid against this dialog and returns `rows` / `capped` / `empty` / `dialog: <text>`. An **unrecognised** dialog is its own outcome, never folded into "empty" — a message this code cannot read is missing information, not evidence that a party has nothing on record.

**The cap has two shapes, and only one of them speaks.** Over the limit by a lot, the search returns the dialog and no rows. Landing at the limit, it returns exactly **1,000 rows and says nothing** — caught only by the shared reader's row-count check (`results_truncated_at_cap`). Both were observed on one name in one run (2026-08-20): `Both` → dialog + 0 rows, then the `Grantor` half → 1,000 rows silently truncated. Watching only the dialog would have called that half complete.

The fast path's ladder: **Both → split into Grantee and Grantor → still capped ⇒ report it.** The split is a genuine narrowing step (each half is roughly half the set) and is also the pre-v3.41 behaviour, so the worst case degrades to what this registry always did. A half that still caps keeps its rows — a truncated set is incomplete, not wrong, and discarding 1,000 real instruments to signal "incomplete" would throw away the very hits being looked for.

**Timing.** The 0-hit fix is the one that matters. Before it, an empty search sat out the full grid timeout: measured at **28 s per search** averaged over four searches on a seller with no Land Court records, of which the two empty Land Court passes were ~45 s each — the registry had said "0 hits" about a second in, both times. With the dialog consumed and the combined search in place, that run went from **~70 s to ~16 s** end to end, same deed, same grantor hits.

## Detail panel

Header table (both offices): `Doc. # | File Date | Rec Time | Type Desc. | # of Pgs. | Book/Page | Consideration | Doc. Status`.

Read it **structurally**, never by regex over the panel text: the generic consideration pattern matches the Rec Time value (`13:38:00.000`) and a trailing `00.00` first, and read a $412,500.00 deed as `00.00` live.

The panel also carries a Street # / Street Name / Description block and a **Certificate/Encumbrance references** list.

### Certificate of Title — which number is the operative one

Three different certificate numbers show up around one Land Court deed. They are not interchangeable:

| Where it appears | What it is |
|---|---|
| Detail panel **Certificate/Encumbrance references** | the certificate the deed **is noted on** — matches the cover sheet's `Noted on Certificate` line. **This is the one to cite.** |
| Index **description** (`PL 19472-A CERT 64188`) | the certificate the land is *described* on — the plan-lot certificate conveyed out of. Not the seller's, not the buyer's. |
| Deed body, "For the Grantor's title, see Certificate of Title No. …" | the **grantor's** certificate |

Worked example — Doc 812445 (15 Larkspur Road, 5/1/2026): panel reference **198332** = cover sheet `Noted on Certificate: 198332` (the buyers' new certificate); index description names **64188** (plan-lot certificate); the deed body recites the grantor's title as **77105**. The result JSON puts 198332 in `certificate_of_title` and 64188 in `certificate_in_index_description`.

**The panel's Book/Page on a Land Court document** (e.g. `00705/148`) is the **Land Court registration** book/page, not a Recorded Land citation. It is kept in `land_court_registration_book_page` so nothing can emit it as `Bk/Pg`. Cite Registered Land as *Document No. N, noted on Certificate of Title No. M*.

---

## Images

Viewer: `https://www.masslandrecords.com/suffolk/D/ImageViewerEx.aspx`, element `#ImageViewer1_docImage`, next-page button `#ImageViewer1_BtnNext` — identical to Middlesex South.

**Resolution:** the old "~217×281 px, some text illegible" note described the on-page render. Rewriting the `ACSResource.axd` src to `CNTHEIGHT=2000&CNTWIDTH=1550` yields a **1542×2000** JPEG per page — fully legible. Do not repeat the low-resolution warning or send the user to the Registry for a better copy.

**Cover sheets track electronic recording, not the office.** A 2026 Land Court deed (Doc 812445) opens with "Suffolk County Registry of Deeds / Electronically Recorded Document / This is the first page of the document"; a 2001 Land Court deed (Doc 604118) begins with the deed itself. Never assume page 1 is — or is not — a cover sheet.

**Incapsula WAF:** a plain scripted GET to masslandrecords.com returns a ~212-byte block page, so there is **no pure-HTTP engine** for Suffolk. The run launches headful real Chrome (`channel="chrome"`); `--engine http` warns and falls back. A 403 renders as an empty page, so an unexpected "no results" on a name you expect should be re-run before it is believed.

**Manual fallback only:** the popup image viewer and Chrome bulk-download limits described for Plymouth apply if you drive the site by hand. The scripted path fetches page images directly and hits none of it.

**Detail panel References grid (v3.50).** `DocDetails1_GridView_Document_Refs`, 10 data rows per page behind a numeric ASP.NET pager (`__doPostBack('DocDetails1$GridView_Document_Refs','Page$N')`; a 10-page window ends in a `...` link to the next page number), total shown as `References - N` in the panel text. Before v3.50 the script kept page 1 only. It is now read in full by the shared `_read_detail_panel` (`_avenu_read_references`). Measured 2026-09-16: the list order can differ between page LOADS but is stable within a session, so the pager walk is sound. Navigator Book Search here is `Navigator1$SearchCriteria1$LinnkButton_13` (sic — "Linnk"), and its results grid has a single combined `Book/Page` column.
