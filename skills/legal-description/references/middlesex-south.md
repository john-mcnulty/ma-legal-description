# Middlesex South District — masslandrecords.com/MiddlesexSouth/D/Default.aspx

Registry mechanics for the `/legal-description` workflow.
Split out of SKILL.md; the workflow steps and every reporting rule live there, not here.

**System:** Avenu/20-20 Perfect Vision Land Records I2 (ASP.NET) — same platform as Plymouth/Suffolk but hosted on masslandrecords.com behind **Incapsula (Imperva) bot protection**.

**Playwright fast path (v3.8):** Supported by `legal_desc_fetch.py --registry middlesex-south` — see Step 1B. First live-validated 2026-07-09 (Trevisan test case, Medford). The notes below matter mainly for manual fallback or debugging.

**Incapsula WAF (critical):** Headless browsers of any flavor get HTTP 403 on the search POST (initial GET returns 200, so the form *looks* reachable — the failure mode is a silently empty page after clicking Search, with no error text). Headful real Chrome passes. The script forces `headless=False, channel="chrome"`; for manual browser work, the user's normal Chrome session works fine.

**Name search:** Separate `SearchFormEx1_ACSTextBox_LastName1` / `_FirstName1` / `_Middle1` fields — do NOT concatenate Plymouth-style. Prefix matching on both fields (searching first name `ROBERT` matches `CLAUDIA`). Party type select identical to Plymouth (`""`/`D`/`I`). A hidden advanced area has `ACSDropDownList_Towns` (server-side town filter, numeric values, e.g. 120=CAMBRIDGE, 115=NEWTON, 103=FRAMINGHAM) and a Compressed/Like search-mode radio — not used by the fast path yet.

**Results grid columns:** `Type` (terse, e.g. GT) | `Name/ Corporation` | `Book` | `Page` | `Type Desc.` (spelled out — DEED/MORTGAGE/DISCHARGE) | `File Date` | `Street #` (full street: "10 ASHGROVE PL") | `Property Descr`. **No Town, Doc #, or Reverse Party columns.** No `Sort$Rec Date` header — selection relies on the script's Python date sort.

**Detail panel:** Header table: Doc. # | File Date | Rec Time | Type Desc. | # of Pgs. | Book/Page | Consideration | Doc. Status. Grantor/Grantee list uses the same `DocDetails1$GridView_GrantorGrantee` markup as Plymouth. Also shows a **References** cross-ref list (discharges, death certificates, related same-day deeds) — high-value for title flags; the script surfaces it in `notes`. Beware: the panel's Rec Time value (e.g. `10:38:19.043`) defeats naive consideration regexes — parse the table structurally (innermost table wins; outer wrapper tables report the whole header as one cell).

**Image viewer:** View Images tab → navigate directly to `https://www.masslandrecords.com/MiddlesexSouth/D/ImageViewerEx.aspx` (Plymouth Option A works — session holds document context). Same `ImageViewer1_docImage` / `BtnNext` / `lblPageNum` elements. **Hi-res trick:** the img src is an `ACSResource.axd` URL whose `CNTWIDTH`/`CNTHEIGHT`/`ZOOM` params control server-side render size; rewriting `CNTHEIGHT=2000` returns a fully legible ~2000px scan (verified on a 1969 typewritten deed) instead of the ~682px container-sized default. This likely works on Suffolk too (same platform) — untested there.

**Old records (~pre-1986):** Consideration blank in the index (read the excise stamp on the deed image); Doc # may be synthetic — cite Bk/Pg. References list still populated and reliable.

**Registered Land:** Not searched by the fast path. Middlesex South Land Court records need a manual search (navigator menu on the left of the search page switches record types) — document the flow on first live Registered Land run.
