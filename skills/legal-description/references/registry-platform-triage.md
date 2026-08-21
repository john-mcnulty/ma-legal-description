# MA Registry Platform Triage — all 21 districts

Which search platform each Massachusetts Registry of Deeds district runs, and
the verified entry-point URL for each.
Split out of SKILL.md; the workflow steps and every reporting rule live there, not here.

**Purpose:** answer "what will it take to add district X?" before any code is
written. Massachusetts has 21 registry districts but only a handful of search
platforms, so most unimplemented districts are a routing-table entry against an
engine that already exists rather than a new engine.

**Surveyed 2026-08-21** by fingerprinting each district's public entry point
(HTTP status, redirect chain, and platform markers in the returned HTML).
Platform identity was verified; **search behaviour was not** — see the caveat at
the end, and the rule in SKILL.md.

---

## Browntech ALIS — the `_alis_*` engine

Same platform as the implemented Norfolk and Barnstable fast paths. All answer
the same `WW400R.HTM?WSIQTP=LR01D&WSKYCD=N` grantee-search URL shape the engine
already builds, and **none sit behind a WAF** — plain HTTP requests are served.

| District | Search host | Status |
|---|---|---|
| Norfolk | `www.norfolkresearch.org` | implemented |
| Barnstable | `search.barnstabledeeds.org` | implemented |
| Essex North | `search.lawrencedeeds.com` | verified 200, 20 KB form page — not implemented |
| Worcester North | `fitchburgdeeds.com` | verified 200, 21.7 KB form page — not implemented |
| Hampden | `search.hampdendeeds.com` | ALIS confirmed — not implemented |

**Hampden session quirk:** a direct request to the `LR01D` search URL returns
302. The district's landing links go through `WSIQTP=SY00` first, so the ALIS
session cookie must be established from the landing page before the search URL
will serve. Norfolk and Barnstable do not need this.

Fitchburg's landing page (`fitchburgdeeds.com`, 564 bytes) is an ALIS bootstrap
stub — `<input name="WSHTNM" value="WW000R00">` plus `openMain()` — not an error.

## Avenu / 20-20 on masslandrecords.com — the browser engine

Same platform and same `/<District>/D/Default.aspx` path shape as the
implemented Suffolk and Middlesex South fast paths. **All are behind Incapsula**,
which 403s scripted requests, so all require the headful-Chrome path Suffolk
already uses. (Confirmed live: `curl` against `masslandrecords.com` returns an
879-byte `_Incapsula_Resource` challenge page.)

| District | Path on masslandrecords.com | Status |
|---|---|---|
| Suffolk | `/suffolk` | implemented |
| Middlesex South | `/MiddlesexSouth` | implemented |
| Berkshire Middle | `/BerkMiddle` | not implemented |
| Berkshire North | `/BerkNorth` | not implemented |
| Berkshire South | `/Berksouth` | not implemented |
| Dukes | `/Dukes` | not implemented |
| Franklin | `/Franklin` | not implemented |
| Hampshire | `/Hampshire` | not implemented |
| Middlesex North | `/MiddlesexNorth` | not implemented |
| Worcester | `/Worcester` | not implemented |

Note the inconsistent capitalisation in the district segments (`BerkMiddle`,
`BerkNorth`, but `Berksouth`) — it appears that way in the registries' own links.

Several districts front their registry with a portal at `massrods.com/<district>/`
which links out to the masslandrecords instance; `lowelldeeds.com` and
`hampdendeeds.com` are 301 aliases into that portal.

## Avenu / 20-20 on i2o.uslandrecords.com — same product, different host, no WAF

| District | Entry point | Status |
|---|---|---|
| Bristol Fall River | `i2o.uslandrecords.com/MA/BristolFallRiver/D/Default.aspx` | not implemented |

The page identifies itself as Avenu / 20-20 and uses the identical
`/D/Default.aspx` shape, but **is not WAF-protected** — a plain request returned
the full 147 KB page with `__VIEWSTATE` intact. If the 20-20 POST flow is
scriptable here, Fall River could run over pure HTTP rather than headful Chrome.
Untested.

**`i2o` is NOT a general Incapsula bypass — this was tested and it does not work.**
Requesting `i2o.uslandrecords.com/MA/{Suffolk,Hampshire,Dukes,BerkNorth}/D/Default.aspx`
returns 302 to `Unavailable.aspx?Error=Session start failed: Configuration Loading Failed`.
The routes resolve per-district (unlike unknown districts, which 404) but are not
provisioned on that host. Do not re-attempt this as a way around Incapsula.

## Bespoke platforms — a new engine each

| District | Entry point | Platform |
|---|---|---|
| Essex South | `salemdeeds.com/SalemDeeds/DefaultSearch2.aspx` | custom ASP.NET ("SalemDeeds"), Incapsula-fronted |
| Bristol North (Taunton) | `search.tauntondeeds.com/Default.aspx` | bespoke ASP.NET; has a dedicated `/Searches/LandCourt/LandCourtInquiry.aspx` |
| Bristol South (New Bedford) | `www.masearchsb.com/MASEARCHSB/` | vendor app, page title `AIT_Search_Web_Application_CC` |

Essex South's own site is reachable only through the Incapsula challenge, so its
search form was identified from the links on `massrods.com/essexsouth/` rather
than from the app itself.

## Unresolved

**Nantucket.** No reachable registry domain found — `nantucketdeeds.com` and
`nantucketdeeds.org` do not resolve, and there is no `massrods.com/nantucket`
portal. The mass.gov org page returned 403 to the survey. Needs a manual lookup
before Nantucket can be routed at all.

---

## Caveat — platform identity is not behavioural equivalence

Sharing an engine tells you the **transport** is already written. It does not
tell you the district behaves like its siblings. Every trap this project has
been bitten by was per-instance, not per-platform: a row cap applied before the
date sort, a name box that prefix-matches, filters that silently suppress rows,
an office dropdown that reads its new value before the postback lands. Each new
district also needs its own town-code table harvested from its search form.

The rule that follows from this — do not run a newly-added district unsupervised
on a real closing file until its behaviour has been verified — is a reporting
rule and lives in SKILL.md, not here.
