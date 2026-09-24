#!/usr/bin/env python3
"""
legal_desc_fetch.py — fast-path for Legal Description Search Workflow
Version: 3.54

v3.54 changes (item 57 — extraction overlapped with the grantor check):

  On Plymouth, Middlesex South and Suffolk the deed extraction (one API call
  on the page images) ran in main() only after the runner returned, i.e.
  strictly after the grantor check, although neither reads the other's
  output: those grantor checks take their names from the INDEX, and nothing
  after the image step changes the page list. Each runner now calls an
  `on_images_ready` hook as soon as its images are saved; main() starts the
  extraction on a worker thread (_ImageExtractionPrefetch) and joins it
  before the stamp/address checks and the report draft.

  1. The worker extracts into a SHADOW copy of the result and join() copies
     back only the keys the extraction changed, so the runner's concurrent
     writes (notes, grantor_check, status) are never clobbered.
  2. If the page list or the section (Recorded/Land Court) changed after the
     start, or the worker failed, the prefetch is discarded with a NOTE and
     the extraction runs synchronously, exactly as before.
  3. timings: the stage is labelled "(overlapped with grantor check)", keeps
     its full `seconds`, and adds only `wall_seconds` (the wait) to
     total_seconds.
  Measured live on the item-56 audit parcel (Plymouth, 2 pages, 4 grantor
  searches): 62.8 s -> 52.0 s; extraction 14.0 s fully hidden (0.0 s wait);
  same deed, stamp and address verified, legal description byte-identical.
  Middlesex South (condo unit, 3 pages): 33.5 s -> ~23 s over 3 runs each.
  Suffolk Recorded Land: 37.1 s -> 30.0 s; Suffolk Registered Land: 35.3 s
  -> 24.9 s, certificate and Land Court stamp checks unchanged.
  Deed selection, extraction content and every exit code are unchanged.

v3.53 changes (item 56 — a Plymouth town PLACEHOLDER was read as a town):

  Plymouth writes `SEEBK` ("see book") — and on older rows `NONE` — in the
  Town cell of trust instruments. _PLYMOUTH_TOWNLESS_CODES already said so,
  but the grantor-hit classifier never consulted it: the placeholder counted
  as positive evidence of ANOTHER town (v3.37 located_elsewhere), so a
  post-acquisition Trustee's Certificate — including one recorded the same
  day as a deed into trust — was tagged "other town" and demoted out of
  needs_review with no OWNERSHIP-RELEVANT note. Trustee certificates,
  appointments and resignations are what decide WHO MUST SIGN.

  1. The classifier reads a placeholder as a blank town (parcel unknown,
     tagged "no address or town indexed").
  2. PRE-acquisition placeholder rows stay out of review, as before, so the
     fix can only ADD post-acquisition rows to the review set.
  3. An ownership-change hit that could NOT be located to a parcel now gets
     its own OWNERSHIP-RELEVANT note; the existing note fired only when the
     index address matched the subject.
  Deed selection and every exit code are unchanged.

v3.52 changes (cross-reference KIND labels for Plymouth's terse codes):

  The report's Cross-References table bucketed each instrument by SUBSTRING
  needles only, which misfiled 40 of the 72 entries in Plymouth's published
  instrument-code table (59 codes + the grid's 8-character truncations):
  every "DIS xxx"/"REL xxx" code — a released UCC, tax lien, lis pendens,
  attachment or execution — was labelled 'discharge' and fired the
  MORTGAGE-discharge note; AFFT TAX (a federal tax lien affidavit) was
  'probate'; ATT/EXON/JGMT/LISPN/TT/CR/trustee codes fell to 'other'.

  1. New _CROSSREF_CODES: the whole table, matched as WHOLE TOKEN SEQUENCES
     (longest first) before the needles — short codes like TT/CR cannot be
     substring needles without firing inside unrelated words.
  2. 'discharge' now means a MORTGAGE discharge only (DIS, DIS REL, REL);
     other releases are 'release'; PR is 'partial_release'. New kinds:
     foreclosure (CRTF ENTRY), redemption (CR), court_order (DCRE/ORDR),
     trust (trustee certificates/appointments/declarations), easement
     (split out of 'taking').
  3. Certificate of Entry (CRTF ENTRY / "CERTIFICATE OF ENTRY" /
     FORECLOS...) added to the OWNERSHIP-RELEVANT set: a foreclosure by
     entry passes title to the lender after three years with no deed, so a
     grantor hit of this type at the subject parcel now gets the "confirm
     the current owners" note instead of the generic encumbrance wording.
  Deed selection and every exit code are unchanged.

v3.51 changes (item 50 — a Plymouth address pick crossed TOWN LINES and
returned another town's deed at exit 0):

  A Lakeville subject returned a deed for the same house number on a
  same-named road in MARION. The grantee search HAD the right row, but its
  town code 'LKVL' was not in _PLYMOUTH_TOWN_ABBREVS (confirmed by the town
  harvest 2026-07-08 and never added), so the town filter matched 0 of 15
  rows, the multi-row town-mismatch retry fired, and the address search —
  county-wide since v3.42 — picked the highest Book in the COUNTY. v3.42
  said town scoping would happen afterwards against the grid; it never did,
  on any of the three address pick sites.

  1. LAKEVILLE -> LKVL and MARION -> MRION added to the dictionary.
  2. New _plymouth_scope_rows_to_town() runs before EVERY address pick
     (--force-address-search / trust fallback, the town/street-mismatch
     retry, the v3.3 misindexed-name fallback): rows in the subject town
     first; else rows the seller's own grantee search also returned (this
     is what survives the NEXT dictionary gap); else rows with no town
     indexed, as UNVERIFIED; else a CRITICAL note.
  3. The dictionary-gap message now fires where it matters. It used to be a
     NOTE on SINGLE-row runs only, where the gap is harmless, and silent on
     multi-row runs, where it chose the parcel. A multi-row run with 0 town
     matches and an unrecognised code now says DICTIONARY GAP by name.
  4. Final-selection town guard (path-independent, like the v3.12 conveyance
     guard): a selected row indexed to a DIFFERENT known town sets the new
     JSON flag `selected_row_town_mismatch` and a CRITICAL note; an
     unrecognised code gets a NOTE that the town could not be checked.
  Also: _town_matches_filter() is never handed an empty town code by the new
  code — "" is a substring of every town name and would "match".

v3.50 changes (Plymouth Book Search — two findings from reviewing a
subdivision covenant and its lot releases by hand):

  1. THE DETAIL-PANEL REFERENCES LIST WAS CUT OFF AT 10, SILENTLY. The
     panel's References grid pages 10 rows at a time behind its own
     ASP.NET pager ('DocDetails1$GridView_Document_Refs', 'Page$N'), and
     _read_detail_panel took a fixed 400-character slice of the panel text
     — page 1 only, shorter still when instrument names are long. Measured:
     a covenant with 11 references lost its 11th (a lot release), and a
     phased condominium's master deed showed 10 of its 19 amendments.
     These feed detail_references / cross_references, i.e. the later
     discharges and releases a reader chases, so a dropped row is lost
     title signal with nothing saying so. New _avenu_read_references()
     reads the grid rows, walks the pager (waiting on grid CONTENT, never
     a selector), and compares the count to the panel's own
     "References - N" caption. New JSON: detail_references_expected,
     detail_references_complete; a short read is a WARNING note.

     MIDDLESEX SOUTH AND SUFFOLK HAD THE SAME DEFECT — same Avenu grid,
     same 400-character slice in _msouth_read_detail / _suffolk_read_detail.
     Measured live: a Middlesex South master deed with References - 47 and
     a Suffolk master deed with References - 683 each came back with 10.
     All three runners now take the list from _read_detail_panel, which
     they already call; the per-registry slices are gone. (Leaving them
     would have been WORSE than before: they would now read the grid's
     LAST page, after the shared reader had walked it.) Live: 47/47; and
     683/683 unique with the page guard lifted — Suffolk serves the list in
     a different order on every page LOAD but a stable one within a
     session, so the walk neither skips nor repeats. With the guard in
     place (_AVENU_REFS_MAX_PAGES = 50, i.e. 500 references) a list that
     long stops and says INCOMPLETE; a vesting deed essentially never gets
     there, a master deed can.

  2. --book/--page AND --verify-grantor-hit NOW WORK ON PLYMOUTH. Both were
     refused pre-flight (v3.35) because only the ALIS HTTP engine had them.
     The registry's Recorded Land "Book Search" (Navigator LinkButton01) is
     an exact, name-independent jump to one instrument — no prefix match,
     no 1000-row cap applied before a sort, no pager — so:
       * --book N --page P pins the vesting deed and skips the grantee name
         search and its town/street retries. The pin is still CHECKED: the
         seller must appear among the grantees, the index address/town must
         agree, the conveyance guard and the image stamp/address checks
         still run. JSON pinned_by_book_page. A Bk/Pg with no instrument is
         deed_not_found (exit 2).
       * --verify-grantor-hit BOOK/PAGE downloads every page of one grantor
         hit (2000 px), reads its detail panel, extracts it with the deed
         schema, checks its recording stamp, and classifies it against the
         subject — the same grantor_hit_verification contract as ALIS.
     Plymouth needs Book AND Page; a half-specified request is refused
     before any search.
     Mechanics learned live: a zero-hit Book Search shows "Search criteria
     resulted in 0 hits." and no Book banner; on an OR (grantor) row the
     Name cell is the grantor; sequential Book Searches in one session
     intermittently time out and succeed in a fresh browser context (the
     search is retried once in one).

  Also fixed while testing: an entity seller (--first "") produced
  "NAME " with a trailing space, so the grantor check searched the entity
  twice; WHITMAN -> WHTMN added to _PLYMOUTH_TOWN_ABBREVS (a two-row name
  search fired a needless town-mismatch retry); and the "Selected row"
  note now labels grantor/grantee correctly on a grantor-side row.

v3.49 changes (item 44 — the ALIS type vocabulary could not see a UCC
fixture filing, because the registry spells it "Finance Statement"):

  _NON_CONVEYANCE_SUBSTR carried the exact literal "FINANCING", which does
  not substring-match "FINANCE STATEMENT". ALIS (Barnstable Land Court)
  indexes UCC fixture filings under the SHORTER spelling, so a live run
  returned TWO of them — an initial filing and its own continuation, both
  noted on the subject certificate — as `unknown`, and the v3.36 classifier
  correctly refused to guess: two `WARNING: ... has UNRECOGNISED type
  'Finance Statement' ... at the SUBJECT property` notes that had to be
  resolved by reading the instruments.

  This is the v3.29 BKCY-vs-BANKRUPTCY lesson exactly: the CONCEPT was in
  the vocabulary, one of its SPELLINGS was not, and an exact literal cannot
  see a spelling it was not given. Fixed by matching the prefix "FINANC",
  which covers FINANCE / FINANCING / REFINANCE in one entry rather than
  leaving a third spelling to be discovered by a third run. The terse
  Avenu/20-20 side already had "UCC" and the "CONTN UC" compounds and is
  unchanged.

  The prefix is deliberately wide, so the regression guard matters: the
  "DEED" allowlist is tested BEFORE the non-conveyance vocabulary, so
  "DEED OF REFINANCE" still classifies as a conveyance. Pinned by a test.

  WHAT THIS CHANGES IN WHAT YOU REPORT: a UCC fixture filing is an
  ENCUMBRANCE, not a conveyance, so it no longer sits in the unknown tier
  demanding a manual read on every run. It is still never dismissed — it
  stays in `grantor_check.deeds` and, at the subject parcel, still emits
  the encumbrance note. A solar-loan fixture filing is a real closing
  action item (payoff / transfer / subordination and a UCC-3 termination);
  the workflow reports it as found, and clearing it remains out of scope
  per the standing discharge rule.

  Live: the run that produced the two warnings was re-run after the fix —
  same 17 grantor hits, nothing dropped or re-tiered, UNRECOGNISED count
  2 -> 0, both rows now reported as encumbrances at the subject parcel.

v3.48 changes (item 42 — Suffolk and Middlesex South get inline extraction,
so NO registry now depends on the assistant retyping a legal description):

  Suffolk and Middlesex South were the last two registries without inline
  extraction: the assistant Read the page images, retyped the description
  into a temp file and re-invoked with --deliver-text-file. The argument
  for closing that is TRANSCRIPTION FIDELITY, not speed — a hand
  transcription silently "corrects" the record. Measured on the live
  fixtures below, the extraction reproduced both deeds word-for-word
  (Land Court: byte-identical to the verified hand transcription; Suffolk
  Recorded: 320/320 words identical), and where it differed from the hand
  copy it was RIGHT — the hand copy had pasted the grantors' "meaning and
  intending" clause into the description body.

  Both registries already saved the exact artifact needed (deed_p{n}.jpg
  at the same CNTHEIGHT=2000 render), and _extract_pdf_fields has
  dispatched on extension via _IMAGE_MEDIA_TYPES since v3.47, so the
  wiring is small. The work was in the four things that would have gone
  wrong quietly:

  48a  _write_markdown_report THREW on Suffolk. It did summary['total']
       on a value run_suffolk sets to the STRING "hits_found"/"no_hits"/
       "incomplete" (ALIS and Plymouth set a dict of counts). The
       caller's try/except swallowed the TypeError into "Report draft
       failed (non-fatal)", so the first Suffolk run to reach the report
       writer would have produced NO report and only a soft note.
       isinstance(summary, dict) — Suffolk falls into the unclassified
       branch, which is correct for a registry with no classification.

  48b  The v3.47 stamp check would have CRIED WOLF ON EVERY LAND COURT
       RUN. _stamp_matches_selection returned False whenever book/page
       were falsy, and Registered Land has neither — so every CORRECT
       Suffolk Land Court run would have warned "the viewer may have
       served a different instrument". Suffolk is the one registry that
       routinely lands in Land Court. It now returns match/mismatch/
       UNKNOWN and keys Land Court on Document Number, corroborated by
       "Noted on Certificate" and the registration book/page. "unknown"
       (no stamp, nothing to check against) is reported as an unchecked
       box, never as a warning and never as a clean check.

  48c  Inline extraction could put the WRONG CERTIFICATE on a Land Court
       run. When the detail panel's Certificate/Encumbrance read comes
       back empty — seen live — extraction filled certificate_of_title
       from the instrument, and a certificate recited in a deed is the
       one the land is DESCRIBED on (conveyed out of), not the one this
       deed is noted on. Live: panel empty, extraction 77105, cover sheet
       "Noted on Certificate : 198332". Before item 42 the field stayed
       visibly "___"; filling it silently would have replaced missing
       information with confident wrong information. Fixed at the source
       (the schema now defines the field as the "Noted on Certificate"
       number and says to return null rather than a recited one) and
       backed by _reconcile_lc_certificate, which prefers the panel,
       falls back to the cover sheet, and WARNS when the two disagree or
       when the number came from the deed text alone.

  48d  The extracted description drifted between runs of the same deed:
       one run stopped at the end of the description, another swept in
       the homestead release and the derivation clause (891 vs 1353
       chars). The schema now names what follows a description and is not
       part of it — homestead release, execution/acknowledgment blocks,
       recording stamp, and the derivation clause (already captured in
       prior_deed_reference, and re-emitted by the .txt's third form from
       the SELECTED deed's own citation). Two consecutive runs then
       returned byte-identical text.

  Also: the report's "Deed Property Address" fell back to printing None
  when an instrument states no address; it now falls back to the indexed
  address and says which source it came from.

  Live-validated 2026-09-02: Suffolk Recorded (Vandermeer / 22 Cardiff St
  Unit 1, Bk 59214/117, 5 pages, 64 s), Suffolk Registered (Hollister / 15
  Larkspur Rd, Doc 812445 noted on Ctf 198332, 3 pages, ~55 s x3), and
  Middlesex South (Draycott / 7 Ashcombe Rd Unit 1, Bk 70921/188, 3 pages,
  54 s). Stamp verified and address verified on all three.

v3.47 changes (Plymouth: legible source images + inline extraction — the
assistant loop, not the registry, was the cost):

  A timed Plymouth run measured the SCRIPT at 31.5 s end to end (grantee
  search, 3-page pager walk, detail panel, 3 image downloads, 45-row
  grantor check). The same run took 2.6 minutes of wall clock, and an
  earlier one 5.4, because everything after the script was manual: Read
  each page image, transcribe the legal description, write a temp file,
  re-invoke with --deliver-text-file, write the report by hand. Two
  defects underneath that, fixed here:

  47a  The saved page images were 527x682 px — the viewer's THUMBNAIL
       render. _download_viewer_image() fetched #ImageViewer1_docImage's
       src as-is; Middlesex South and Suffolk have rewritten the same
       Avenu ACSResource.axd request to CNTHEIGHT=2000 (a 1542x2000 scan)
       since v3.8/v3.40 and Plymouth never got the port. A typed modern
       deed happened to be readable at 527 px; a metes-and-bounds or
       handwritten one is not, and the images exist so a HUMAN can check
       the transcription against the record. Ported. A page that still
       comes back at the default size is now SAID (per-page method tag +
       a WARNING note) rather than passing silently — the acceptance
       test for a saved page is "legible enough to audit", not "a .jpg".

  47b  Plymouth had NO inline extraction: _run_pdf_extraction() was only
       ever called from the ALIS flow, so legal_description was null, no
       report draft / .txt / clipboard was produced, and the v3.27
       extraction modes did not apply. _extract_pdf_fields() now sends
       image pages as image blocks (PDFs unchanged), and the Plymouth
       dispatch runs the same extraction, report draft and delivery as
       ALIS — gated by the same --extraction {auto,api,claude-code}
       resolution, with the same claude-code fallback note naming the
       files to Read. Two checks come with it, both cheap and both aimed
       at the audit question: the extracted recording stamp is compared
       to the selected Bk/Pg (a mismatch means the viewer served the
       wrong instrument), and the extracted property address is compared
       to the street parsed from --base-name (WARNING on mismatch; no
       auto-retarget on Plymouth — its index-level town and street guards
       already ran before the images were fetched).

  47c  run_plymouth() now records per-stage timings (_Timings, v3.31),
       so the next "where did the time go" question is answered from the
       result JSON instead of a stopwatch around the process.

  47d  Found by the first live run of 47b: the address check tokenises
       on [A-Z0-9]+, so a possessive street name ("Baker's Lane") split
       into BAKER + S and could never equal the BAKERS parsed from
       --base-name — an ADDRESS MISMATCH on the correct parcel. This was
       latent in the shared ALIS helpers too, and one layer up: with the
       apostrophe written in --base-name, the v3.12 index street guard
       fired a false "does not match expected street" and a needless
       address-search retry (measured: +18 s, and on a parcel whose deed
       is absent from the address index the retry could pick a worse
       row). _parse_street_from_base_name() now strips apostrophes at the
       source, and every matcher normalises both sides (_addr_norm).

  47e  Also from that run: the extracted legal_description came back as
       one flat string with no line or paragraph breaks, while the
       delivery's "verbatim" form promises line breaks preserved. The
       schema description now asks for the instrument's line breaks as
       newlines and paragraph breaks as blank lines, and says in so many
       words not to correct apparent typos or odd punctuation — the same
       run showed why: the recorded deed carried a semicolon inside a
       date ("dated March 3; 2015" style), the extraction reproduced it,
       and a hand transcription from the old 527 px thumbnail had
       silently "fixed" it to a comma.
       The record is the record; the human audit exists to catch exactly
       this, and it can only do so if the text was not tidied first.

  The report heading "Screenshots Saved" is now "Source Pages Saved": the
  requirement is a human-auditable copy of each page the description was
  taken from, in whatever format the registry serves.

v3.40 changes (a PORT DIVERGENCE, not a design change — the public copy had
silently lost half of the v3.36 guard):

  Plymouth's non-conveyance guard sets `selected_row_is_not_a_deed` on two
  distinct cases and is supposed to word them differently, because they call
  for different follow-up: an UNRECOGNISED instrument type ("we could not
  tell what this is") and a RECOGNISED non-conveyance one ("this is an
  ASSIGNMENT, not a deed"). Only the first branch survived the move into this
  repo. The second set the flag and appended NOTHING.

  So a public run that selected a recognised non-conveyance instrument — the
  18 Kestrel Ave / Hingham case this guard exists for, where the address
  index held only MTG/DISCHARGE/ASSIGNMENT rows — produced a bare boolean and
  no CRITICAL note anywhere in the output or the report draft. The flag alone
  is not the warning; the note is. A reader scanning notes for problems saw a
  clean run.

  This is the missing-information-read-as-a-negative-answer family again,
  arriving by a new route: not a logic error, but a copy that drifted. The
  branch is restored verbatim from the maintained lineage.

  LESSON, recorded because it will recur until the two copies are collapsed:
  the divergence was invisible to every gate. `verify_scrub.py` checks for
  leaked identifiers, `rule_inventory.py verify` counts rules, and the test
  suite lives outside this repo — none of them compares the two lineages.
  A dropped `else:` is not detectable by any of them.

v3.39 changes (item 22 — ownership that changes with NO deed was being
hidden, on the exact case v3.38 was written for):

  A live Norfolk Land Court run named a seller who had DIED; title had
  passed to his surviving spouse by tenancy-by-the-entirety survivorship
  with no deed ever recorded. The deed-out check was correctly clean, and
  the DEATH CERTIFICATE was demoted out of `needs_review`. Three
  independent defects, each of which alone would have hidden it:

  22a  _instrument_significance() was passed doc_type ONLY. Plymouth
       indexes the terse code `DEATH CRTF` as the TYPE, but ALIS Land
       Court indexes a GENERIC type (`CERTIFICATE`, `AFFIDAVIT`) and puts
       the real nature in the Desc cell ("DEATH OF <name>"). Every
       DEATH/DIVORCE/PROBATE substring was therefore unreachable on ALIS.
       Now matches type+desc; the exact-CODE set stays keyed on the type,
       because Desc may ESCALATE a hit but never dismiss one (v3.23).

  22b  The registry writes a literal placeholder `Addr: N/A` rather than
       leaving the field blank, and it was consumed as a real,
       NON-MATCHING address — demoting rows from `parcel unknown` (kept)
       to `other street, subject town`. The v3.20 lesson one layer out:
       a placeholder MEANS missing information.

  22c  On Registered Land the Certificate of Title number is an EXACT
       parcel key, already on every index row, and nothing used it. A hit
       whose Ctf# equals the selected deed's Ctf# is now the subject
       parcel outright, with no abstract fetch. Absence still asserts
       nothing, in either direction.

  Test: ownership_surfacing_test.py (4 sections). Also fixed a fixture in
  alis_grantor_classify_test.py that went stale at v3.37 and had been
  failing since — item 18 updated two of the three affected tests.

v3.38 changes (item 10 — the grantor check, refocused on the question it
actually answers, and made ~4x faster as a consequence):

  SCOPE, set by the user 2026-08-14. The grantor check is not an
  exhaustive title exam from the deed-in forward. It answers two things:
  does the purported owner STILL OWN the parcel, and WHO are all the
  current owners/signers. The second matters as much as the first,
  because intake routinely arrives wrong — an Offer naming individuals
  who actually hold as TRUSTEES, one seller named when there are two, a
  spouse added to the deed, or a parcel deeded to adult children in
  estate planning. Everything else (discharges, payoff, encumbrance
  status) already belonged to /title-rundown and the discharge workflow.

  1. THE DEED-OUT NET REPLACES THE SURNAME-ONLY PASS. Measured before
     touching anything: the always-on full surname-only search returned
     188 rows to keep 28 (154 to keep 24 on another case) and was
     essentially the ENTIRE grantor-check runtime — 53s of a 94s run,
     42s of a 57s run — while the named-seller and co-owner passes
     returned 4-6 rows each. Both platforms PREFIX-match, so a full-name
     search already reaches longer index spellings ("PENN" -> "PENNE");
     what it cannot reach is an instrument indexed with an INITIAL
     ("SMITH, J") or a misspelled first name. So the net is now
     SURNAME + FIRST INITIAL, run PER KNOWN OWNER, restricted to the
     deed group (`*DD`) server-side. Note this INCREASED coverage: the
     old pass netted only the seller's surname, so a co-owner's initial
     net (`QUINTERO, J*`, `WHITTAKER, M*`) never existed — and on the live
     runs those contributed rows the old pass never returned.
     True surname-only survives as a CONDITIONAL FALLBACK, fired only
     when no owner first name was available (no abstract, extraction
     failed, entity seller) — i.e. when the broad net is actually
     load-bearing, since v3.28's abstract party lists normally enumerate
     every owner by name. What NEITHER form rescues, and the note says
     so: a misspelled SURNAME. That is the address search's job.
  2. OWNERSHIP-BEARING INSTRUMENTS ARE ELEVATED, not filed as
     encumbrances. A death certificate vests a survivor WITH NO DEED
     EVER RECORDED; a trustee certificate/appointment/resignation
     changes who signs; a taking divests; a decree or order can vest or
     confirm. All were being reported as "assess as an encumbrance, not
     a deed-out" — the exact wording that buries them. New
     `_instrument_significance()` returns `ownership_change` | `burden`
     | `''`, deliberately INDEPENDENT of `_classify_instrument` (a
     DECREE is still `unknown` and still warns, AND is
     ownership-relevant — the two answer different questions). Burdens
     (easement, covenant, restriction — user-requested) get their own
     note. `classification.significance` is in the JSON, and an
     ownership-change instrument is never demoted out of needs_review.
  3. THE LIEN SWEEP IS OPT-IN (`--lien-sweep`, default OFF). It asks a
     different question — person-level liens that can reach
     after-acquired property — and belongs to /title-rundown. When it
     does not run the notes SAY so and name the flag, because a sweep
     that silently did not run must never read as a sweep that found
     nothing. Never applied to a net pair (deed-group by construction).
  4. Named-seller and co-owner searches KEEP ALL INSTRUMENT TYPES (user
     decision) — the subject-parcel mortgage/homestead picture is
     unchanged. Only the net is type-restricted.
  5. The prefetch now prefetches the deed-group net instead of the
     retired surname-only pass. That prefetch is where the cost actually
     sat: it ran on a worker thread during extraction, did not finish in
     time because of its row count, and the grantor check then BLOCKED
     on it. `_pair_key` now includes the document group, so a
     deed-group set can never be served to an all-types pair and
     silently narrow it.

  CORRECTION TO THE BACKLOG: item 10 assumed the fix was concurrent
  pagination because "the pager is WSSRPP/offset-driven, so page N+1
  does not depend on page N". IT IS NOT. ALIS pagination is
  postback-driven — each continuation page re-posts hidden fields
  harvested from the PREVIOUS page's HTML — so pages cannot be fetched
  independently. Restricting what is fetched, rather than parallelising
  the fetching, is what actually worked.

  MEASURED, live, same cases before and after:
    Arroyo/Norfolk  56.9s -> 24.1s   (grantor check 41.7s -> 9.4s)
    Whittaker/Norfolk  94.2s -> 57.2s   (grantor check 53.1s -> 12.5s)
    KDM/Plymouth      29s -> 19s     (sweep no longer runs by default)
  Whittaker's real deed-out CRITICAL still fires and still ranks first; its
  needs_review went 47 -> 5 across v3.36-v3.38; the KDM counter-fixture
  is unchanged at 12 with 0 demoted.

v3.37 changes (item 18 — needs_review must shrink on NOISE without
shrinking on MISSING INFORMATION):

  A post-acquisition conveyance-type hit was promoted to `needs_review`
  REGARDLESS of parcel. Right when nothing locates the hit; wrong when
  something does — on a common surname the broad surname-only pass filled
  the review set with other people's parcels (Whittaker: 47 of 48 rows,
  against v3.21's stated goal of "5 rows instead of 93"). A short list
  nobody can trust is read the same way as no list at all.

  THE FIX IS CONSTRAINED BY A COUNTER-FIXTURE PAIR, and that pair is the
  reason it is narrow:
    * Whittaker — 23 other-parcel + 7 other-town rows, each POSITIVELY placed
      somewhere else by an indexed address or town. Noise.
    * KDM    — 8 rows tagged `parcel unknown — subject town`, because the
      Plymouth index simply carries no address for them. A CORRECT flood.
  A naive "shrink needs_review" change passes Whittaker and silently breaks
  KDM. So demotion requires POSITIVE EVIDENCE, and deliberately only the
  strongest kind:
    (a) a TOWN mismatch, with a town actually indexed. Same-town rows
        (`other_same_town`) are NOT demoted — same-town is exactly where
        this workflow's documented wrong-parcel traps live (a seller with
        two properties in one town; a street whose suffix the index
        ignores). An address mismatch inside the subject town is not
        strong enough evidence to stop looking.
    (b) never on a tier name alone. `other_town` is reached BOTH by
        "indexed in another town" AND — on ALIS, where a blank town cannot
        match — by "no town cell at all". Keying on the tier would demote
        the second, which is the v3.20 null-address mistake in a new place.
    Subject / possible-subject / unknown-same-town are never demoted, and
    an UNKNOWN instrument type is never less reviewable than a known
    conveyance in the same position.

  THE SHRINK IS AUDITABLE, because "needs_review is small" and "the
  classifier lost rows" must not look identical: new
  `classification.located_elsewhere`, new
  `summary.demoted_located_elsewhere` count, and a summary note saying in
  words how many were held back and why. NOTHING is dropped —
  `grantor_check.deeds` still lists every hit with its parcel tag; this
  changes ORDER OF ATTENTION, not the evidence.

  Live: Whittaker needs_review 47 -> 10 (22 demoted, deed-out CRITICAL still
  ranked first, deeds complete at 33); KDM 12 with 0 demoted — all 8
  parcel-unknown rows intact. The asymmetry is the whole point.

v3.36 changes (item 0a — the three-way instrument classifier, designed
2026-08-13 and built here; resolves item 13 and improves item 18):

  `_is_non_conveyance_instrument` was a BOOL whose unknown-type
  fall-through returned "conveyance". That single default served 17 call
  sites doing two OPPOSITE jobs, and it was wrong for both in different
  directions:
    - grantor-hit classification: an unrecognised type became a CRITICAL
      deed-out. False alarm, and each one costs a Claude-in-Chrome
      verification trip — which is what dominates run time (item 13: a
      Sunnova solar `CONTN UC` UCC-continuation was flagged as a possible
      deed-out of the subject parcel).
    - row selection: an unrecognised type stayed a deed candidate AND
      passed `selected_row_is_not_a_deed` silently, so it could be
      reported as the vesting deed. Quiet, and far worse.
  A pure allowlist ("only flag if it IS a Deed") fixes the first and makes
  the second worse the other way: any conveyance whose label lacks the
  literal string "DEED" — probate distribution, order of taking, a
  registry indexing QCD/WD — would silently vanish from the deed-out
  check. That is the same missing-information-as-a-negative-answer defect,
  hiding a REAL deed-out instead of raising a false one.

  So the classifier stops choosing: `_classify_instrument()` returns
  'conveyance' | 'non_conveyance' | 'unknown', and each caller picks its
  own safe default — finishing an idea the code already applied to BLANK
  types, which were kept for the grantor check and treated as not-a-deed
  for selection.
    (a) GRANTOR CHECK: unknown is NOT a CRITICAL. It emits
        "WARNING: … has UNRECOGNISED type '<TYPE>' at the SUBJECT
        property — not classified", stays in `needs_review`, and surfaces
        the raw type so the vocabulary can be extended. One line to read
        instead of a browser session. New `classification.instrument_class`.
        Unknown is NEVER dropped: the broad surname-only filter, the
        abstract prefetch and the page-1 sampler all now exclude only
        KNOWN non-conveyances.
    (b) ROW SELECTION: the bool survives as a thin wrapper (unknown →
        not-a-deed), so an unrecognised type now trips
        `selected_row_is_not_a_deed` instead of being reported as the
        vesting deed — a free bug fix. Plymouth's guard words the two
        cases differently ("is a MORTGAGE, NOT a deed" vs "UNRECOGNISED
        type — cannot confirm"), and ALIS gains the guard it never had at
        all (`_alis_select_deed_row` falls back to unfiltered rows, so a
        non-conveyance could be selected there with no warning whatsoever).
        Middlesex names unrecognised types separately in its
        deed_not_found note.
    (c) VOCABULARY HARVEST — the half that makes 'unknown' rare. Loaded
        the registry's OWN published table (titleview.org/plymouthdeeds
        -> InstrAbbreviations.pdf, 61 codes). Two structural facts found
        there, both of which caused item 13: the results grid TRUNCATES
        codes to 8 chars (`CONTN UCC` displays as `CONTN UC`,
        `DCLN HMSTD` as `DCLN HMS`), and compound codes only classify
        when EVERY token is known. Both forms plus the compound halves are
        now listed, and every concept is paired with its spelled-out ALIS
        counterpart (the v3.29 BKCY/BANKRUPTCY rule, applied deliberately
        instead of after a miss). DCRE (Decree) and ORDR (Order) are
        DELIBERATELY omitted so they warn — both can affect title.
    (d) TAKING CAVEAT (pre-existing, surfaced during the design): a
        TAKING is classified non-conveyance so it never fires the deed-out
        CRITICAL, but unlike a mortgage it CAN divest title. At the
        subject parcel its encumbrance note now carries that caveat.

  Live-validated on the two cases that define the change: Halloran
  (`CONTN UC`) went from a CRITICAL false deed-out to a plain encumbrance
  note — zero CRITICALs, correct deed still selected — and Whittaker kept its
  REAL deed-out CRITICAL while an unrecognised `COVENANT` at the subject
  parcel became a WARNING instead of a second false CRITICAL. Whittaker's
  `needs_review` also fell 47 -> 33 (total 48 -> 34) purely from the
  harvest recognising more noise, which is item 18 moving in the right
  direction without touching its rule. The COVENANT was then added to the
  vocabulary — that loop is the design working.

v3.35 changes (item 14, from the 2026-08-13 Plymouth validation run —
the NINTH-counted instance of MISSING INFORMATION READ AS A NEGATIVE
ANSWER, fixed after the tenth):

  HTTP-ONLY FLAGS ARE REFUSED, NEVER SILENTLY IGNORED. The Plymouth run's
  own CRITICAL note says "Verify before closing"; the operator runs the
  documented remediation, `--verify-grantor-hit BOOK/DOC`, and the flag
  was silently ignored on `--registry plymouth`: full search, exit 0,
  `grantor_hit_verification: null`, no note, no error — indistinguishable
  from a clean verification, on the CRITICAL path. Three surfaces, three
  fixes, one rule (the v3.27 pre-flight precedent — if the request is
  knowably unsatisfiable, fail before any work):
    (a) PRE-FLIGHT REFUSAL: `--verify-grantor-hit`, `--book`, `--page` on
        any registry but Norfolk/Barnstable — or combined with an explicit
        `--engine playwright` — exit 1 before anything is created, with an
        error naming the flag and the fix. `--book/--page` are the same
        defect class: a silently dropped pin reports the heuristic pick at
        exit 0 as if the pin was honored.
    (b) AUTO-FALLBACK HONESTY: the one unrefusable path (`--engine auto`
        falls back to Playwright after an HTTP failure, unknowable
        pre-flight) used to warn on STDERR only — a channel the skill does
        not read; since v3.30 the result JSON is the record. The fallback
        now writes `grantor_hit_verification: {status: "not_performed",
        requested, reason}` — the FIELD carries the answer, null is never
        the encoding for "did not run" — plus a WARNING note; a dropped
        `--book` pin gets its own WARNING note.
    (c) Plymouth-side implementation of the verification itself remains
        OPEN (needs the Book&Page search form, undocumented) — but the
        operator now finds out in 2 seconds instead of never.

v3.34 changes (item 19, from the 2026-08-13 Norfolk validation run —
the TENTH instance of MISSING INFORMATION READ AS A NEGATIVE ANSWER):

  CO-OWNER NAME PARSER NO LONGER SWALLOWS MARITAL RECITALS — AND AN
  UNDERIVABLE NAME WARNS INSTEAD OF VANISHING. A granting clause written
  "Anna Marie Coyne being unmarried" (no comma) gave the v3.14 splitter
  tokens ending in the recital, so it derived surname 'UNMARRIED' and the
  grantor check searched "UNMARRIED, ANNA" — a party that does not exist —
  then recorded `status: ok, 0 rows`, which the reading guide defines as
  a CLEAN answer for that name. The run was rescued only by the v3.28
  abstract-sourced co-owner pass finding the real party under her indexed
  name, which is also why this fix keeps BOTH sources: they fail
  independently. Two halves:
    (a) `_NAME_RECITAL_PHRASE_RE` cuts status phrases ("being unmarried",
        "a single person", "husband and wife", "individually") before
        tokenising — anchored on the status words so a period-stripped
        middle initial ("John A Smith") can never be truncated — and
        `_NAME_RECITAL_TOKENS` strips trailing status words the same way
        generational suffixes are stripped;
    (b) an individual's entry that still yields no searchable pair — or a
        derived surname landing ON a recital word — now appends a WARNING
        naming the entry and saying that party's grantor search DID NOT
        RUN from the deed's party list. Entity entries stay silent (their
        skip is documented v3.14 behaviour). A rare real surname that
        collides with a recital word ("Single") degrades to the WARNING
        path — the safe direction: flagged for a hand search rather than
        silently searched wrong or silently dropped.
  Scope: ALIS extraction-side only (`_grantee_full_name_pair`). The
  abstract/Plymouth/Middlesex co-owner sources parse INDEX-format names,
  which carry no recitals — confirmed by the trust-seller validation run,
  whose index-derived trustee names were clean.

v3.33 changes (item 17 + 17b, found offline before the 2026-08-13
Barnstable validation run and confirmed on Norfolk — the same family:
MISSING INFORMATION MUST NOT READ AS A NEGATIVE ANSWER, here in the form
of a FABRICATED answer):

  ALIS TOWN RESOLVERS NO LONGER FABRICATE TOWN CODES. Both
  `_barnstable_resolve_town` and `_norfolk_resolve_town` accepted ANY
  code-shaped last word of an address (3-5 / 4-5 letters) verbatim as an
  ALIS town code, silently: "10 Some Road Yarmouth Port - Smith" derived
  town 'PORT' — a town that does not exist — and the search would return
  zero rows and a FALSE deed_not_found at exit 2, the exact v3.17 failure
  class, from the USPS-correct spelling a user would naturally type. The
  passthrough now requires the token to be a KNOWN code (a value of the
  town table), or to have been passed EXPLICITLY via --town — and an
  explicit unknown code is still passed through (codes can be genuinely
  missing from the table: the WEYB/WEYM history) but with a NOTE warning
  that a wrong code produces a false deed_not_found. A token DERIVED from
  the address is a town-name guess, never a code: unknown derived names
  now fall to the existing guarded fallbacks (BARN + NOTE on Barnstable,
  *ALL + NOTE on Norfolk).

  17b: _BARNSTABLE_TOWN_CODES gains the OTHER towns' villages — v3.28
  added only Barnstable's own, so "Yarmouthport" resolved to BARN, the
  WRONG town (should be YARM), with only a NOTE in the way. Yarmouth,
  Dennis, Harwich, Chatham, Falmouth, Sandwich, Bourne, Eastham, Orleans,
  Truro, Wellfleet and Brewster villages now map to their towns; USPS
  two-word forms included for explicit --town use. Two-word villages
  whose LAST word is code-shaped ("Yarmouth Port" -> 'PORT', "Woods
  Hole" -> 'HOLE') derive an unknown token by design and land on the
  guarded fallback — the parser takes only the last word, and 'PORT'
  is ambiguous between Yarmouth and Dennis anyway.

v3.32 changes (item 21a, from the 2026-08-13 Middlesex South validation
run — the same family again: MISSING INFORMATION MUST NOT READ AS A
NEGATIVE ANSWER):

  MIDDLESEX SOUTH GRANTOR CHECK: PER-SEARCH ACCOUNTING + ERROR ISOLATION
  + FIRST-NAME PREFIX BROADENING. The co-owner loop existed (seller + all
  deed grantees from the detail panel) but three defects made it
  unverifiable and fragile:
    (a) one try/except wrapped EVERY search, so a failure in search #1
        silently cancelled the co-owner searches, appended a "non-fatal"
        note, and the run still reported success — the v3.29 "errored
        search reads as clean title" defect, on a third platform;
    (b) no per-search record existed, so "searched, every row already
        found" and "never searched" produced byte-identical output — the
        item 11 defect, on a third platform (the validation run could not
        tell whether the co-owner returned by the detail panel was ever
        searched at all);
    (c) the first-name field is a PREFIX match (proven live: querying
        first-name 'ALAN' reached 'ALAN GEORGE'), so a co-owner queried
        with a full multi-token first name (e.g. 'ANNA MARIE') could
        never reach an instrument indexed under the bare first name — the
        item 11b trap on the first-name axis.
  Each search now runs in its own try/except and records
  {name, label, rows_returned, rows_new, status} into
  grantor_check.searches via the platform-generic recorder
  (_plymouth_record_searches — Plymouth-named, nothing Plymouth-specific);
  an errored search lands in grantor_check.incomplete_searches and the
  closing note says the check is INCOMPLETE — never "no subsequent
  instruments found" — while completed searches' rows are kept. Co-owner
  first names are truncated to their first token (a strict superset under
  prefix matching, the same move as Plymouth's middle-initial drop), and
  co-owner labels gain "(co-owner from detail panel)" so the report reads
  like the ALIS/Plymouth via-labels. Zero-row searches are trustworthy
  here because STEP 4 only runs after the grantee search already returned
  rows in the same browser session — the Incapsula "silently empty page"
  failure mode cannot have started mid-session without also failing the
  pagination reads, which now surface as ERROR statuses.

  Header note: v3.31 (per-stage timings, doctor preflight, scrub-check
  commit gate, README/packaging) shipped without this docstring being
  bumped; the version line read 3.30 through that release. Its changes
  are documented inline at the `timings` / `run_doctor` definitions.

v3.30 changes (two open backlog items, both of the same family — MISSING
INFORMATION MUST NOT READ AS A NEGATIVE ANSWER):

  1. RESULT WRITTEN TO DISK (`<base-name> - result.json`, item 9b).
     stdout was the only output channel, so a run that was not redirected
     — or whose tail overflowed the caller's output limit — lost book,
     page and grantor_check.needs_review, and the only recovery was
     re-running the whole search (36% of one bad run's wall clock on the
     Ellsworth run; it then happened again on Grant). `_write_result_json`
     writes beside the PDFs before printing. A re-run REFRESHES the file
     (the re-run is the recovery path, so the never-overwrite rule used
     for hand-editable deliverables would be exactly wrong here), except
     that an unsuccessful run will not clobber a successful record — it
     diverts to a timestamped sibling and says so. Non-fatal throughout.
     New result field `result_file`.

  2. PER-SEARCH GRANTOR ACCOUNTING + PLYMOUTH PREFIX BROADENING (item 11).
     Hits are de-duplicated across search names and tagged with the FIRST
     search that found them, so on a co-owned parcel where both owners
     signed everything, every line reads "via: <named seller>" and the
     co-owner pass is indistinguishable from never having run — the Grant
     / 23 Harrowgate Dr run had to be re-verified by hand before its
     report could say the co-owner had not conveyed. `grantor_check.searches`
     now records {name, rows_returned, rows_new, status} per search on
     BOTH platforms, with a readable note and a report block, so
     "searched, all rows duplicate" / "searched, zero rows" / "never
     searched" render differently. Second half: Plymouth's party field is
     a PREFIX match, so 'GRANT LAUREN S' cannot reach an instrument
     indexed 'GRANT LAUREN' (49 rows vs 14) — a trailing middle initial
     is now dropped from Plymouth search names, the broad form being a
     strict superset that replaces rather than adds a search.

  Header note: v3.29 (server-side grantor date window + all-years lien
  sweep) shipped without this docstring being bumped; the version line
  read 3.28 through that release. Its changes are documented inline at
  the `_grantor_window_start` / `_PLYMOUTH_LIEN_DOC_TYPES` definitions.

v3.28 changes (three gaps from Salgado / 87 Marchmont St Hyannis, 2026-08-12 —
the run returned the correct deed at exit 0 and still needed three things
finished by hand):

  1. DEED-GROUP (*DD) FALLBACK FOR A CAPPED GRANTOR SEARCH. The broad
     surname-only SALGADO search capped at 150 rows, and Barnstable's grantor
     search is already town-scoped, so v3.20's town-scoped retry had
     nowhere narrower to go: the check reported INCOMPLETE with no path
     forward — the exact outcome that machinery exists to prevent.
     Document type is the other axis. `_alis_grantor_check_http` gains
     Phase B2: a capped search with no usable town retry (or whose town
     retry also capped) re-runs restricted to `*DD`, merged not
     substituted. Complete `*DD` RESOLVES the cap for a broad
     surname-only search — that search keeps conveyance types only, so
     nothing it would have kept is missing — and only closes the DEED-OUT
     question for a full-name search, which stays in incomplete_searches
     for its non-conveyance rows and says so. New check_meta list
     `deed_group_retries`. Live: capped/150 -> complete 36 rows.

  2. CO-OWNER SEARCH NAMES FROM THE REGISTRY ABSTRACT
     (`_alis_abstract_party_pairs`). The v3.14 co-owner check reads
     `grantees_full`, i.e. the PDF extraction, so it silently never ran
     when extraction failed — and worse, a co-owner REMOVED by the vesting
     deed is named only on its GRANTOR side, where `grantees_full` could
     never have found them. Salgado: grantee "SALGADO, MARIA TERESA",
     grantors "DESALGADO, MARIA ISABEL" + "SALGADO, MARIA TERESA" — the
     departing party is indexed under a different surname, so neither the
     full-name nor the broad surname-only SALGADO search could reach a
     deed-out by her. The abstract lists every party on both sides in index
     format, needs no API, and is already fetched. Grantees are always
     added; grantors only when some party appears on BOTH sides (the
     re-vesting / co-owner-removal pattern), so an arm's-length seller is
     never searched. `result["abstract"]` now carries grantors/grantees.

  3. EXTRACTION DEGRADES AFTER A FAILURE THAT WILL RECUR
     (`_extraction_fatal_reason` + `_mark_extraction_unavailable`). A valid
     key on an account with no credit returns HTTP 400 "Your credit balance
     is too low" for every call: v3.27's pre-flight probe passed (the
     credentials were fine), and the run then made the same doomed call for
     the main deed and for every candidate sample. A present key is not a
     usable key. The first account/credential-class failure now latches
     `extraction_unavailable` on the result; the later extraction sites —
     the auto-retarget's re-extraction, the grantor-hit samples and
     --verify-grantor-hit — skip their calls and name the PDFs to Read
     instead. Transient failures (rate limit, timeout, 5xx) and
     per-document ones do NOT latch. `extraction_mode` still reports what
     was resolved pre-flight and `extraction_error` stays set, because this
     one IS a failure rather than the chosen mode.

  Also: Barnstable VILLAGE names (Hyannis, Centerville, Osterville, …) map
  to BARN, so a correctly-scoped run stops emitting an "unrecognised town"
  NOTE; and `_alis_indexed_name_pair` strips every parenthetical group, not
  only "(&…)", so an index name like "COYNE, MARTIN H. (JR.&AL)" no
  longer parses to the unsearchable first name "MARTIN H. (JR.&AL)".

v3.27 changes (no-API extraction is a first-class MODE, not a failure):
  Running without ANTHROPIC_API_KEY used to mean a full search followed by
  an `extraction_error` — the shape of a broken run. Since v3.22/v3.23 that
  framing is simply wrong: abstracts and index-based classification moved
  the wrong-parcel guard, the auto-retarget, the grantor check and the
  cross-references off the model entirely. The API's remaining job is
  reading the deed PDFs — which Claude can do directly.

  0. REPO-ONLY: `--deliver-text-file <path>` re-enters v3.19 delivery with
     the legal description Claude transcribed from the PDFs, so a
     claude-code run still produces the same three-form .txt (+ --copy /
     --docx) instead of hand-assembling the paste forms. The note it emits
     says plainly that the text was not read off the deed by the script.
  1. NEW `--extraction {auto,api,claude-code}` (default auto) +
     `_resolve_extraction_mode()`, resolved BEFORE any network work:
       auto         API when credentials exist, else claude-code with a
                    friendly note. A key-holder's run is unchanged; a
                    keyless install now works out of the box.
       api          Forces the API; missing credentials is a hard,
                    actionable pre-flight error ("No search was
                    performed") naming both remedies.
       claude-code  Skips the API entirely. `extraction_error` stays null
                    and the notes name the exact PDFs to read.
     `--no-extract-pdf-text` remains as a deprecated alias. New JSON field
     `extraction_mode`.
  2. BUG FIXED, found by the live keyless run: `_anthropic_client()`
     reported a usable client when there were no credentials. The
     installed SDK constructs `Anthropic()` happily with ANTHROPIC_API_KEY
     unset (api_key=None) or empty (api_key='') and only raises at request
     time, so the probe's own docstring ("may only surface on the first
     request") described what always happened. It now checks the resolved
     api_key/auth_token, which is what lets `auto` degrade up front
     instead of after a full search.
  3. The notes state honestly what a keyless run keeps and loses:
     unaffected are the search, deed selection, the registry-abstract
     address check (wrong-parcel guard + auto-retarget), the grantor check
     with needs_review classification, cross-references and the PDF
     downloads; by hand are the legal description from the deed PDFs, and
     the page-1 sample for any candidate/grantor hit whose abstract
     carried no address.
     Live-validated keyless (Kalmar, 33 s): auto-retargeted to the correct
     Bk 35430/139 over the seller's other same-town parcel, and still
     flagged the Bk 40928/96 deed-out CRITICAL — identical safety output
     to the API run, minus the legal description.

v3.26 changes (cross-references consumed + abstract-vs-PDF address check):
  Four code paths collected the registries' cross-reference lists and NONE
  of them consumed it: ALIS Recorded `Ref By:`/`Refers to Book:` (v3.22),
  ALIS Land Court `Parent doc:`/`Related doc:` (v3.25), the Plymouth detail
  panel's References table (v3.24), and Middlesex South's (v3.8). Each
  rendered differently, so nothing downstream could read them uniformly.

  1. NEW: _normalize_cross_references() / _classify_cross_reference() /
     _cross_reference_note(). All four sources normalise to one
     `cross_references` list: {kind, instrument, book, page, doc_number,
     certificate, date, direction, source, raw}. `direction` is the part a
     title reader acts on — `later` (a subsequent instrument references
     this deed: the homesteads/discharges/deeds recorded against the parcel
     afterwards), `earlier` (this deed's prior deed or Land Court parent
     certificate), `related`. `kind` buckets the instrument text
     (discharge / homestead / deed / mortgage / death_cert / probate /
     assignment / lien / plan / taking / notice / other — longest needle
     first, so DISCHARGE beats DIS). An unparseable line is still returned
     with `raw` set and the rest null: dropping a cross-reference is the
     same "missing information read as absence" mistake as v3.20's null
     addresses.
  2. Report gains a **Recorded Cross-References** table (its own section —
     it is a lead list, not a finding).
  3. SCOPE UNCHANGED, and stated in the output: this workflow does not
     verify discharges. A discharge-type cross-reference is the index
     saying such an instrument exists, NOT proof a mortgage was
     discharged; both the note and the report say so explicitly. The
     consumers are /title-rundown and the discharge search.
  4. Abstract-vs-PDF address disagreement is now flagged (WARNING). Both
     addresses have been reported since v3.22 and have always agreed; a
     disagreement means a misindexed abstract or a wrong-parcel PDF, and
     must not pass silently because one of the two matched. Compared on
     the street parsed from --base-name (loose containment when none).

v3.25 changes (Land Court abstracts — the keying was in the ABS icon's href):
  v3.22/v3.23 abstracts were Recorded Land only, because probing the Land
  Court abstract with the Recorded Land parameters returned HTTP 500 and
  the working keying was unknown. Discovered 2026-08-12 by reading the ABS
  icon's href off a live LC results page (pure HTTP, no browser): the LC
  abstract uses the SAME recording-date + control-number keying, just
  `WSIQTP=LC09A` + `WSKYCD=D` instead of `LR09A`/`B` (the href's extra
  `W9IMID`/`W9ABR` params are optional). Confirmed identical on Norfolk
  and Barnstable.

  1. _alis_abstract_url() now builds the LC URL for land_court rows;
     _alis_parse_abstract_html() routes pages without "Bk-Pg:" to the new
     _alis_parse_lc_abstract_text() (own label vocabulary: Address:/Descr:/
     Grantor:/Grantee:/Consideration:/Ctf#:/Doc date:, with Address
     PRECEDING Town — the Recorded Land page pairs them in the opposite
     order; multi-group documents repeat the block). Same output shape,
     plus `certificate` (numeric Ctf# only — "See parent list" stays None)
     and refs from Parent doc:/Related doc: (the parcel's chain).
  2. Everything gated on the old "" URL simply turns on for Registered
     Land: the selected-row STEP 2.5 abstract (address verification with
     no PDF and no API — closes the wrong-parcel-guard gap for Land Court,
     the Kilbride failure surface), candidate resolution, grantor-hit
     samples, and v3.23 classification (LC rows previously classified from
     town/type/date only). certificate_of_title fills from the abstract's
     Ctf# when the index row lacked one.
  3. Live samples that drove the parser: Norfolk Doc 1183426 — the
     Kilbride / 29 Fox Meadow Road deed itself (Address, Ctf# 174905,
     consideration, parties, Parent doc 438,116); Barnstable Doc 982447
     (COC: no Consideration, non-numeric Ctf#, Related doc + Parent doc).
     Fixture: abstract_fixtures/lc_abstract_norfolk_doc1183426.html, test
     alis_lc_abstract_test.py.

v3.24 changes (Plymouth detail-panel References — user-pointed, 2026-08-12):
  The Plymouth detail panel was already read for the full grantor/grantee
  list and Consideration, but its References cross-ref list (later
  homesteads, discharges, death certificates and related deeds recorded
  against the selected deed) was parsed on Middlesex South (v3.8) and the
  ALIS abstracts (v3.22 `refs`) yet dropped on Plymouth — the one registry
  reading the panel without it. _read_detail_panel now returns
  `references`; the Plymouth result gains `detail_references` + a
  "Detail panel references" note. Free title signal for the discharge
  workflow; no extra navigation (same panel, one more slice).

v3.23 changes (ALIS grantor-hit classification — the common-name pile, ALIS
edition):
  The v3.20 town-scoped retries made the ALIS grantor check COMPLETE but
  left it unreadable on a common name: the Keegan live run (2026-08-12, log
  2026-08-12-003) returned 322 instruments in grantor_check.deeds, and
  unlike Plymouth (v3.21) there was no classification — every row had to be
  read by hand. The blocker was always that the ALIS index has no address
  column; v3.22 removed it, because the Document Abstract answers "which
  parcel?" for one GET per hit, no PDF and no model call.

  1. NEW: _alis_classify_grantor_hit / _alis_grantor_sort_key /
     _alis_grantor_hit_str / _alis_finalize_grantor_check /
     _alis_classify_fetch_abstracts — the Plymouth v3.21 trio ported to the
     ALIS path, sharing the same tier names, tags, needs_review rule, and
     JSON shape (grantor_check.needs_review + .summary) so both registries
     read identically. Hit lines gain the abstract address and a parcel tag.
  2. Abstracts are fetched IN PARALLEL (8 workers, own Session each) for the
     rows an address can actually reclassify: post-acquisition conveyance
     hits (the deed-out candidates) and rows in the subject town. Cap
     _ALIS_CLASSIFY_ABSTRACT_CAP = 250 — deliberately NOT the 5-hit
     _GRANTOR_HIT_SAMPLE_CAP, which now only bounds PDF sampling (still the
     fallback for blank-Addr rows). Rows beyond the cap classify from
     town/type/date alone, which errs toward needs_review.
  3. NOTHING IS DROPPED (v3.11 rule): full-name hits carry the seller's own
     mortgages/homesteads/liens and are classified and ordered, never
     filtered. A row with no abstract address is NEVER "a different parcel"
     on that basis alone (the Keegan/v3.20 lesson) — it is parcel-unknown and
     stays in needs_review when its town matches (or it is a post-acq
     conveyance). The index Desc cell can only ESCALATE a hit to
     possible_subject, never dismiss one.
  4. The STEP 8 _hit_address_note closure is hoisted to module level
     (_alis_hit_address_note) so classification and sampling emit identical
     CRITICAL / POSSIBLE / UNVERIFIED wording; rows classification already
     assessed are marked so the sampler does not duplicate their notes, and
     the sampler reuses classification's cached abstracts instead of
     re-fetching. Sampling now runs on the sorted rows, so the 5-sample
     budget goes to the most relevant conveyance hits.
  5. Report: the GRANTOR CHECK section leads with the needs_review set, then
     the full tagged list. Fixed in passing: "POSSIBLE SUBJECT PROPERTY"
     notes (v3.16) were missing from the report's note-prefix filter and
     never rendered as flags.
  6. SPEED — the v3.20 regression fixed. The Keegan validation ran 4m39s
     against the 25–65s benchmark because three capped county-wide grantor
     searches each re-ran town-scoped at up to 20 pages, serially.
     _alis_grantor_check_http now fetches in parallel (Phase A: live
     county-wide searches; Phase B: scoped retries; own Session + own notes
     list per worker) and merges serially in pair order, so notes, dedupe
     order and via-labels stay deterministic. The retry is never skipped
     based on the truncated county-wide set's contents.
  7. Connection-refused now maps to registry_unavailable: a hard-down
     registry (TCP refused — observed Norfolk 2026-08-11/12, WinError
     10061) raises AlisRegistryUnavailableError from _alis_http_get exactly
     like the v3.17 nightly-backup maintenance page, so the run exits 1
     with status registry_unavailable ("retry later, conclude nothing")
     instead of a generic error.

v3.22 changes (ALIS Document Abstract — the address was in the index all along):
  The workflow had an explicit rule to SKIP the ALIS Document Abstract page
  ("all required metadata is on the results and image list pages"). That
  enumeration — Bk/Pg, date, parties, page count — missed the one field that
  matters most for parcel identification: `Addr:`. Meanwhile v3.14/3.15 were
  downloading a page-1 PDF and paying a vision-model call per candidate and
  per grantor hit to re-derive exactly that.

  Worse, the derived version has a failure mode the index does not. Keegan
  Bk15978/412's page 1 reads only "SEE ATTACHED FULL LEGAL", so its sampled
  address came back null and the candidate was silently dropped — the entire
  v3.20 defect. Its abstract carries "Town: WEYMOUTH  Addr: 402 SEDGEFIELD STREET"
  as plain text. One GET would have prevented it.

  1. NEW: _alis_abstract_url() / _alis_parse_abstract_html() /
     _alis_fetch_abstract_http() / _alis_abstract_address_strings(). The
     abstract URL is keyed by recording date + control number, both already
     parsed off the results grid, so no extra navigation is needed. Parsing
     is positional over the page's labels, which handles repeated Town:/Addr:
     pairs (multi-parcel deeds — Bk5311/226 lists two) and missing fields
     alike. Also yields Doc$ consideration, page count, grantors/grantees and
     the Ref By:/Refers to Book: cross-references.
  2. CANDIDATES: the abstract is consulted BEFORE any PDF work. When it names
     an address there is nothing left to learn from a page-1 scan, so both the
     download and its model call are skipped; when it does not (the `Addr:`
     field is often blank — Bk11873/154 has none), the run falls through to
     the existing page-1 sample and, still, v3.20 deep sampling. An absent
     address means UNVERIFIED, never "a different parcel".
  3. GRANTOR HITS: same treatment, and this is where the saving is largest —
     assessing 5 hits cost 5 downloads + 5 vision calls purely to ask "which
     parcel?". Live Keegan run: 4 of 5 answered from the abstract.
  4. THE WRONG-PARCEL GUARD NO LONGER NEEDS THE CLAUDE API. STEP 6 was gated
     on PDF extraction having succeeded; it now runs whenever any address is
     available from either source, so the guard survives
     --no-extract-pdf-text, a missing ANTHROPIC_API_KEY, and extraction
     failure. This is what makes the planned no-API extraction mode safe.
  5. New result fields: `abstract` (url/addresses/consideration/pages/refs)
     and `deed_property_address_abstract`; each candidate and grantor-hit
     sample gains `abstract_addresses` + `abstract_url`. `consideration` is
     filled from Doc$ when the index and PDF did not supply it.
  Fixed in passing: the AUTO-RETARGETED note read the address out of
  `sample_extraction` and so printed None for candidates the abstract had
  resolved without a sample; it now reports the address actually used and
  names its source.

  RECORDED LAND ONLY. The Land Court abstract is keyed differently and returns
  HTTP 500 for these parameters (probed live 2026-08-12); Land Court rows fall
  through to the existing sampling path untouched.

  Live-validated 2026-08-12 on the Keegan run that produced the v3.20 defect:
  correctly selected Bk 15978/412, 4 of 6 candidates and 4 of 5 grantor hits
  resolved from abstracts, and the abstract's "196 BRAMBLETON LANE, MILTON"
  independently agreed with a sibling instrument's PDF-extracted address.

v3.21 changes (Plymouth grantor-check classification — the common-name pile):
  Found live 2026-08-12, James Merrick / 52 Kingsbury Rd, Hingham. The Plymouth
  grantor check returned 93 instruments for `MERRICK JAMES` — roughly forty of
  them 1870s Hull deeds belonging to a 19th-century namesake, the rest other
  parcels and other towns spanning 1762–2026 — with no filtering, ordering or
  tagging of any kind. Every row had to be assessed by hand. Exactly three
  touched the subject parcel, and none of those was a conveyance.

  The ALIS engine has had conveyance-type and pre-acquisition-date filters
  since v3.11/v3.16; the Plymouth path never got them. Ported here, and
  strengthened: the Plymouth results grid carries a street + town cell per
  row, so the parcel question is answerable straight from the index with no
  PDF sampling at all (the ALIS index has no address, which is why v3.15/3.16
  had to download page-1 samples to ask the same question).

  NOTHING IS DROPPED — Plymouth runs full-name searches only (named seller +
  each grantee off the deed), and per the ALIS rule a full-name hit is kept
  regardless of type or date, because the seller's OWN mortgages, homesteads
  and liens arrive through exactly those searches. Hits are CLASSIFIED and
  ORDERED instead:

  1. _plymouth_classify_grantor_hit() tags each hit with a parcel tier —
     subject / possible_subject (street name matches, number unconfirmed) /
     unknown_same_town / other_same_town / other_parcel / other_town — plus
     pre_acquisition and conveyance booleans. A row with NO indexed address is
     never treated as a different parcel on that basis alone; it is only
     deprioritised when its TOWN also differs (the Keegan lesson from v3.20:
     missing information is not a non-match).
  2. needs_review = any hit at (or not excludable from) the subject parcel, OR
     any conveyance-type instrument recorded on/after the acquisition date —
     the two ways a deed-out can present. New JSON: grantor_check.needs_review
     and grantor_check.summary (tier counts). grantor_check.deeds still holds
     EVERY hit, now ordered most-relevant first with a tag appended per line.
  3. A conveyance at the subject parcel recorded on/after acquisition emits a
     CRITICAL note (the deed-out this check exists to find); a non-conveyance
     there emits an encumbrance note instead, so a homestead is not mistaken
     for a conveyance.

  On the Merrick set this cuts the review pile from 93 rows to 5 — the three
  subject-parcel homestead declarations plus the two post-acquisition Brockton
  instruments (a different parcel, but a post-acquisition conveyance, so it is
  surfaced rather than assumed away). Regression-tested offline against the
  real 93-hit result set (tools/plymouth_grantor_filter_test.py).

  Classification requires a street parsed from --base-name. Entity/trust
  sellers with no parseable street fall back to pre-v3.21 behaviour: every hit
  reported unclassified, with a note saying so.

v3.20 changes (Keegan/402 Sedgefield St Weymouth fixes — unverifiable candidates
and the grantor-check pagination cap):
  Found live 2026-08-10, Richard Keegan / 402 Sedgefield St, Weymouth (Norfolk).
  The run returned the SUPERSEDED 1998 purchase deed (Bk 11873/154) at
  exit 0 with no warning; the operative deed was the 2002 re-vesting deed
  Bk 15978/412 (Keegan & Keegan → themselves, tenants by the entirety).

  1. NULL SAMPLE ADDRESS = UNVERIFIABLE, NOT A NON-MATCH. The 2002 deed's
     page 1 read only "SEE ATTACHED FULL LEGAL"; its address lived on an
     attached exhibit page the candidate page-1 sample never downloaded,
     so sample_extraction.property_address came back null and the v3.14
     auto-retarget silently dropped the candidate. The only candidate that
     self-described its address was the older deed, which won by default.
     Now: candidates with no sampled address are deep-sampled
     (_alis_extend_candidate_samples — first _CANDIDATE_SAMPLE_MAX_PAGES
     pages, light extraction over all of them) before matching, and any
     candidate that STILL has no address triggers an explicit
     WARNING/CRITICAL note naming it (CRITICAL when it is recorded later
     than the selected deed and could supersede it).

  2. MULTIPLE ADDRESS MATCHES ARE RANKED BY RECORDED DATE. Several
     matching candidates are the same parcel's chain of deeds to this
     owner (purchase deed + later re-vesting deed); the most recently
     recorded match is selected as the operative vesting instrument
     (previously: gave up and asked for a manual --book/--page pick).
     Falls back to the manual note when dates are missing or tied. New
     helper _alis_same_party_reconveyance(): grantor == grantee on the
     selected candidate (Keegan: 'KEEGAN, RICHARD H' → 'KEEGAN, RICHARD H.')
     is flagged as a re-vesting deed — affirmative evidence it supersedes
     the purchase deed.

  3. TOWN-SCOPED RETRY WHEN THE GRANTOR CHECK CAPS. On a common name the
     county-wide grantor search (Norfolk uses town=*ALL by design) hit the
     5-page/150-row cap on all three Keegan searches — and a truncated
     check cannot support a clean-title statement. Now _alis_search_http
     reports truncation via `meta`, and _alis_grantor_check_http re-runs a
     capped search scoped to the subject town (retry_town, cap
     _ALIS_RETRY_MAX_PAGES=20 pages) and MERGES the results — the *ALL
     pass is kept, not replaced (it catches a seller who moved within the
     county). Keegan town-scoped: 69 and 31 rows, complete. A deed-out of
     the subject parcel is indexed under the subject town, so a complete
     scoped pass closes the subject-parcel question. grantor_check gains
     capped_searches / incomplete_searches; a zero-hit check with an
     incomplete search renders as CRITICAL "Grantor check INCOMPLETE" in
     the report, never as "Clean".

v3.19 changes (Step 7 delivery — paste-out forms, clipboard, .docx):
  On a successful run with a populated legal_description, main() now performs
  the skill's Step 7 for EVERY registry (central hook, non-fatal):
  _deliver_legal_description() writes "Legal Description - <base_name>.txt"
  containing three labelled forms — verbatim (line breaks preserved),
  paste-ready, and paste-ready + "For title, see ..." derivation clause
  (Recorded Land Bk/Pg wording vs Land Court Doc#/Certificate wording;
  missing values become ___ blanks, never guesses).

  The paste-ready reflow (_reflow_legal_description) is CONSERVATIVE —
  whitespace only: hard-wrapped lines joined (blank-line paragraph breaks
  kept, so multi-parcel descriptions survive), line-break hyphen splits
  rejoined, space runs collapsed, curly quotes / primes / dashes / exotic
  spaces normalized to ASCII. It never corrects spelling, expands
  abbreviations, fixes apparent OCR errors, or re-punctuates — a silently
  "improved" metes-and-bounds call is invisible in review and wrong in a
  recorded instrument.

  --copy places the paste-ready form on the clipboard via OS-native tools
  (PowerShell Set-Clipboard reading a UTF-8 temp file / pbcopy /
  xclip|xsel|wl-copy — no pip dependency). --docx also writes a .docx via
  python-docx (skipped with a note if the package is absent). New JSON
  fields: txt_file, docx_file, clipboard_copied, legal_description_paste_ready.
  Existing .txt/.docx files are never overwritten (same policy as the report
  draft); every delivery failure is a note, never a run error.

v3.18 changes (Avenu server-side truncation detection — silent wrong parcel):
  Found live 2026-07-28, Town of Hingham / 319 Halstead St, Hingham. A grantee
  search on a MUNICIPALITY returned exactly 1000 rows — the registry's
  server-side result cap — and the script reported a deed from it at exit 0
  with no warning at all.

  Two things make this dangerous, and neither was detected:
    1. The cap is applied BEFORE the Rec Date sort. Sorting therefore only
       reorders the OLDEST 1000 rows; every newer instrument, including the
       vesting deed, never reaches the browser. The newest row in that sorted
       set was from 1981.
    2. Because the cap is applied server-side, page 10 has no Next link — so
       the pager walk terminated by exactly the same signal as a genuine last
       page. The existing `capped` warning only fires when Next STILL EXISTS at
       max_pages, so it stayed silent.
  ~870 of the 1000 rows were town-wide TKG/TAKING/NOTC/ESMT municipal
  instruments. From what was left the script selected DEED Bk 4102/519 (Bouve
  family -> Hingham Town Of, 6/27/1980) — a real deed for an unrelated parcel —
  with selected_row_is_not_a_deed=false and no warning. None of the existing
  guards can catch this: the town/street filters test rows that were RETURNED,
  and the grid's addr cell is empty on old municipal rows.

  Fix: _read_all_result_rows_paginated() now detects truncation on two
  independent signals — the site's own banner ("Your search results have been
  limited to the first 1000 records", read via _avenu_truncation_banner() while
  a results page is still on screen) and a row count reaching _AVENU_ROW_CAP
  (1000). Either sets the new result field `results_truncated_at_cap` and emits
  a CRITICAL note saying the set is unusable for deed selection. The flag is
  STICKY: run_plymouth passes one result dict to every search it runs, and a
  clean address-search retry must not erase an earlier truncated name search.
  Wired into all three Plymouth paginated reads (grantee search, street/town
  mismatch address retry, v3.3 address fallback).

  Claude-side handling: treat a truncated result set as UNVERIFIED regardless
  of exit code — do not report a deed selected from it. Narrow the search
  (property address search, or a more specific party name). When the address
  index has no deed either, trace the chain from the prior record owner named
  on an MLC / tax lien / 6(d) certificate at the address, and check Registered
  Land (Land Court), which the fast path does not search.

v3.17 changes (registry maintenance-page detection — false deed_not_found fix):
  Found live 2026-07-16 (~11:30 PM ET), Laura Bennett / 190 Ridgemont Rd
  Dennis Port: the Barnstable registry was offline for its nightly backup and
  served a 264-byte HTTP 200 maintenance page ("The Barnstable Public Search
  program is currently unavailable due to nightly backup or periodic
  maintenance") for every request. Both engines parsed it as zero result rows
  and returned deed_not_found / exit 2 — a FALSE NEGATIVE for a seller with a
  recorded deed (Bk 37211/188, found by the same search in May 2026). On an
  unattended run this would have produced a "no deed found for the named
  seller" conclusion on a real closing file.

  Fix: _alis_registry_unavailable_html() detects the Browntech outage page
  (small HTML body containing "currently unavailable" + "maintenance"/
  "backup"). The HTTP engine checks every response in _alis_http_get — the
  single choke point for search pages, pagination, grantor checks, and PDF
  downloads — retries in case the window is just closing, then raises
  AlisRegistryUnavailableError. The dispatch maps that to a new status
  `registry_unavailable` (exit 1) WITHOUT the auto Playwright fallback (the
  browser would load the same page and false-negative identically). Both
  Playwright runners check page content after the grantee-search goto for
  the same reason. Norfolk runs identical Browntech software and gets the
  fix through the shared helpers.

v3.16 changes (speed: light-model sampling, post-acquisition sample gate,
search/extraction overlap, script-generated report draft):
  Four latency fixes, approved 2026-07-16. The registry interaction was
  never the bottleneck — the multimodal extraction calls and the chat-side
  report composition were.

  1. LIGHT MODEL FOR PAGE-1 SAMPLES. Candidate samples and grantor-hit
     samples only extract an address and party names from one page — that
     never needed the main extraction model. They now run on
     _EXTRACT_MODEL_LIGHT (claude-haiku-4-5) via
     _extract_pdf_fields_light(), which retries once on the main model on
     any failure so a light-model hiccup can't blind the address checks.
     The MAIN deed and --verify-grantor-hit full extractions stay on
     _EXTRACT_MODEL_MAIN (claude-opus-4-8) — the verbatim legal
     description is the deliverable and keeps the strongest reader.
     SAFEGUARD (found live, Renwick Bk39044/162): the light model read the
     deed-out's address as 'Cloverfield Avenue' with NO street number, which
     the strict number+name match would have dismissed as a different
     parcel — a false reassurance on a genuine deed-out. Two fixes: the
     address comparison gained a middle tier (street-NAME match without a
     confirmable number → "POSSIBLE SUBJECT PROPERTY ... treat as a
     likely deed-out until verified", never "different parcel"), and any
     light-model sample landing in that tier is re-extracted with the
     main model before the note is emitted.

  2. GRANTOR-HIT SAMPLES: PRE-ACQUISITION HITS NOT SAMPLED. A conveyance
     recorded before the seller acquired the subject property cannot be a
     deed-out of it. Renwick live run: 3 of 5 sampled hits (1996 Tarrant Dr,
     2016/2017 Selkirk St) predate the 06-30-2017 acquisition — three
     extractions that could not change the answer. Such hits stay in
     grantor_check.deeds (full-name hits are still reported regardless of
     date) but no longer get a sample download + extraction. Hits whose
     date fails to parse are still sampled (safe default).

  3. GRANTOR SEARCHES OVERLAP EXTRACTION. v3.14 serialized the grantor
     check after extraction so the retarget and co-owner names could feed
     it — but the USER-NAME and BROAD-SURNAME searches depend on neither.
     STEP 4.5 now prefetches those two searches on a worker thread (own
     requests.Session) while the extraction API calls run; STEP 7 joins,
     reuses the prefetched rows, and only the indexed-name / co-owner
     searches still hit the registry serially. All filtering (acquisition
     exclusion, pre-acq drop) still happens at STEP 7 with the FINAL row,
     so the retarget-correctness reasoning from v3.14 is unchanged.
     Prefetch fails soft: on any error the check just searches live.

  4. SCRIPT-GENERATED MARKDOWN REPORT DRAFT. When the run succeeds with a
     populated legal_description, _write_markdown_report() renders the
     Step 6 report ("Legal Description - <base_name>.md", the skill's
     documented structure: LEGAL DESCRIPTION / Deed Metadata / Title
     Flags / Screenshots Saved) directly into the output folder and
     reports it as result["report_file"]. The Title Flags section is
     assembled from the extraction title_flags, a multi-grantee
     all-must-sign flag, the grantor-check hits + sample address
     assessments, and the address-verification/auto-retarget notes — each
     tagged for attorney review. The draft carries a "DRAFT — generated
     by legal_desc_fetch.py; review before sending" marker: Claude's job
     shrinks to reviewing/adjusting judgment calls instead of composing
     the whole report token-by-token. An existing report file is NEVER
     overwritten (a re-run after manual edits must not destroy them) — a
     note says so and the run proceeds without a draft.

v3.15 changes (ALIS grantor-check hits become fetchable — samples + targeted
verification):
  From the Brandt run (2026-07-13): the grantor check correctly surfaced a
  real deed-out (Bk36890/431, Brandt → Almeida) but confirming it required
  hand-rolled requests calls outside the script — --book/--page only matches
  rows from the GRANTEE-search candidate list, and grantor_check.deeds were
  text strings with no image behind them. Two additions (HTTP engine only):

  1. AUTO-SAMPLE OF CONVEYANCE-TYPE GRANTOR HITS. Every grantor-check hit
     whose doc_type is a conveyance (same _is_non_conveyance_instrument
     test the candidate guard uses; blank types excluded) gets a page-1
     sample PDF (label "grantorhit_Bk<b>_Pg<p>" / "grantorhit_Doc<n>") and
     a light extraction (_GRANTOR_HIT_SCHEMA: property_address, lot_or_unit,
     grantors, grantees), capped at 5 hits with a truncation note. Results
     land in grantor_check.samples (grantor_check.deeds strings unchanged).
     Each sampled address is compared against the street parsed from
     --base-name: a match emits a CRITICAL "conveys the SUBJECT property"
     note (a genuine deed-out of the subject parcel); a non-match emits a
     "different parcel" note. Mirrors the multiple_deed_candidates
     sample_file/sample_extraction mechanism.

  2. --verify-grantor-hit BOOK/PAGE (Land Court: document number). Fully
     fetches ONE grantor-check hit — all pages downloaded + full
     _DEED_SCHEMA extraction — into the new result field
     grantor_hit_verification (index metadata, files, extraction, and the
     same subject-address comparison). The hit must appear in the grantor
     check's results (same searches, exclusions, and pagination caps); if
     it doesn't, a note lists the hits that were found. Combine with
     --book/--page to keep the main deed selection pinned on re-runs.

  Both are non-fatal: sampling/verification errors append notes and never
  break the main result. STEP 8 in run_alis_http, after the grantor check.

v3.14 changes (ALIS auto-retarget by extracted address + co-owner grantor check):
  The two approved follow-ups to the v3.10 inline PDF extraction. Both close
  manual steps that v3.10 exposed (HTTP engine only, like v3.9's
  multi-candidate plumbing they build on).

  1. AUTO-RETARGET BY EXTRACTED ADDRESS. When multiple_deed_candidates
     fires, the script already extracts every candidate's property address
     from its page-1 sample — but kept the most-recent-deed heuristic's pick
     anyway, so Claude had to notice the mismatch and re-run with
     --book/--page (a second ~55s invocation; Renwick 2026-07-11, Brandt
     2026-07-13). Now, after extraction, the MAIN deed's extracted address
     is checked against the street parsed from --base-name
     (_parse_street_from_base_name — the v3.12 Plymouth guard's parser):
       - match → "Address verified" note, done;
       - mismatch and EXACTLY ONE candidate's sample_extraction address
         matches → the script re-runs image-list/download/extraction for
         that instrument in the same invocation (STEP 3+4 refactored into
         _alis_fetch_deed_files() so it can run twice), swaps the top-level
         fields, demotes the heuristic pick to selected:false in
         multiple_deed_candidates (its page-1 file + extracted address are
         preserved there), and emits a loud "AUTO-RETARGETED" note;
       - zero or several matches → prior behavior + a note telling Claude
         to pick via the sample extractions.
     Guard rails: fires only when a street parses from --base-name, never
     when --book/--page was passed, never when the main-deed extraction
     failed. Retargeted files are saved under "deed_Bk<b>_Pg<p>" (Land
     Court: "deed_Doc<n>") so the wrong pick's files are not overwritten.
     New result field: auto_retargeted (bool). Single-candidate runs get
     the same address check as a note-only signal ("Address verified" /
     "ADDRESS MISMATCH ... nothing to retarget to").

  2. CO-OWNER NAMES FROM THE DEED FEED THE GRANTOR CHECK. The grantor check
     searched (a) the user-supplied seller name, (b) the exact indexed
     grantee name from the selected row, (c) broad surname (Recorded Land
     only). A co-owner with a DIFFERENT surname who conveys alone was
     invisible; on Land Court even same-surname co-owners were missed (no
     broad search there, and the LC index shows one grantee + "(&AL)").
     v3.10's grantees_full has every co-owner's full name from the deed
     itself (Kowalczyk → ["Tomasz Adam Kowalczyk", "Marta Lynn Kowalczyk"]).
     Each entry is parsed to a (LAST, FIRST) pair
     (_grantee_full_name_pair: natural order, capacity language and
     generational suffixes stripped, entity/trust names skipped), deduped
     against pairs already covered by an existing full-name prefix, and
     searched like any full-name pair — hits tagged
     "via: <LAST>, <FIRST> (co-owner from deed)". This fulfills the
     "Plymouth model" from the retired Land Court grantor-check spec.

  ORDERING: extraction now runs BEFORE the grantor check (STEP 5, was
  STEP 6). The two were sequential anyway, so this costs nothing and buys
  both features their inputs: the auto-retarget must finish before the
  grantor check so the check runs against the CORRECT acquisition
  instrument (indexed grantee name + acquisition-date/book exclusions all
  come from the selected row), and the co-owner pairs only exist after
  extraction. _alis_grantor_check_http() accepts an optional third
  per-pair element carrying an explicit via-label.

v3.13 changes (Plymouth pagination — the results grid was only ever page 1):
  The Avenu grid defaults to 20 rows/page.  Every Plymouth read took the first
  page and stopped, so on a busy seller or a busy street the older instruments
  — including the vesting deed — were simply invisible.  Live proof
  2026-07-13: a grantee search for GRANT PETER reports "122 rows"; the script
  saw 20.

  The v3.7 "pager walk" that was supposed to prevent this never ran: it looked
  for standard ASP.NET 'Page$N' GridView links, and this grid has none.  Its
  real controls (found live) are __doPostBack targets
  DocList1$PageView100Btn (100 rows/page) and DocList1$LinkButtonNext.  The
  walk was dead code in every caller, including the grantor check.

  - _read_all_result_rows_paginated() rewritten: switches to 100 rows/page,
    then follows Next until it disappears (the last page renders 'Previous'
    but no 'Next').  Rows are tagged with `_pager_page`.  Caps at 10 pages
    (= the site's own 1000-row limit) and warns if the cap is hit.
  - _read_all_result_rows() now scans to ctl102 (was ctl51) — at 100 rows/page
    the old cap would have dropped half of every full page.
  - The grantee search, the street/town-mismatch address retry, and the v3.3
    address fallback all read paginated now (previously page 1 only).  The
    grantor check inherits the fix for free.

  ORDER OF OPERATIONS MATTERS (both learned live):
  - Page size BEFORE sort.  The 100/Page postback re-renders from the default
    index order and DISCARDS the Rec Date sort.
  - Waits must key on CONTENT, not on selectors.  Every one of these controls
    is an UpdatePanel postback, and the OLD grid keeps satisfying
    'ctl02 exists' / networkidle while the stale rows are still on screen — so
    the previous waits returned early and callers read pre-postback data.  New
    _avenu_grid_fingerprint() / _avenu_wait_for_grid_change() block until the
    rendered rows actually change.

  - _sort_results_by_date_desc(): direction is now validated by REC DATE, not
    by book number.  Plymouth book numbers are non-monotonic with date (v2.7's
    own finding), so the old b02<b03 check could not tell asc from desc — it
    reported "descending applied" on a grid that was ascending.  Combined with
    the stale-read bug above it was clicking the header a second time and
    toggling the sort back.  Confirmed live: the Rec Date sort is server-side
    and GLOBAL across the whole result set (page 1 is strictly newer than page
    2), so it is a real tool for reaching the newest/oldest instrument.
  - _plymouth_ensure_row_visible(): ctl numbers are unique only WITHIN a pager
    page, and the walk parks the grid on the LAST page — so clicking a row
    selected from page 1 by its recorded ctl would open the WRONG deed's detail
    panel and images.  The selected row is now re-located (replaying the search
    and paging forward if needed) and its ctl re-derived by instrument identity
    before any click.

v3.12 changes (Plymouth street-level wrong-parcel detection):
  Ports the ALIS "retarget by address" idea to Plymouth's grantee name-search
  path. Plymouth's wrong-parcel guard was TOWN-scoped only: _select_best_row()
  filtered candidates by town, and run_plymouth() fired the address-search
  retry only when the selected row's town differed from the expected town. A
  seller who owns SEVERAL PROPERTIES IN THE SAME TOWN defeated it completely —
  every candidate matched the town, so the most-recently-recorded deed won
  regardless of which parcel it conveyed, with exit 0 and no warning.
  (Reference: Peter Grant, 2026-07-13 — subject property 18 Kestrel Ave,
  Hingham; the name search selected a DEED for 23 Harrowgate Dr, Hingham. Caught
  only by the human address check in the skill's Step 6 preamble.)

  - New _street_matches_filter(): substring match of the street-name word
    parsed from --base-name against the grid's Street cell ("KESTREL" ⊂
    "18 KESTREL AVE"), tolerating suffix variance (AVE/AVENUE/DR) and the
    "&OTHERS" multi-parcel marker.
  - _select_best_row() takes street_filter=: after the town filter, narrows to
    rows naming the expected street. Falls back to the town-only set when no
    row matches, so it can only ever disambiguate — never zero out a result.
  - run_plymouth() now computes town_mismatch AND street_mismatch, and both
    trigger the SAME existing address-search retry (previously town-only).
    The street check runs only when the town matched (a town mismatch is the
    stronger signal and is still reported on its own terms), and unlike the
    town check it fires even on a single-row result — one row naming a
    different street is a real wrong parcel, not an abbreviation artifact.
    Retry notes name which signal fired ("street mismatch" vs "town mismatch").
  - If a street mismatch is detected but street info can't be parsed for the
    retry, a loud VERIFY MANUALLY warning is emitted rather than silently
    returning the wrong deed.
  - Guard rails: only active when a street name parsed from --base-name (so
    entity/trust sellers and malformed base-names behave exactly as before);
    the explicit --force-address-search path is untouched.

  Also in v3.12 — FINAL-SELECTION CONVEYANCE GUARD + new result field
  `selected_row_is_not_a_deed` (bool). The v3.3 misindexed-name fallback only
  guards the NAME-search path, so any row reached via an address search (incl.
  the new street-mismatch retry, and the pre-existing --force-address-search
  and trust/LLC fallbacks) could report a non-conveyance instrument as the
  vesting deed with status "success" and no warning — the address-row filter
  falls back to "using all rows" when the address has no DEED-type row. Now a
  path-independent check runs on the FINAL selection and emits a CRITICAL note
  telling Claude not to extract a legal description from it, and to check
  Registered Land / a misindexed grantee name. Surfaced by the same Grant run:
  the retry reached the correct parcel (18 Kestrel Ave) but the address index
  held only MTG/DISCHARGE/ASSIGNMENT rows, so an ASSIGNMENT was selected.

v3.10 changes (inline ALIS PDF extraction via Claude API):
  Closes the last manual step in Norfolk/Barnstable runs: previously the
  script returned PDF paths and Claude had to Read each scanned deed to get
  the legal description, signing date, consideration, etc. — ~30–60 s and
  several tool calls per run. Now the script extracts those fields itself.

  - ALIS deed PDFs are image-based scans with no text layer (pypdf/pdfplumber
    return nothing), so extraction calls the Claude API (model
    claude-opus-4-8, multimodal) via the anthropic SDK. Each deed's page
    PDFs are sent as base64 document blocks in ONE request; the response is
    constrained with structured outputs (output_config.format json_schema),
    so the result is guaranteed-parseable JSON — no text parsing.
  - Extracted per deed: legal_description (verbatim), property_address,
    signing_date, consideration, document_number, certificate_of_title
    (Land Court), grantors_full / grantees_full (full names incl. middle
    names + trustee capacity), tenancy, prior_deed_reference,
    recording_stamp (Bk/Pg sanity check), title_flags (trust/divorce/
    TIC/homestead/estate recitals).
  - multiple_deed_candidates page-1 samples get a lighter extraction
    (property address + parties) so the wrong-parcel check needs no Read
    calls either. Main deed + candidates extract concurrently (threads).
  - Results land in result["pdf_extraction"]; high-value fields are also
    promoted to top level (legal_description, signing_date, grantees_full,
    ...) and fill index nulls (consideration, document_number).
  - Gated: on by default on the HTTP engine; --no-extract-pdf-text opts
    out. Fails soft — missing anthropic SDK, missing ANTHROPIC_API_KEY, or
    an API error sets result["extraction_error"] and adds a note telling
    Claude to fall back to Reading the PDFs; files are saved regardless.

v3.9 changes (Norfolk audit fixes — pure-HTTP ALIS engine, grantor-check
pagination + name variants, multi-candidate deed selection):
  From the 2026-07-09 Norfolk audit (Renwick / 72 Cloverfield Ave Weymouth,
  run 2026-07-09-003) plus the 2026-05-22 Kowalczyk Land Court grantor-check
  spec. Three fixes, all ALIS (Norfolk + Barnstable):

  1. PURE-HTTP ENGINE (default). The Browntech ALIS sites need no browser:
     search results, pagination, Document Image List, and deed PDFs are all
     plain GETs (verified live on both registries 2026-07-11). New sync
     `_alis_*_http` helpers on requests + BeautifulSoup and a shared
     run_alis_http() runner replace Playwright for norfolk/barnstable runs —
     seconds instead of ~3 min, no browser fragility. `--engine
     {auto,http,playwright}` (default auto) picks HTTP and falls back to the
     unchanged Playwright path on hard HTTP failure (e.g. WAF) or missing
     requests/bs4. Playwright import is now lazy-checked so the HTTP path
     works without Playwright installed.
     Mechanics discovered live: results-per-page param WSSRPP (10/20/30 —
     we request 30); next page = GET WW400R.HTM with the results form's
     hidden fields + WSIQTP=LR01N (Recorded Land) / LC01N (Land Court),
     mirroring doVarButton2() in the site's validate.js.

  2. GRANTOR CHECK: pagination + name variants + Land Court full name.
     ALIS paginates at 10 rows and sorts/groups by the EXACT indexed name
     string ("RENWICK, MICHELE D" sorts after every "RENWICK, MICHELE"), so the
     old page-1-only, last-name-only check missed the critical 2020
     Renwick→Cardoso deed out (Bk 39044/162) and, on Land Court, returned
     pages of unrelated namesakes (Kowalczyk run — 10 unrelated certificates
     reported, the seller's real Doc#1462018/1483473 missed).
     _alis_grantor_check_http() now (a) walks pagination (30/page, cap 5
     pages/search, with a truncation note if the cap is hit); (b) searches
     BY FULL NAME — the user-supplied seller name AND the exact indexed
     grantee name from the selected deed row (carries the middle initial);
     (c) on Recorded Land ALSO keeps the broad surname-only search (catches
     same-surname joint owners); on Land Court full-name searches only, per
     the Kowalczyk spec — the broad search is what produced namesake noise.
     Results are deduped across searches and each hit is tagged with the
     search that found it. The acquisition instrument is excluded by
     book+page (was: book only) / document number.

  3. MULTI-CANDIDATE DEED SELECTION (wrong-parcel guard). When the grantee
     search yields multiple distinct conveyance instruments (Renwick: heuristic
     picked the Tara Gardens condo Bk 35507/244 over subject Lot 38
     Bk 34918/103 — ALIS Desc is too low-signal to disambiguate), the JSON
     now includes `multiple_deed_candidates` with every candidate's index
     metadata plus a downloaded page-1 PDF per candidate, so Claude can
     verify the address on each and re-run with the new `--book`/`--page`
     args to target the right instrument. HTTP engine only.

v3.5 changes (Plymouth hyphenated / compound-surname retry):
  - Problem: Plymouth's name search uses a SINGLE combined "LASTNAME FIRSTNAME"
    field that prefix-matches the concatenated index string. When the seller's
    true surname is hyphenated (e.g. "WHITFIELD-BARROW"), a search built from a
    partial surname fails: "WHITFIELD ALAN" does NOT prefix-match the index entry
    "WHITFIELD-BARROW ALAN D" — after "WHITFIELD" the index continues "-BARROW", not
    " ALAN". Searching the other component ("BARROW ALAN") fails too, since the
    index does not begin with "BARROW". Both of the user's runs for 28 East
    Street, Hingham (seller Alan Whitfield-Barrow, Bk 58120/377) returned 0 rows.
  - Fix: new _plymouth_compound_surname_retry(). When the combined grantee name
    search returns 0 results, the script retries with the SURNAME ONLY (no first
    name). A surname-only search "WHITFIELD" prefix-matches "WHITFIELD-BARROW ..." and
    returns the row. The returned rows are then filtered by the seller's first
    name (first token, matched against the grantee Name column, e.g. "ALAN" in
    "WHITFIELD-BARROW ALAN D") so an unrelated same-prefix surname is not selected.
    The surviving rows flow through the normal deed-type filter, Python date
    sort, and town-aware selection unchanged.
  - Ordering: the compound-surname retry runs BEFORE the trust/LLC address-search
    fallback, because a name-index match is more precise than an address search
    and does not depend on parseable street info. If it finds nothing, the
    address fallback still fires as before.
  - Result JSON gains "found_via_compound_surname" (bool). The grantor check is
    unaffected — it already derives names from the detail-panel grantees, which
    carry the full hyphenated surname ("WHITFIELD-BARROW ALAN D").
  - SCOPE: Plymouth-only. The ALIS registries (Norfolk/Barnstable) use SEPARATE
    last/first fields with begins-with surname matching, so a surname component
    generally already matches a hyphenated surname there; if a live ALIS case
    ever proves otherwise, port this retry into _alis_* (follow-up).
  - Reference fix run: 14 Fernwold Street, Hingham (seller "Alan Whitfield", true
    surname "Whitfield-Barrow", Bk 58120/377).

v3.4 changes (Plymouth misindexed-name / no-deed address fallback):
  - Problem: a grantee name search can miss the true vesting deed when the
    registry MISINDEXED the grantee under a misspelled name. On 60 Aldergate St,
    Middleborough (run 2026-06-23-001) the deed-in (Bk 51338/204) was indexed
    "HANNIGAN" instead of "HENNIGAN", so the only HENNIGAN grantee hit was a
    Certificate of Redemption (type "CR"). The script reported the redemption as
    the vesting deed and never found that the seller had since sold the property.
  - Fix has two parts:
      1. Deed-type filtering now also strips tax-title redemptions ("CR"), tax
         takings ("TT"/"TAX"), municipal lien certificates ("MLC"), easements
         ("ESMT"), and UCCs — none of which convey title — so they can never be
         selected as a vesting deed.
      2. New _is_non_conveyance_instrument() + _plymouth_address_fallback(): if
         the row selected from the name search is still not a conveyance deed
         (e.g. only a redemption survived because the real deed is misindexed),
         the script retries with an address search, which is index-name-
         independent. The most-recent deed-type row is selected — that is the
         vesting deed in the normal case, or the OUT-conveyance when the seller
         has already sold (surfacing that the seller is no longer the record
         owner). Falls back gracefully with a VERIFY-MANUALLY note when no
         street info is available or the address search finds no deed.
  - _is_non_conveyance_instrument() is SHARED across all fast-path registries.
    Its vocabulary covers both the terse Avenu/20-20 codes (Plymouth/Suffolk:
    "CR", "TT", "MLC", "ESMT"...) and the spelled-out Browntech ALIS labels
    (Norfolk/Barnstable: "MORTGAGE", "CERTIFICATE OF REDEMPTION"...). It now
    backs every deed-type filter: the Plymouth name filter, all three Plymouth
    address-search filters, and ALIS _alis_select_deed_row(). This stops ANY
    fast-path county from selecting a redemption/tax-taking/lien as a deed —
    Norfolk/Barnstable previously excluded only mortgages/discharges/etc. and
    shared the same latent bug.
  - SCOPE NOTE: the address-search REMEDY (recovering the deed when a name is
    misindexed) is still Plymouth-only — there is no ALIS address-search path in
    the script yet. On Norfolk/Barnstable the shared classifier prevents picking
    a non-deed but cannot yet recover a misindexed deed; that fallback is a
    separate follow-up (requires building an ALIS address search + confirming
    the Browntech sites expose one).
  - Reference fix run: 2026-06-24-001 (60 Aldergate St, Middleborough).

v3.3 changes (ALIS Land Court column mapping):
  - _alis_parse_results() now maps result-table columns per registry section.
    Recorded Land and Land Court share a column layout EXCEPT:
      * column 1: Recorded Land = Reverse Party; Land Court = Certificate #
      * column 6: Recorded Land = "Book-Page";   Land Court = "Doc#-Sequence"
    The parser previously read column 1 as reverse_party and column 6 as
    book/page for both — so a Land Court row reported the Certificate of
    Title as the grantor and the Document Number as the book number.
    Each row now carries a `land_court` flag plus correctly separated
    `certificate` and `document_number` fields. Downstream consumers
    (_alis_select_deed_row, _alis_grantor_check, run_norfolk, run_barnstable)
    branch on the flag; the result JSON gains a `certificate_of_title` field
    and reports `document_number` from the index for Land Court deeds. The
    grantor check excludes the acquisition document by document_number on
    Land Court (by book on Recorded Land), and `grantors` is left empty for
    Land Court deeds since that index has no opposite-party column.

v3.2 changes (ALIS Land Court field-name fix):
  - _alis_url() now emits the correct name-index field names for Land Court
    searches. Recorded Land uses W9SNM/W9GNM with results handler WW401R00;
    Land Court uses W9SN8/W9GN8 with results handler WW401L00. The function
    previously hardcoded the Recorded Land names for both — a Land Court
    search built with W9SNM/W9GNM silently returned zero results because the
    LC form ignores the unknown parameters. This caused the Land Court
    fallback in run_norfolk()/run_barnstable() to never find registered-land
    deeds (confirmed on the Norfolk Kowalczyk run 2026-05-22, where a
    registered-land property in Randolph was missed and had to be located
    via manual browser search). Fix applies to both registries since
    _alis_url() is shared.

v3.1 changes (ALIS PDF link robustness):
  - _alis_get_pdf_hrefs() now returns a dict with primary + fallback PDF hrefs
    plus the Document Image List URL. Permissive fallback handles non-standard
    short single-file naming (e.g. /WwwImg/D1UJ.PDF on a 1988 Foxborough deed,
    Bk7906/Pg271) where there is no [PREFIX]0001.PDF pattern to match. The
    numbered-page pattern remains the primary path for multi-page deeds.
  - On exit 1 paths ("no PDF links found" or "PDF download failed for all
    pages"), the JSON now includes top-level "image_list_url" and
    "all_pdf_hrefs_on_image_list" so Claude can recover with a direct fetch
    instead of re-navigating from the search results page.
  - Applies to both Barnstable and Norfolk (shared _alis_* code path).


Plymouth County form structure (confirmed from live DOM inspection 2026-04-27):
  Name:       #SearchFormEx1_ACSTextBox_LastName1  — single "LAST FIRST" combined field
  Party type: #SearchFormEx1_ACSRadioButtonList_PartyType1  — <select>: I=Grantee, D=Grantor
  Search btn: #SearchFormEx1_btnSearch
  Results:    AJAX — wait for a[href*="GridView_Document$ctl02$ButtonRow"] before reading DOM
  Detail panel: click Book link → panel appears → wait for a[href*="TabController1"]
  View Images: __doPostBack('TabController1$ImageViewertabitem','') sets server session silently
               then navigate to ImageViewerEx.aspx to load viewer
  Image:      #ImageViewer1_docImage — <img> with authenticated src URL

Barnstable & Norfolk Counties (Browntech ALIS):
  Both run identical ALIS software — only the base URL and town codes differ.
  Shared helpers prefixed `_alis_*` accept a `base_url` parameter and serve
  both registries. Direct-URL search, PDF fetch via page.request.get().

Usage:
  python legal_desc_fetch.py --registry plymouth --last MARCHETTI --first WILLIAM \\
      --base-name "12 Cranmore Hill Lane Unit 203 Scituate - Marchetti" \\
      --output "/path/to/your/output/folder"

Output:  JSON to stdout
Exit 0:  success
Exit 2:  deed not found
Exit 1:  error

Plymouth trust-vested fallback (v2.5+):
  If name search returns 0 results, the script automatically retries with a
  property address search. Street number and street name are parsed from
  --base-name (first numeric token + second token) if not supplied via
  --street-number and --street. Use for trust- or LLC-vested properties.
"""

import asyncio
import json
import argparse
import os
import sys
import re
import time
# Aliased: several functions in this file bind a local named `html`
# (`html = resp.text`), which would shadow the stdlib module.
import html as _html
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
from datetime import date as _dt_date, timedelta as _dt_timedelta

# Playwright is only required for the browser-driven paths (Plymouth,
# Middlesex South, Suffolk stub, and the ALIS fallback engine). The default
# ALIS HTTP engine runs without it, so a missing install is reported only
# when a Playwright path is actually selected (see main()).
try:
    from playwright.async_api import async_playwright, Page, BrowserContext
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    Page = None
    BrowserContext = None
    _PLAYWRIGHT_AVAILABLE = False

_PLAYWRIGHT_INSTALL_MSG = (
    "Playwright not installed. "
    "Run: python -m pip install playwright && python -m playwright install chromium"
)

# requests + BeautifulSoup power the ALIS pure-HTTP engine (v3.9).
try:
    import requests
except ImportError:
    requests = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

_HTTP_AVAILABLE = requests is not None and BeautifulSoup is not None
_HTTP_INSTALL_MSG = (
    "requests/beautifulsoup4 not installed. "
    "Run: python -m pip install requests beautifulsoup4"
)

# anthropic SDK powers inline PDF extraction (v3.10). Optional — without it
# (or without credentials) the script still runs and Claude falls back to
# Reading the PDFs.
try:
    import anthropic
except ImportError:
    anthropic = None

import base64
from concurrent.futures import ThreadPoolExecutor


PLYMOUTH_SEARCH = "https://titleview.org/plymouthdeeds/"
PLYMOUTH_VIEWER = "https://titleview.org/plymouthdeeds/ImageViewerEx.aspx"

BARNSTABLE_BASE = "https://search.barnstabledeeds.org"
NORFOLK_BASE    = "https://www.norfolkresearch.org"

# Norfolk County ALIS town codes. Each Norfolk municipality has its own code
# (unlike Barnstable where BARN covers all villages). Codes are mostly the first
# Full town code list enumerated 2026-05-16 from the Norfolk LC01D (Land Court)
# form dropdown — codes appear to be shared between Recorded and Land Court forms.
# ✓ = confirmed on a live Recorded Land run. Unknown towns fall back to *ALL.
# Barnstable County ALIS town codes. Full list enumerated 2026-05-20 from the
# Barnstable LR01D form dropdown. BARN covers all Barnstable villages (Hyannis,
# Centerville, Osterville, Cotuit, etc.); other towns have their own codes.
# ✓ = confirmed on a live run.
_BARNSTABLE_TOWN_CODES: dict[str, str] = {
    "BARNSTABLE":    "BARN",   # covers all Barnstable villages ✓
    "BOURNE":        "BOUR",   # ✓ (skill notes)
    "BREWSTER":      "BREW",
    "CHATHAM":       "CHAT",
    "DENNIS":        "DENN",   # ✓ confirmed 2026-05-20 (Bennett)
    "EASTHAM":       "EAST",
    "FALMOUTH":      "FALM",   # ✓ (skill notes)
    "HARWICH":       "HARW",
    "MASHPEE":       "MASH",   # ✓ (skill notes)
    "ORLEANS":       "ORLE",
    "PROVINCETOWN":  "PROV",
    "SANDWICH":      "SAND",   # ✓ (skill notes)
    "TRURO":         "TRUR",
    "WELLFLEET":     "WELL",
    "YARMOUTH":      "YARM",   # ✓ (skill notes)
    # v3.28 — Barnstable's VILLAGES, which is how these addresses are
    # written ("87 Marchmont Street, Hyannis"). All record under BARN, so the
    # fallback already produced the right code — but it produced it with a
    # NOTE saying the town was unrecognised, which reads like a defect on a
    # run that was in fact correctly scoped (Salgado, 2026-08-12).
    "HYANNIS":          "BARN",   # ✓ confirmed live 2026-08-12 (Salgado)
    "HYANNISPORT":      "BARN",
    "CENTERVILLE":      "BARN",
    "OSTERVILLE":       "BARN",
    "COTUIT":           "BARN",
    "MARSTONS MILLS":   "BARN",
    "WEST BARNSTABLE":  "BARN",
    "CUMMAQUID":        "BARN",
    # v3.33 (item 17b) — the OTHER towns' villages, which v3.28 never added:
    # only Barnstable's own villages were mapped, so "Yarmouthport" fell to
    # BARN (the WRONG town — should be YARM) with only a NOTE standing
    # between the run and a wrong-town search (2026-08-13 validation run).
    # Single-word forms are what _parse_town_from_base_name can actually
    # produce (it takes the LAST word, so "Yarmouth Port" derives "PORT" and
    # is handled by the item 17 guard instead); the USPS two-word forms are
    # for an explicit --town argument.
    "YARMOUTHPORT":     "YARM",   # ✓ confirmed live 2026-08-13 (--town YARM)
    "YARMOUTH PORT":    "YARM",
    "SOUTH YARMOUTH":   "YARM",
    "WEST YARMOUTH":    "YARM",
    "BASS RIVER":       "YARM",
    "DENNISPORT":       "DENN",
    "DENNIS PORT":      "DENN",
    "SOUTH DENNIS":     "DENN",
    "WEST DENNIS":      "DENN",
    "EAST DENNIS":      "DENN",
    "HARWICHPORT":      "HARW",
    "HARWICH PORT":     "HARW",
    "EAST HARWICH":     "HARW",
    "WEST HARWICH":     "HARW",
    "SOUTH HARWICH":    "HARW",
    "CHATHAMPORT":      "CHAT",
    "SOUTH CHATHAM":    "CHAT",
    "WEST CHATHAM":     "CHAT",
    "NORTH CHATHAM":    "CHAT",
    "EAST FALMOUTH":    "FALM",
    "NORTH FALMOUTH":   "FALM",
    "WEST FALMOUTH":    "FALM",
    "WOODS HOLE":       "FALM",
    "TEATICKET":        "FALM",
    "WAQUOIT":          "FALM",
    "EAST SANDWICH":    "SAND",
    "FORESTDALE":       "SAND",
    "SAGAMORE":         "BOUR",
    "SAGAMORE BEACH":   "BOUR",
    "BUZZARDS BAY":     "BOUR",
    "MONUMENT BEACH":   "BOUR",
    "POCASSET":         "BOUR",
    "CATAUMET":         "BOUR",
    "NORTH EASTHAM":    "EAST",
    "EAST ORLEANS":     "ORLE",
    "SOUTH ORLEANS":    "ORLE",
    "NORTH TRURO":      "TRUR",
    "SOUTH WELLFLEET":  "WELL",
    "EAST BREWSTER":    "BREW",
    "WEST BREWSTER":    "BREW",
}


def _barnstable_resolve_town(town_arg: str, base_name: str) -> tuple[str, list[str]]:
    """
    Resolve --town arg to an ALIS town code for Barnstable County.

    Returns (code, notes_list). Accepts:
      - empty string → derive town from base_name; fall back to BARN if unrecognized
      - town name (any case): looked up in _BARNSTABLE_TOWN_CODES → ALIS code
      - ALIS code (3-5 uppercase letters): trusted, returned as-is
      - "*ALL": returned as-is
    """
    notes: list[str] = []
    raw = (town_arg or "").strip()
    if raw.upper() == "*ALL":
        return "*ALL", notes
    candidate = raw.upper() if raw else _parse_town_from_base_name(base_name).upper()
    if not candidate:
        notes.append("No --town provided and could not parse town from base_name. Defaulting to BARN.")
        return "BARN", notes
    if candidate in _BARNSTABLE_TOWN_CODES:
        return _BARNSTABLE_TOWN_CODES[candidate], notes
    # v3.33 (item 17): a code-shaped token is only trusted when it is a KNOWN
    # code, or when the user passed it EXPLICITLY. The old passthrough took
    # ANY 3-5 letter last word of an address as a town code, silently — so
    # "10 Some Road Yarmouth Port - Smith" derived town 'PORT', a town that
    # does not exist, and the search would have returned zero rows and a
    # FALSE deed_not_found at exit 2 (the v3.17 failure class). A derived
    # token is a town-name GUESS, never a code.
    if candidate in set(_BARNSTABLE_TOWN_CODES.values()):
        return candidate, notes
    if raw and 3 <= len(candidate) <= 5 and candidate.isalpha():
        notes.append(
            f"NOTE: '{candidate}' is not a known Barnstable town name or ALIS "
            f"code — trusting it as a code ONLY because it was passed "
            f"explicitly via --town. A wrong code returns ZERO rows and a "
            f"false deed_not_found; if this run finds nothing, re-check the "
            f"town before concluding no deed exists."
        )
        return candidate, notes
    notes.append(
        f"NOTE: town '{candidate}' not in _BARNSTABLE_TOWN_CODES. "
        f"Defaulting to BARN (Barnstable villages). "
        f"To filter by town, pass --town with the ALIS code or add an entry to _BARNSTABLE_TOWN_CODES."
    )
    return "BARN", notes


_NORFOLK_TOWN_CODES: dict[str, str] = {
    "AVON":         "AVON",
    "BELLINGHAM":   "BELL",
    "BRAINTREE":    "BRAI",   # ✓ confirmed live run 2026-04 (Sarno)
    "BROOKLINE":    "BRKL",
    "CANTON":       "CANT",
    "COHASSET":     "COHS",
    "DEDHAM":       "DEDH",
    "DORCHESTER":   "DORC",
    "DOVER":        "DOVE",
    "FOXBOROUGH":   "FOXB",   # ✓ confirmed live run 2026-05-16 (Sarno)
    "FRANKLIN":     "FRKL",
    "HOLBROOK":     "HLBK",
    "HYDE PARK":    "HYDE",
    "MEDFIELD":     "MEDF",
    "MEDWAY":       "MDWY",
    "MILLIS":       "MILS",
    "MILTON":       "MLTN",
    "NEEDHAM":      "NDHM",
    "NORFOLK":      "NORF",
    "NORWOOD":      "NRWD",
    "PLAINVILLE":   "PLNV",
    "QUINCY":       "QUIN",   # ✓ confirmed via skill notes
    "RANDOLPH":     "RAND",
    "ROXBURY":      "ROXB",
    "SHARON":       "SHRN",
    "STOUGHTON":    "STOU",
    "WALPOLE":      "WALP",
    "WELLESLEY":    "WELL",
    "WEST ROXBURY": "WROX",
    "WESTWOOD":     "WSTD",
    "WEYMOUTH":     "WEYM",   # WEYB returned no results 2026-06-10; WEYM confirmed correct (LC01D form)
    "WRENTHAM":     "WREN",
}


def _norfolk_resolve_town(town_arg: str, base_name: str) -> tuple[str, list[str]]:
    """
    Resolve --town arg to an ALIS town code for Norfolk County.

    Returns (code, notes_list). The code is suitable for the W9TOWN URL parameter;
    notes_list is empty on a clean resolve and contains a hint string when
    falling back to *ALL or when an unknown candidate is passed through.

    Accepts:
      - empty string → derive town from base_name (e.g. "...Braintree - Smith" → "BRAINTREE")
      - town name (any case): looked up in _NORFOLK_TOWN_CODES → ALIS code
      - ALIS code (4-5 uppercase letters): trusted, returned as-is
      - "*ALL": returned as-is
      - unrecognized name longer than 5 chars: NOTE logged, fall back to *ALL
    """
    notes: list[str] = []
    raw = (town_arg or "").strip()
    if raw.upper() == "*ALL":
        return "*ALL", notes
    candidate = raw.upper() if raw else _parse_town_from_base_name(base_name).upper()
    if not candidate:
        notes.append(
            "No --town provided and could not parse town from base_name. "
            "Falling back to *ALL (all Norfolk towns)."
        )
        return "*ALL", notes
    if candidate in _NORFOLK_TOWN_CODES:
        return _NORFOLK_TOWN_CODES[candidate], notes
    # v3.33 (item 17): same guard as Barnstable — a code-shaped token is only
    # trusted when it is a KNOWN code, or when the user passed it EXPLICITLY.
    # The old passthrough took ANY 4-5 letter last word of an address as a
    # town code, silently ("...Some Road Port - Smith" -> town 'PORT'),
    # scoping the search to a nonexistent town: zero rows, false
    # deed_not_found. A derived token is a town-name GUESS, never a code;
    # unknown derived names belong on the *ALL fallback below, which is the
    # safe direction (broader, never wrong).
    if candidate in set(_NORFOLK_TOWN_CODES.values()):
        return candidate, notes
    if raw and 4 <= len(candidate) <= 5 and candidate.isalpha():
        notes.append(
            f"NOTE: '{candidate}' is not a known Norfolk town name or ALIS "
            f"code — trusting it as a code ONLY because it was passed "
            f"explicitly via --town. A wrong code returns ZERO rows and a "
            f"false deed_not_found; if this run finds nothing, re-check the "
            f"town (or use *ALL) before concluding no deed exists."
        )
        return candidate, notes
    notes.append(
        f"NOTE: town '{candidate}' not in _NORFOLK_TOWN_CODES. "
        f"Falling back to *ALL — results will include all Norfolk towns. "
        f"To filter, pass --town with the ALIS code (e.g. --town BRAI for Braintree) "
        f"or add an entry to _NORFOLK_TOWN_CODES."
    )
    return "*ALL", notes


# Plymouth County grid uses short abbreviations for town names.  Most match via
# substring check (e.g. SCIT ⊂ SCITUATE).  A few do not — those need an entry
# here.  As of v2.9, dict entries are only required when a seller owns MULTIPLE
# Plymouth County properties (multi-result name search); single-result runs
# accept any unrecognized abbreviation and log a NOTE prompting the addition.
# Add new entries as observed from WARNING/NOTE messages in run output.
_PLYMOUTH_TOWN_ABBREVS: dict[str, str] = {
    "CARVER":        "CRVR",   # confirmed 2026-05-14 (address-search result row)
    "DUXBURY":       "DXBY",   # confirmed 2026-05-11 (grantor check output)
    "HALIFAX":       "HLFX",   # confirmed 2026-05-11
    "HINGHAM":       "HNGHM",  # confirmed 2026-05-13
    "MIDDLEBOROUGH": "MIDDO",  # confirmed 2026-05-13 (Novak run)
    "PLYMOUTH":      "PLMTH",  # confirmed 2026-05-14
    "KINGSTON":      "KGSTN",  # confirmed 2026-06-19 (Reyes/Beckwith run)
    "MARSHFIELD":    "MSHFD",  # confirmed 2026-07-08 (KDM Realty Corp run)
    "WHITMAN":       "WHTMN",  # confirmed 2026-09-16 (a two-row name search
                               # fired a needless town-mismatch retry)
    # v3.51 (item 50) — both confirmed 2026-07-08 by the town harvest and left
    # out for 2.5 months. The LAKEVILLE gap returned a MARION deed at exit 0.
    "LAKEVILLE":     "LKVL",   # confirmed 2026-07-08 (harvest); 2026-09-22 run
    "MARION":        "MRION",  # confirmed 2026-07-08 (harvest)
}

# v3.51 — the 27 Plymouth County municipalities, as the GRID spells them
# (the Towns dropdown says MIDDLEBORO). Used only to tell a grid town code
# that names some OTHER known town from one the script cannot recognise at
# all — the second is a dictionary gap, not evidence of a different town.
_PLYMOUTH_TOWNS: tuple[str, ...] = (
    "ABINGTON", "BRIDGEWATER", "BROCKTON", "CARVER", "DUXBURY",
    "EAST BRIDGEWATER", "HALIFAX", "HANOVER", "HANSON", "HINGHAM", "HULL",
    "KINGSTON", "LAKEVILLE", "MARION", "MARSHFIELD", "MATTAPOISETT",
    "MIDDLEBOROUGH", "NORWELL", "PEMBROKE", "PLYMOUTH", "PLYMPTON",
    "ROCHESTER", "ROCKLAND", "SCITUATE", "WAREHAM", "WEST BRIDGEWATER",
    "WHITMAN",
)

# Grid town cells that carry no town at all. `_town_matches_filter` must never
# see an empty code: "" is a substring of every town name, so it "matches".
_PLYMOUTH_TOWNLESS_CODES = frozenset({"", "NONE", "SEEBK"})


# ---------------------------------------------------------------------------
# Image download helpers
# ---------------------------------------------------------------------------

async def _download_viewer_image(page: Page, output_path: Path) -> str:
    """
    Download the deed image currently shown in the Plymouth image viewer.

    v3.47 (47a) — the viewer's <img> src is an Avenu ACSResource.axd request
    whose CNTWIDTH/CNTHEIGHT params set the SERVER-SIDE render size, and the
    default is the on-screen container (~527x682 px — a thumbnail). Saving
    that as the audit copy defeats the point of saving it. Rewrite to a
    2000 px render exactly as Middlesex South (v3.8) and Suffolk (v3.40) do
    on the same platform; fall back to the default src, then to an element
    screenshot, so a markup change degrades to the old behaviour instead of
    failing the run. The caller reports the method per page, and warns when
    any page was not the hi-res render.
    Returns: 'hires_src_download' | 'src_download' | 'screenshot' | 'failed'
    """
    src = None
    try:
        # .src (property) is already absolute; the attribute may be relative.
        src = await page.evaluate(
            "() => { const i = document.querySelector('#ImageViewer1_docImage');"
            " return i ? i.src : null; }"
        )
    except Exception:
        pass
    if not src:
        src = await page.get_attribute("#ImageViewer1_docImage", "src")
    if src and not src.startswith("http"):
        src = (f"https://titleview.org{src}" if src.startswith("/")
               else f"https://titleview.org/plymouthdeeds/{src}")

    if src and "ACSResource" in src:
        hi = re.sub(r"CNTHEIGHT=\d+", "CNTHEIGHT=2000", src)
        hi = re.sub(r"CNTWIDTH=\d+", "CNTWIDTH=1550", hi)
        if hi != src:
            try:
                resp = await page.request.get(hi)
                if resp.ok:
                    body = await resp.body()
                    if len(body) > 5000:  # sanity: not an error page / placeholder
                        output_path.write_bytes(body)
                        return "hires_src_download"
            except Exception:
                pass
    if src:
        try:
            response = await page.request.get(src)
            if response.ok:
                output_path.write_bytes(await response.body())
                return "src_download"
        except Exception:
            pass

    img_el = await page.query_selector("#ImageViewer1_docImage")
    if img_el:
        try:
            await img_el.screenshot(path=str(output_path))
            return "screenshot"
        except Exception:
            pass

    return "failed"


async def _parse_page_count(page: Page) -> int:
    """Read the total-pages label in the Plymouth image viewer."""
    label = (await page.text_content("#ImageViewer1_lblPageNum") or "").strip()
    m = re.search(r"of\s+(\d+)|/\s*(\d+)", label, re.IGNORECASE)
    if m:
        return int(m.group(1) or m.group(2))
    return 1


# ---------------------------------------------------------------------------
# Plymouth County search helper
# ---------------------------------------------------------------------------

async def _plymouth_search(page: Page, combined_name: str, party_type: str,
                           date_from: tuple = None,
                           doc_type_values: list = None) -> bool:
    """
    Navigate to Plymouth search, set party type, enter name, click Search.
    Ensures Name Search mode is active — the server may remember Property Search
    mode from a previous address-search call in the same browser session, which
    hides the name field. Switches back via __doPostBack if necessary.
    Returns True if the page loaded, False on timeout.

    v3.29 — optional SERVER-SIDE narrowing, used by the grantor check only
    (see _GRANTOR_WINDOW_LOOKBACK_DAYS):
      date_from       : (Y, M, D) recorded-date floor → ACSTextBox_DateFrom.
      doc_type_values : option values for ACSDropDownList_DocumentType, which
                        despite the id is a MULTI-select listbox of 586
                        entries. Used by the lien sweep.
    Both controls live on the Advanced panel and are hidden until
    BtnAdvanced is clicked — they exist in the DOM either way and are posted
    with the form (DateFrom is prefilled with the index floor, 8/6/1686), but
    Playwright will not fill a hidden input, so the panel is opened on demand.
    Neither is touched unless asked for, so the grantee search is unchanged.
    """
    await page.goto(PLYMOUTH_SEARCH, wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_selector("#SearchFormEx1_ACSTextBox_LastName1", timeout=5000)
    except Exception:
        # Form is in Property Search (or other) mode — switch to Name Search (LinkButton00)
        await page.wait_for_function("() => typeof __doPostBack === 'function'", timeout=10000)
        await page.evaluate("() => __doPostBack('Navigator1$SearchCriteria1$LinkButton00', '')")
        await page.wait_for_selector("#SearchFormEx1_ACSTextBox_LastName1", timeout=15000)

    if date_from or doc_type_values:
        if not await page.is_visible("#SearchFormEx1_ACSTextBox_DateFrom"):
            await page.click("#SearchFormEx1_BtnAdvanced")
            await page.wait_for_selector("#SearchFormEx1_ACSTextBox_DateFrom",
                                         state="visible", timeout=15000)
        if date_from and date_from > (0, 0, 0):
            await page.fill("#SearchFormEx1_ACSTextBox_DateFrom",
                            f"{date_from[1]}/{date_from[2]}/{date_from[0]}")
        if doc_type_values:
            await page.select_option(
                "#SearchFormEx1_ACSDropDownList_DocumentType", doc_type_values)

    await page.select_option("#SearchFormEx1_ACSRadioButtonList_PartyType1", party_type)
    await page.fill("#SearchFormEx1_ACSTextBox_LastName1", combined_name)
    await page.click("#SearchFormEx1_btnSearch")
    return True


# v3.50 — Recorded Land "Book Search" (Navigator LinkButton01).
_PLYMOUTH_BOOK_SEARCH_LINK = "Navigator1$SearchCriteria1$LinkButton01"


async def _plymouth_book_search(page: Page, book: str, pg: str,
                                timeout_ms: int = 30000) -> list:
    """
    v3.50 — open one Recorded Land instrument by Book/Page and return its
    result rows (one row per indexed party, OR and EE sides).

    Book Search is exact and NAME-INDEPENDENT: no prefix matching, no
    1000-row cap applied before a sort, no pager. That is what makes it the
    right tool for a --book/--page pin and for --verify-grantor-hit.

    Two traps are handled here rather than left to callers:
      * the results area can still show the PREVIOUS search's grid, so the
        rows are accepted only once the search banner names THIS book and
        page, and only rows whose Book/Page cells match are returned;
      * a zero-hit search leaves no new grid at all, which is returned as
        [] — the caller must treat that as "no instrument at this Bk/Pg",
        never as a clean result.

    Page size is set to 100 in the rare case one Bk/Pg carries more than
    20 party rows. Raises on navigation failure (callers retry once in a
    fresh context — sequential Book Searches in one session were measured
    timing out intermittently).
    """
    book = str(book).strip().lstrip("0") or "0"
    pg = str(pg).strip().lstrip("0") or "0"
    await page.goto(PLYMOUTH_SEARCH, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_function("() => typeof __doPostBack === 'function'",
                                 timeout=15000)
    if not await page.is_visible("#SearchFormEx1_ACSTextBox_Book"):
        await page.evaluate(
            f"() => __doPostBack('{_PLYMOUTH_BOOK_SEARCH_LINK}', '')")
        await page.wait_for_selector("#SearchFormEx1_ACSTextBox_Book",
                                     state="visible", timeout=15000)
    await page.fill("#SearchFormEx1_ACSTextBox_Book", book)
    await page.fill("#SearchFormEx1_ACSTextBox_PageNumber", pg)
    await page.click("#SearchFormEx1_btnSearch")

    banner = re.compile(rf"Book:\s*{re.escape(book)}\s+Page Number:\s*{re.escape(pg)}\b")
    waited = 0
    while waited < timeout_ms:
        await page.wait_for_timeout(500)
        waited += 500
        try:
            body = await page.inner_text("body")
        except Exception:
            continue
        # A zero-hit search shows this message and NO "Book: … Page Number:"
        # banner (measured 2026-09-16); the page was freshly loaded above,
        # so the message cannot be left over from an earlier search.
        if re.search(r"resulted in 0 hits", body, re.I):
            return []
        if banner.search(body):
            if re.search(r"(?<![0-9])0 rows\)", body) or not await page.query_selector(
                    'a[href*="GridView_Document$ctl02$ButtonRow"]'):
                # banner is for this search; give the grid a moment, then
                # accept an empty result only if it stays empty
                await page.wait_for_timeout(1500)
                if not await page.query_selector(
                        'a[href*="GridView_Document$ctl02$ButtonRow"]'):
                    return []
            break
    else:
        raise TimeoutError(f"Book Search for Bk {book}/Pg {pg} did not return "
                           f"within {timeout_ms // 1000} s")

    await _avenu_set_page_size_100(page)
    rows = await _read_all_result_rows(page)
    return [r for r in rows
            if (r.get("book") or "").lstrip("0") == book
            and (r.get("page") or "").lstrip("0") == pg]


async def _plymouth_open_and_download_instrument(
    context, book: str, pg: str, base_name: str, label: str,
    output_folder: Path, notes: list, errors: list,
) -> dict:
    """
    v3.50 — Book Search one instrument in a FRESH page, open its detail
    panel, and download every page image at the 2000 px render. Used by
    --verify-grantor-hit. Returns {"rows", "detail", "files", "ok"}.
    One retry in a new page on a search timeout.
    """
    out = {"rows": [], "detail": None, "files": [], "ok": False}
    for attempt in (1, 2):
        # Attempt 2 runs in a NEW browser context: the intermittent Book
        # Search timeouts were per-session and cleared with a fresh session.
        ctx = context if attempt == 1 else await context.browser.new_context(
            accept_downloads=True)
        vpage = await ctx.new_page()
        try:
            rows = await _plymouth_book_search(vpage, book, pg)
            out["rows"] = rows
            if not rows:
                notes.append(f"Book Search found NO instrument at Bk {book}/Pg {pg}.")
                return out
            live_ctl = rows[0]["ctl"]
            if await _open_detail_panel(vpage, ctl=live_ctl, expected_book=book):
                out["detail"] = await _read_detail_panel(vpage)
            link = await vpage.query_selector('a[href*="TabController1$ImageViewertabitem"]')
            if link:
                await link.click()
                await vpage.wait_for_timeout(1500)
            await vpage.goto(PLYMOUTH_VIEWER, wait_until="domcontentloaded", timeout=30000)
            await vpage.wait_for_selector("#ImageViewer1_docImage", timeout=20000)
            await vpage.wait_for_timeout(1500)
            total = await _parse_page_count(vpage)
            for n in range(1, total + 1):
                if n > 1:
                    before = await vpage.evaluate(
                        "() => document.querySelector('#ImageViewer1_docImage').src")
                    await vpage.click("#ImageViewer1_BtnNext")
                    for _ in range(40):
                        await vpage.wait_for_timeout(250)
                        now = await vpage.evaluate(
                            "() => document.querySelector('#ImageViewer1_docImage').src")
                        if now != before:
                            break
                    await vpage.wait_for_timeout(700)
                path = output_folder / f"{base_name} - {label}_p{n}.jpg"
                method = await _download_viewer_image(vpage, path)
                if method == "failed":
                    errors.append(f"{label}: page {n} download failed.")
                else:
                    out["files"].append(str(path))
                    notes.append(f"{label}: page {n} saved ({method}): {path.name}")
            out["ok"] = bool(out["files"]) and len(out["files"]) == total
            return out
        except Exception as e:
            if attempt == 2:
                errors.append(f"{label}: Bk {book}/Pg {pg} could not be opened "
                              f"({type(e).__name__}: {e}).")
                return out
            notes.append(f"{label}: first attempt failed ({type(e).__name__}); "
                         "retrying in a fresh page.")
        finally:
            try:
                await vpage.close()
                if ctx is not context:
                    await ctx.close()
            except Exception:
                pass
    return out


async def _plymouth_compound_surname_retry(
    page: Page,
    seller_last: str,
    result: dict,
) -> bool:
    """
    Retry a Plymouth grantee search using the SURNAME ONLY (blank first name),
    to catch hyphenated / compound surnames the combined 'LAST FIRST' field
    misses.

    Plymouth's name field prefix-matches the concatenated 'LASTNAME FIRSTNAME'
    index string.  When the true surname is hyphenated (e.g. 'WHITFIELD-BARROW'),
    a search for 'WHITFIELD ALAN' fails — after 'WHITFIELD' the index continues
    '-BARROW', not ' ALAN'.  A surname-only search 'WHITFIELD' prefix-matches
    'WHITFIELD-BARROW ...' and returns the row.  The caller must still filter the
    returned rows by first name (the surname prefix can match unrelated people).

    Returns True if the retry produced results, False otherwise.
    """
    await _plymouth_search(page, seller_last.upper().strip(), "I")
    if await _has_results(page, timeout_ms=15000):
        result["notes"].append(
            f"Compound-surname retry: surname-only search "
            f"'{seller_last.upper().strip()}' (blank first name) returned results "
            f"— will filter rows by first name. Handles hyphenated surnames "
            f"(e.g. 'WHITFIELD' → 'WHITFIELD-BARROW') that the combined name field misses."
        )
        return True
    result["notes"].append(
        f"Compound-surname retry: surname-only search "
        f"'{seller_last.upper().strip()}' also returned no results."
    )
    return False


async def _plymouth_address_search(
    page: Page,
    street_number: str,
    street_name: str,
    result: dict | None = None,
) -> bool:
    """
    Submit a Plymouth property address search (trust-vested fallback).

    The search page defaults to Name Search mode from a clean browser context.
    Property Search mode is reached by clicking LinkButton05 in the Navigator's
    Search Criteria panel. Confirmed from live DOM: LinkButton05 text = "Property Search".

    Use the first word of the street name for the broadest match
    (e.g. "WEXFORD" matches "Wexford Avenue").
    Returns True if the form was submitted; False on navigation timeout.

    The search is COUNTY-WIDE: no town filter is applied (v3.42 — see the
    comment at the form-fill step). Callers must scope by town afterwards
    against the results grid, not before it.
    

    Timing (v3.6): this path costs a full page reload PLUS a second
    __doPostBack to switch UI modes — structurally heavier than the plain
    name search, which only needs one. If `result` is passed, per-phase
    timings are appended to result["notes"] as a "[timing]" line so slow
    phases are visible in the JSON output instead of just total run time.
    """
    t0 = time.monotonic()
    await page.goto(PLYMOUTH_SEARCH, wait_until="domcontentloaded", timeout=30000)
    t1 = time.monotonic()
    # Switch to Property Search mode by firing the __doPostBack directly.
    # LinkButton05 ("Property Search") lives inside a collapsed accordion panel
    # so it cannot be clicked; calling __doPostBack bypasses the visibility check.
    await page.wait_for_function("() => typeof __doPostBack === 'function'", timeout=15000)
    t2 = time.monotonic()
    await page.evaluate("() => __doPostBack('Navigator1$SearchCriteria1$LinkButton05', '')")
    # Wait for the property search form to render after the AJAX postback
    await page.wait_for_selector("#SearchFormEx1_ACSTextBox_StreetNumber", timeout=15000)
    t3 = time.monotonic()
    await page.fill("#SearchFormEx1_ACSTextBox_StreetNumber", street_number)
    await page.fill("#SearchFormEx1_ACSTextBox_StreetName", street_name)
    # NO TOWN FILTER — deliberate; do not add one back without reading this.
    #
    # Until v3.42 this function tried to set #SearchFormEx1_ACSDropDownList_Towns
    # two ways and BOTH were wrong for the real markup, so the filter was never
    # once applied: the options are labelled in UPPERCASE ("HINGHAM") while the
    # code sent Title case, and their values are numeric ("100080") while the
    # code sent the town name. Both select_option() calls missed and execution
    # fell through to a bare `pass`. The v3.6 note here saw the symptom — the
    # pair burning ~60s of Playwright actionability timeout — and made the
    # failure fast rather than correct.
    #
    # Removing it rather than fixing it matches the Suffolk v3.40 decision,
    # where the Towns and Recorded Date filters were measured SILENTLY
    # SUPPRESSING ROWS and both were deleted. Plymouth's dropdown has the same
    # hazard: alongside the 27 towns it carries MULTIPLE TOWNS (100000), NONE
    # (100180), SEE BOOK (100260) and PLYMTH COLONY (100300). A deed conveying
    # parcels in more than one town is indexed under MULTIPLE TOWNS, so a
    # working town filter would hide it from the subject town's search.
    #
    # The search is therefore county-wide, which is what it has effectively
    # been all along. Town scoping happens AFTER the fact, in
    # _town_matches_filter() against the results grid, where a non-matching row
    # is visible and can be reported instead of silently absent.
    t4 = time.monotonic()
    await page.click("#SearchFormEx1_btnSearch")
    t5 = time.monotonic()
    if result is not None:
        result["notes"].append(
            "[timing] plymouth_address_search: "
            f"goto_search_page={t1-t0:.2f}s doPostBack_ready={t2-t1:.2f}s "
            f"mode_switch_postback={t3-t2:.2f}s fill_form={t4-t3:.2f}s "
            f"submit_click={t5-t4:.2f}s total={t5-t0:.2f}s "
            "(submit_click excludes the results-grid wait, logged separately "
            "by the caller's _has_results call)"
        )
    return True


# Terse Avenu/20-20 (Plymouth, Suffolk) document-type codes that do NOT convey
# title.  ALIS (Norfolk, Barnstable) spells its types out as whole words, so
# those are matched by substring instead (see _NON_CONVEYANCE_SUBSTR below).
_NON_CONVEYANCE_CODES = {
    "CR",          # Certificate / Instrument of Redemption (tax-title)
    "TT",          # Tax Taking
    "TAX",         # Tax lien / taking
    "MLC",         # Municipal Lien Certificate
    "ESMT",        # Easement
    "MTG",         # Mortgage
    "DIS",         # Discharge
    "REL",         # Release (of mortgage/lien — not a conveyance)
    "ASST",        # Assignment (Avenu code; ALIS uses ASSIGN)
    "TKG",         # Taking (eminent domain / tax)
    "NOTC",        # Notice
    "LIEN",        # Lien
    "ATTACH",      # Attachment
    "ASSIGN",      # Assignment
    "DCLN HMS",    # Declaration of Homestead
    "TR CRTF",     # Trustee's Certificate (not the conveyance itself)
    "BKCY",        # Bankruptcy
    "UCC",         # UCC financing statement
    "PLAN",        # Plan
    "AFFI",        # Affidavit
    "SUBORD",      # Subordination
    # -------------------------------------------------------------------
    # v3.36 (item 0a vocabulary harvest + item 13) — the FULL Plymouth
    # instrument-code list, harvested from the registry's own published
    # table: "Click here for abbreviations of document types" on
    # titleview.org/plymouthdeeds/ -> InstrAbbreviations.pdf ("INSTRUMENT
    # CODES WITH CORRESPONDING DESCRIPTIONS, effective November 3, 2003";
    # 61 codes). Everything below is non-conveyance; the ONLY conveyance
    # codes in that table are DEED and MDEED, both caught by the "DEED"
    # allowlist.
    #
    # TWO STRUCTURAL FACTS learned here, both of which caused item 13:
    #  1. The results grid TRUNCATES codes to 8 characters — the published
    #     `CONTN UCC` displays as `CONTN UC`, `DCLN HMSTD` as `DCLN HMS`.
    #     So the published spelling ALONE is not enough; the truncated form
    #     is what the classifier actually sees. Both are listed.
    #  2. Compound codes are TOKEN pairs, and `_classify_instrument` only
    #     calls a compound non-conveyance when EVERY token is known — so
    #     the individual halves (CONTN, UC, AMDT, DIS, REL, …) must be
    #     present or the pair falls through to 'unknown'. That is precisely
    #     how a Sunnova solar `CONTN UC` fixture-filing continuation fired
    #     a false CRITICAL deed-out on the Halloran run.
    # Same two-vocabulary lesson as v3.29's BKCY/BANKRUPTCY miss.
    #
    # DELIBERATELY OMITTED so they classify 'unknown' and WARN rather than
    # being quietly filed as encumbrances: DCRE (Decree) and ORDR (Order).
    # Both can affect or confirm title and deserve human eyes; the middle
    # tier exists for exactly this.
    # -------------------------------------------------------------------
    # Compound halves / short tokens (make the pair rule work)
    "CONTN", "CONT", "UC", "AMDT", "AMND", "SUBD", "DCLN", "CRTF", "ACPT",
    "APPT", "RSGN", "EXTN", "MDFN", "AGRT", "TRUST", "HMSTD", "HMS", "TR",
    "TAX", "CONTR", "LISPN", "OPTN", "ATT", "PR", "REL UCC", "REL TAX",
    # Whole codes from the published table
    "6D CRTF",      # 6D Certificate
    "ACPT TR",      # Acceptance of a Trustee
    "AFFT",         # Affidavit
    "AFFT DIS",     # Discharge of an Affidavit
    "AFFT TAX",     # Affidavit re Federal Tax Lien
    "AGRT",         # Agreement
    "AMDT MTG",     # Amendment of a Mortgage
    "AMDT TRUST", "AMDT TRU",      # Amendment of a Trust (+8-char form)
    "AMDT UCC", "AMDT UC",         # Amendment of a UCC Filing
    "APPT ACPT TR", "APPT ACP",    # Appointment & Acceptance of a Trustee
    "CONTN UCC", "CONTN UC",       # Continuation of a UCC Filing  <-- item 13
    "CRTF ATT",     # Certificate of Judgment re Assignment/Execution
    "CRTF ENTRY", "CRTF ENT",      # Certificate of Entry
    "DCLN HMSTD",                  # Declaration of Homestead (DCLN HMS above)
    "DCLN TRUST", "DCLN TRU",      # Declaration of Trust
    "DEATH CRTF", "DEATH CR",      # Death Certificate
    "DIS ATT",      # Discharge of an Attachment
    "DIS EXON",     # Discharge of Execution
    "DIS LISPN", "DIS LISP",       # Discharge of Lis Pendens
    "EXON",         # Execution
    "EXTN EXON", "EXTN EXO",       # Extension of an Execution
    "JGMT",         # Judgment
    "LSE",          # Lease
    "MDFN AGRT", "MDFN AGR",       # Modification Agreement
    "NOTC CONTR", "NOTC CON",      # Notice of Contract
    "NOTC LSE",     # Notice of Lease
    "NOTC OPTN", "NOTC OPT",       # Notice of an Option
    "OPTN",         # Option
    "OPTN AGRT", "OPTN AGR",       # Option Agreement
    "POA",          # Power of Attorney
    "REL",          # Release (already above; kept adjacent for the table)
    "RSGN TR",      # Resignation of Trustee
    "SUBD MTG",     # Subordination of Mortgage
    "VOTE",         # Vote
    "WAVR",         # Waiver
}

# Substrings that mark a non-conveyance instrument in ALIS full-word labels
# (and as a safety net for any spelled-out Avenu label).  Checked only AFTER
# the "DEED" allowlist, so a real deed (which always contains "DEED") is never
# mis-flagged even if its label also contains one of these words.
_NON_CONVEYANCE_SUBSTR = (
    "REDEM",        # REDEMPTION / CERTIFICATE OF REDEMPTION
    "TAX TAKING", "TAKING", "TAX LIEN", "TAX TITLE",
    "MORTGAGE", "DISCHARGE", "ASSIGNMENT", "RELEASE", "ATTACHMENT",
    "EASEMENT", "LIEN", "NOTICE", "HOMESTEAD", "PLAN", "BANKRUPT",
    "AFFIDAVIT", "CERTIFICATE", "SUBORDINAT", "TERMINAT",
    # UCC financing statements. Matched on the PREFIX, because the two
    # registries spell the SAME instrument differently and the exact literal
    # "FINANCING" silently missed one of them: ALIS (Barnstable Land Court)
    # indexes the type as "Finance Statement", observed live 2026-09-06 when
    # a solar-loan fixture filing AND its continuation both came back
    # UNRECOGNISED at the subject parcel and had to be read by hand. The
    # spelled-out form elsewhere is "FINANCING STATEMENT". "FINANC" covers
    # FINANCE / FINANCING / REFINANCE alike. Same lesson as the v3.29
    # BKCY-vs-BANKRUPTCY miss: pair a concept across EVERY vocabulary rather
    # than trusting one spelling. The terse Avenu side already has "UCC" and
    # the "CONTN UC" compounds in _NON_CONVEYANCE_CODES.
    "FINANC",
    # v3.36 — the spelled-out counterparts of the Plymouth code table
    # (ALIS labels, and Plymouth's own 301xxx range). Every concept is
    # paired across BOTH vocabularies here, which is the v3.29
    # BKCY/BANKRUPTCY lesson applied deliberately rather than after a miss.
    "CONTINUATION",     # CONTINUATION OF UCC  <-- item 13, spelled form
    "AMENDMENT",
    "LIS PENDENS",
    "EXECUTION",
    "JUDGMENT",
    "ATTORNEY",         # POWER OF ATTORNEY
    "AGREEMENT",
    "OPTION",
    "LEASE",            # also matches RELEASE, which is non-conveyance anyway
    "WAIVER",
    "VOTE",
    "RESIGNATION",
    "APPOINTMENT",
    "ACCEPTANCE",
    "TRUSTEE",          # TRUSTEE CERTIFICATE / RESIGNATION OF TRUSTEE
    "DECLARATION",      # DECLARATION OF HOMESTEAD / OF TRUST
    # Added 2026-08-13 by the loop this design exists to create: the
    # Whittaker re-run WARNED on an unrecognised 'COVENANT' at the subject
    # parcel (under the old fall-through it would have been a false
    # CRITICAL deed-out). A covenant/restriction binds land, it does not
    # convey it.
    "COVENANT",
    "RESTRICTION",
    # NOT listed, deliberately, so they classify 'unknown' and WARN:
    # "DECREE", "ORDER" — both can affect or confirm title.
)

# Terse codes / labels that DO convey title but do not contain the word "DEED".
# Avenu truncates "UNIT DEED" to "UNIT DEE".
_CONVEYANCE_CODES = {"UNIT DEE"}


def _classify_instrument(deed_type: str) -> str:
    """
    v3.36 (item 0a) — classify an index document-type three ways:

        'conveyance'     — contains "DEED" or is a known conveyance code
        'non_conveyance' — matches the non-conveyance vocabulary
        'unknown'        — neither; ALSO blank/None (missing information)

    This replaces the bool `_is_non_conveyance_instrument`'s fall-through,
    which returned "conveyance" for anything unrecognised — safe for the
    grantor check (over-flags: a `CONTN UC` solar-UCC continuation fired a
    false CRITICAL deed-out, item 13, costing a browser verification trip)
    but UNSAFE for row selection (an unknown type could be reported as the
    vesting deed without tripping `selected_row_is_not_a_deed`). The two
    roles need OPPOSITE defaults, so the classifier stops choosing one:
    each caller decides what 'unknown' means on its own path. Blank types
    were already handled this way (kept for the grantor check, not-a-deed
    for selection) — 'unknown' finishes that idea for unrecognised types.

    Vocabulary covers BOTH the terse Avenu/20-20 codes used by Plymouth/
    Suffolk (e.g. "CR", "TT", "MLC") AND the spelled-out labels used by
    Browntech ALIS on Norfolk/Barnstable. Compound terse codes ("DIS REL",
    "CONTN UC") are non-conveyance only when EVERY token is itself a known
    non-conveyance code — a compound with an unseen half stays 'unknown'.
    Reference for the misindexed-name detection role: 60 Aldergate St,
    Middleborough (vesting deed misindexed "HANNIGAN" vs "HENNIGAN"; the
    only grantee hit was a Certificate of Redemption, type "CR").
    """
    t = (deed_type or "").upper().strip()
    if not t:
        return "unknown"
    if "DEED" in t or t in _CONVEYANCE_CODES:
        return "conveyance"
    if any(s in t for s in _NON_CONVEYANCE_SUBSTR):
        return "non_conveyance"
    if t in _NON_CONVEYANCE_CODES:
        return "non_conveyance"
    # Compound terse codes like "DIS REL" (discharge+release) or "CONTN UC"
    # (continuation of UCC): non-conveyance when every whitespace token is
    # itself a known non-conveyance code.
    tokens = t.split()
    if len(tokens) > 1 and all(tok in _NON_CONVEYANCE_CODES for tok in tokens):
        return "non_conveyance"
    return "unknown"


def _is_non_conveyance_instrument(deed_type: str) -> bool:
    """
    Selection-role wrapper over `_classify_instrument` (v3.36). True for
    anything that is not a KNOWN conveyance — including 'unknown' types,
    which now behave as not-a-deed on the selection paths so an unrecognised
    type trips `selected_row_is_not_a_deed` instead of being silently
    reported as the vesting deed (previously the fall-through kept it as a
    deed candidate AND let it pass that guard). Every Plymouth filter that
    uses this falls back to the unfiltered set when nothing survives, so
    the flip can narrow a selection but never zero one out.

    Grantor-check call sites must NOT use this wrapper — they call
    `_classify_instrument` directly, because dropping or CRITICAL-flagging
    an unknown type are both the wrong default there (the middle tier
    exists precisely for them).
    """
    return _classify_instrument(deed_type) != "conveyance"


async def _plymouth_address_fallback(
    page: Page,
    street_number: str,
    street_name: str,
    result: dict,
    town: str = "",
    seller_rows: list | None = None,
) -> dict | None:
    """
    Run a Plymouth property-address search and return the most recently
    recorded deed-type row, or None. v3.51: the pick is scoped to `town`
    first (_plymouth_scope_rows_to_town) — the search itself is county-wide.

    An address search is index-name-independent, so it recovers the vesting (or
    most-recent) deed when a grantee name search misses it — most often because
    the grantee was misindexed under a misspelled name.  When the named seller
    has since conveyed the property out, the most-recent deed surfaced here is
    the out-conveyance, which is exactly the signal that the seller is no longer
    the record owner (v3.3).
    """
    await _plymouth_address_search(page, street_number, street_name, result=result)
    t_submit = time.monotonic()
    has_results = await _has_results(page, timeout_ms=15000)
    t_results = time.monotonic()
    result["notes"].append(
        f"[timing] plymouth_address_fallback: wait_for_results_grid="
        f"{t_results-t_submit:.2f}s"
    )
    if not has_results:
        result["notes"].append("Address-search fallback: no results.")
        return None
    # v3.13 — page size before sort (the 100/page postback drops the sort), then
    # walk every pager page so an older deed is not stranded on page 2+.
    await _avenu_set_page_size_100(page)
    await _sort_results_by_date_desc(page)
    t_sort = time.monotonic()
    addr_rows = await _read_all_result_rows_paginated(
        page, notes=result["notes"], flags=result
    )
    t_read = time.monotonic()
    result["notes"].append(
        f"[timing] plymouth_address_fallback: sort_by_date={t_sort-t_results:.2f}s "
        f"read_rows={t_read-t_sort:.2f}s"
    )
    result["notes"].append(
        f"Address-search fallback returned {len(addr_rows)} row(s)."
    )
    deed_rows = [
        r for r in addr_rows
        if not _is_non_conveyance_instrument(r.get("deed_type", ""))
    ]
    if deed_rows:
        addr_rows = deed_rows
        result["notes"].append(
            f"Address-search fallback: filtered to {len(addr_rows)} deed-type row(s)."
        )
    if not addr_rows:
        result["notes"].append(
            "Address-search fallback: no deed-type rows after filtering."
        )
        return None
    addr_rows = _plymouth_scope_rows_to_town(
        addr_rows, town, result["notes"], "Address-search fallback",
        seller_rows=seller_rows,
    )
    try:
        row = max(
            addr_rows,
            key=lambda r: (int(r.get("book") or 0), int(r.get("doc_number") or 0)),
        )
    except (ValueError, TypeError):
        row = addr_rows[0]
    result["notes"].append(
        f"Address-search fallback selected Bk{row['book']} {row['deed_type']} "
        f"{row['recorded_date']} addr={row['street']!r} town={row['town']!r}."
    )
    return row


async def _has_results(page: Page, timeout_ms: int = 20000) -> bool:
    """Wait for the AJAX results grid to load. Returns True if results found."""
    try:
        await page.wait_for_selector(
            'a[href*="GridView_Document$ctl02$ButtonRow"]',
            timeout=timeout_ms
        )
        return True
    except Exception:
        return False


async def _sort_results_by_date_desc(page: Page) -> bool:
    """
    Sort the Plymouth search results grid by Rec Date descending (most recent first).

    Strategy:
      1. Click the 'Rec Date' column header using page.click() — avoids stale-
         handle errors that occur with ElementHandle.click() after AJAX re-renders.
      2. Wait for the AJAX grid to re-render.
      3. Compare book numbers of ctl02 vs ctl03: if ctl02 < ctl03 the sort is
         still ascending; click again for descending.
      4. Return True when descending is confirmed (or after two clicks).

    Selector: Avenu/20-20 ASP.NET GridView sort links fire __doPostBack with an
    argument like 'Sort$Rec Date'.  Exact href confirmed on first live run.
    Falls back gracefully if no matching header is found.
    """
    _SELECTORS = [
        'a[href*="Sort$Rec Date"]',           # most likely: __doPostBack sort arg
        'a[href*="Sort"][href*="Rec Date"]',  # fallback: href contains both tokens
        'th a:has-text("Rec Date")',           # last resort: text in header cell
    ]

    async def _find_working_selector() -> str:
        """Return the first selector that matches an element, or ''."""
        for sel in _SELECTORS:
            el = await page.query_selector(sel)
            if el:
                return sel
        return ""

    async def _click_header_and_wait() -> bool:
        """
        Click the Rec Date header and wait for the re-sorted grid to actually land.

        v3.13: waits for the grid FINGERPRINT to change, not for a selector or
        networkidle.  The old grid satisfies 'ctl02 exists' instantly, so the
        previous wait returned while the pre-sort rows were still on screen —
        the direction check below then read stale rows, wrongly concluded
        "ascending", and clicked again, toggling the grid back to ascending.
        (Live 2026-07-13: a "descending" sort returned rows starting at 1757.)
        """
        sel = await _find_working_selector()
        if not sel:
            return False
        before = await _avenu_grid_fingerprint(page)
        try:
            # page.click() handles its own retry logic — no stale-handle risk
            await page.click(sel, timeout=5000)
        except Exception:
            return False
        return await _avenu_wait_for_grid_change(page, before)

    async def _rec_date(ctl: str) -> tuple:
        """Parsed Rec Date of a row, as a sortable (y, m, d).  (0,0,0) if unread."""
        try:
            el = await page.query_selector(
                f'a[href*="GridView_Document$ctl{ctl}$ButtonRow_Rec Date"]'
            )
            return _parse_deed_date((await el.inner_text()).strip()) if el else (0, 0, 0)
        except Exception:
            return (0, 0, 0)

    async def _is_descending() -> bool:
        """True when the grid's first rows run newest → oldest."""
        d02, d03 = await _rec_date("02"), await _rec_date("03")
        if d02 == (0, 0, 0) or d03 == (0, 0, 0):
            return False  # can't tell
        return d02 >= d03

    if not await _click_header_and_wait():
        return False  # header not found — caller falls back to book-number selection

    # v3.13 — validate the direction by REC DATE, not by book number.
    #
    # The old check compared ctl02's book number to ctl03's and clicked again if
    # b02 < b03.  But Plymouth's digitized old records have book numbers that are
    # NON-MONOTONIC with date (v2.7's own finding: a 1978 deed at Bk32450 sits
    # alongside a 2002 deed at Bk22572) — the very reason row selection was moved
    # to a Python date sort.  Using that same broken proxy to decide whether the
    # grid is ascending meant the function could return True ("descending
    # confirmed") while the grid was actually ASCENDING.  Observed live
    # 2026-07-13: a sorted GRANT PETER search returned rows starting at 1757.
    #
    # The Rec Date column is the thing being sorted, so read it directly.
    if not await _is_descending():
        if not await _click_header_and_wait():
            return False
    return await _is_descending()


async def _read_all_result_rows(page: Page, cols: dict = None,
                                anchor: str = "Book") -> list:
    """
    Read all result rows (ctl02–ctl11) from the Grantee search results grid.
    Returns a list of row dicts, ordered as the registry returns them.

    v3.6: the entire grid is read in ONE page.evaluate() call so every cell
    comes from the same DOM snapshot — JS executes atomically on the page's
    main thread, so an UpdatePanel re-render cannot interleave mid-read.
    The prior per-cell query_selector loop (~90 round trips) could race with
    the re-render triggered by the date-sort header click, producing chimera
    rows: Book/Page cells from the pre-sort grid glued to Type/Date/Doc#
    cells of the post-sort grid.  (Observed 2026-07-08, KDM Realty Corp,
    Marshfield: DEED Doc#41886 reported at Bk46013/Pg9; actual Bk8827/Pg315.)
    The snapshot is re-taken until two consecutive reads are identical, so a
    read that lands on a mid-render DOM state is discarded.

    v3.7: reads up to 50 rows (ctl02–ctl51) instead of 10.  The Avenu grid
    renders ALL result rows on one page at least up to 14 rows (confirmed
    live 2026-07-08: KDM REALTY CORP grantor search rendered ctl02–ctl15 with
    no pager) — the old ctl11 cap silently dropped rows 11+, hiding the
    oldest instruments on long-held properties.

    v3.8: optional `cols` overrides the column-header map for Avenu sites
    whose grids use different column names (Middlesex South: 'File Date'
    instead of 'Rec Date', 'Type Desc' for the spelled-out type, no Town /
    Doc # / Reverse Party columns — unmatched columns read as '').

    v3.40: optional `anchor` names the column whose presence marks "this ctl
    row exists"; the loop stops at the first row missing it.  It defaulted to
    'Book' hard-coded, which silently returned ZERO rows on any grid without a
    Book column — exactly the shape of Suffolk's Registered Land (Land Court)
    grid, which is document-number based (Type | Name/Corporation | Doc. # |
    Type Desc. | File Date | Street # | Property Descr).  Land Court callers
    pass anchor='Type Desc'.
    """
    _COLS = cols or {
        # v3.50 — "party" (OR / EE) tells a Book Search's grantor rows from
        # its grantee rows; unused (and harmless) elsewhere.
        "party": "Party",
        "book": "Book", "page": "Page", "doc_number": "Doc",
        "deed_type": "Type", "recorded_date": "Rec Date",
        "street": "Street", "town": "Town",
        "reverse_party": "Reverse Party", "name": "Name",
    }

    async def _snapshot() -> list:
        return await page.evaluate(
            """(args) => {
                const cols = args.cols, anchor = args.anchor;
                const rows = [];
                // v3.13: scan to ctl102 — the grid is switched to 100 rows/page
                // (_plymouth_set_page_size_100), so the old ctl51 cap would have
                // silently dropped rows 51-100 of every full page.
                for (let i = 2; i < 103; i++) {
                    const ctl = String(i).padStart(2, '0');
                    const cell = (col) => {
                        const el = document.querySelector(
                            `a[href*="GridView_Document$ctl${ctl}$ButtonRow_${col}"]`);
                        return el ? el.innerText.trim() : '';
                    };
                    if (!cell(anchor)) break;
                    const row = { ctl: ctl };
                    for (const [key, col] of Object.entries(cols)) row[key] = cell(col);
                    rows.push(row);
                }
                return rows;
            }""",
            {"cols": _COLS, "anchor": anchor},
        )

    prev = await _snapshot()
    for _ in range(4):
        await page.wait_for_timeout(300)
        cur = await _snapshot()
        if cur == prev:
            return cur
        prev = cur
    return prev


# Avenu results-grid pager controls (Plymouth, Suffolk, Middlesex South).
# Discovered live 2026-07-13: the grid does NOT use the standard ASP.NET
# GridView 'Page$N' pager that _read_all_result_rows_paginated searched for
# (v3.7-v3.12) — so that pager walk never matched anything and every caller
# silently saw only the FIRST PAGE.  The real controls are these __doPostBack
# targets.  Default page size is 20; 100/Page is available and cuts the number
# of pages 5x.
_AVENU_PAGESIZE_100 = "DocList1$PageView100Btn"
_AVENU_NEXT         = "DocList1$LinkButtonNext"
# 10 pages x 100 rows = 1000, which is also the site's own hard result cap
# ("Your search results have been limited to the first 1000 records").
_AVENU_MAX_PAGES    = 10
_AVENU_ROW_CAP      = 1000


async def _avenu_truncation_banner(page: Page) -> str:
    """
    The site's own truncation notice, if it is on screen (v3.18).

    Avenu caps a result set server-side and says so in plain text —
    "Your search results have been limited to the first 1000 records".  Returns
    the matched sentence, or "" when the result set is complete.
    """
    try:
        return await page.evaluate(
            """() => {
                const t = (document.body.innerText || '');
                const m = t.match(/[^.\\n]*limited to the first[^.\\n]*/i);
                return m ? m[0].trim() : '';
            }"""
        )
    except Exception:
        return ""


async def _avenu_grid_fingerprint(page: Page) -> str:
    """
    Identity of what the grid is CURRENTLY showing: row count + the first and
    last row's Book/Doc cells.

    Every pager control is an ASP.NET UpdatePanel postback, and the OLD grid
    stays in the DOM until the re-render lands.  Waiting on a selector that the
    old grid also satisfies (e.g. 'ctl02 exists') therefore returns instantly
    and the caller reads STALE rows — which silently re-reads page 1 forever, or
    reads a 20-row page believing the 100/page switch took effect.  Callers wait
    for this fingerprint to CHANGE instead.
    """
    return await page.evaluate(
        """() => {
            const cell = (ctl, col) => {
                const el = document.querySelector(
                    `a[href*="GridView_Document$ctl${ctl}$ButtonRow_${col}"]`);
                return el ? el.innerText.trim() : '';
            };
            let n = 0, last = '';
            for (let i = 2; i < 103; i++) {
                const ctl = String(i).padStart(2, '0');
                if (!cell(ctl, 'Book')) break;
                n++;
                last = cell(ctl, 'Book') + '/' + cell(ctl, 'Doc');
            }
            return n + '|' + cell('02', 'Book') + '/' + cell('02', 'Doc') + '|' + last;
        }"""
    )


async def _avenu_wait_for_grid_change(page: Page, before: str, timeout_ms: int = 15000) -> bool:
    """
    Block until the grid's fingerprint differs from `before`, i.e. the postback's
    re-render has actually landed.

    This is the ONLY reliable "the grid updated" signal on these pages.  Waiting
    on a selector ('ctl02 exists') or on networkidle does not work: the OLD grid
    satisfies the selector immediately, so the wait returns while the stale rows
    are still on screen and the caller reads them.  That is what made the Rec
    Date sort appear to fail — the direction check ran against pre-sort rows,
    concluded "still ascending", and clicked the header a second time, toggling
    the grid back to ascending.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        await page.wait_for_timeout(250)
        try:
            if await _avenu_grid_fingerprint(page) != before:
                # Let the re-render settle so _read_all_result_rows' own
                # two-identical-snapshots check converges on the NEW grid.
                await page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False


async def _avenu_postback_and_wait(page: Page, target: str, timeout_ms: int = 15000) -> bool:
    """
    Fire an Avenu grid postback and wait until the grid content actually changes.

    Returns False if the control is absent or the grid never changed (treat as
    "nothing happened"), True once the new content is on screen.
    """
    if not await page.query_selector(f'a[href*="{target}"]'):
        return False
    before = await _avenu_grid_fingerprint(page)
    try:
        await page.evaluate(f"() => __doPostBack('{target}','')")
    except Exception:
        return False
    return await _avenu_wait_for_grid_change(page, before, timeout_ms)


async def _avenu_set_page_size_100(page: Page) -> bool:
    """
    Switch the results grid to 100 rows/page (default is 20).

    The site hides the page-size link for the size that is already active, so an
    absent link means either "already at 100" or "result set fits on one page".
    Either way there is nothing to do.  Safe to call unconditionally.
    """
    return await _avenu_postback_and_wait(page, _AVENU_PAGESIZE_100)


async def _avenu_click_next_page(page: Page) -> bool:
    """
    Advance the results grid to the next pager page.

    Returns False when there is no Next link — which is how the LAST page is
    detected (on the final page the site renders 'Previous' but no 'Next').
    """
    return await _avenu_postback_and_wait(page, _AVENU_NEXT)


async def _read_all_result_rows_paginated(
    page: Page,
    max_pages: int = _AVENU_MAX_PAGES,
    flags: dict = None,
    cols: dict = None,
    notes: list = None,
    anchor: str = "Book",
) -> list:
    """
    Read result rows across ALL pager pages (v3.13 — real pager, was dead code).

    v3.7-v3.12 looked for ASP.NET 'Page$N' links, which this grid does not use,
    so the walk never fired: every caller (grantor check, and after v3.13 the
    grantee/address searches too) saw only the first page.  Live confirmation
    2026-07-13: a grantee search for GRANT PETER reports "122 rows" but
    rendered only the first 20 — 102 rows, including any older vesting deed,
    were invisible.

    Now: switches to 100 rows/page, then walks with the Next button until it
    disappears (the last page has no Next).  Each row is tagged with
    `_pager_page` (1-based) because ctl numbers are only unique WITHIN a page —
    a caller that needs to click a row's Book link must first bring that pager
    page back on screen (see _plymouth_relocate_row).

    max_pages caps the walk at 10 pages (= 1000 rows at 100/page, which is also
    the site's own hard result cap).  A note is added if the cap is hit.

    v3.18 — SERVER-SIDE TRUNCATION DETECTION.  The walk terminating normally is
    NOT evidence that the result set is complete.  Avenu caps a search at 1000
    rows server-side, and because the cap is applied before the grid is built,
    page 10 legitimately has no Next link — so the walk ends by the same signal
    as a genuine last page and `capped` (which only fires when Next still exists
    at max_pages) stayed False.  Worse, the cap is applied BEFORE the Rec Date
    sort, so sorting only reorders the oldest 1000 rows and every newer
    instrument is invisible.  Live 2026-07-28, Town of Hingham / 319 Halstead St:
    a municipality grantee search returned exactly 1000 rows whose newest row was
    from 1981; the caller then selected a 1980 deed for an unrelated parcel and
    reported it at exit 0 with no warning.

    When `flags` is passed, `flags["results_truncated_at_cap"]` is set True on
    either signal (the site's own banner, or a row count at the cap) and a
    CRITICAL note is emitted.  Callers must treat a truncated set as unusable
    for deed selection.
    """
    # Idempotent — a no-op when the caller already switched to 100/page (which
    # run_plymouth does BEFORE sorting, since this postback drops the sort).
    await _avenu_set_page_size_100(page)

    rows: list = []
    prev_page_key = None
    pages_read = 0
    capped = False
    banner = ""

    for page_num in range(1, max_pages + 1):
        page_rows = await _read_all_result_rows(page, cols=cols, anchor=anchor)
        if not page_rows:
            break

        # Whole-page identity.  Rows are NOT deduplicated individually: the grid
        # renders one row per party, so a deed with two grantees is two rows that
        # legitimately share (book, doc) — and two rows can even share the party
        # name.  Only a repeat of the ENTIRE page means the postback was a no-op.
        page_key = [
            (r.get("book"), r.get("doc_number"), r.get("name"), r.get("deed_type"))
            for r in page_rows
        ]
        if page_key == prev_page_key:
            break
        prev_page_key = page_key

        for r in page_rows:
            r["_pager_page"] = page_num
        rows.extend(page_rows)
        pages_read = page_num

        # Check for the site's truncation banner BEFORE leaving the page — it is
        # rendered with the grid, so it is only reliably readable while a results
        # page is on screen.
        if not banner:
            banner = await _avenu_truncation_banner(page)

        if not await _avenu_click_next_page(page):
            break  # no Next link => last page (OR the server-side cap, see below)
        if page_num == max_pages:
            capped = True

    # v3.18 — two independent truncation signals.  The row count matters on its
    # own: the banner is not always rendered, and a run that reaches exactly the
    # cap is truncated whether or not the site says so.
    truncated = bool(banner) or len(rows) >= _AVENU_ROW_CAP
    if flags is not None:
        # STICKY — never downgraded by a later search.  run_plymouth passes the
        # same result dict to every search it runs (name, then an address-search
        # retry), and a clean retry must not erase the fact that an earlier
        # search was truncated: the CRITICAL note for it stays in notes either
        # way, and a flag that contradicts its own note is worse than a flag that
        # over-warns.  A false alarm costs a manual check; a cleared flag costs a
        # wrong parcel.
        flags["results_truncated_at_cap"] = (
            bool(flags.get("results_truncated_at_cap")) or truncated
        )

    if notes is not None:
        if capped:
            notes.append(
                f"WARNING: pager walk hit the {max_pages}-page cap ({len(rows)} rows). "
                f"Older instruments may still be unread."
            )
        if pages_read > 1:
            notes.append(
                f"Pager walk: read {len(rows)} row(s) across {pages_read} page(s)."
            )
        if truncated:
            notes.append(
                f"CRITICAL: the registry TRUNCATED this search at its {_AVENU_ROW_CAP}-row "
                f"server-side cap ({len(rows)} rows read"
                + (f"; site says: {banner!r}" if banner else "")
                + "). The cap is applied BEFORE the Rec Date sort, so the rows read are "
                "NOT the most recent ones and any newer instrument — including the "
                "vesting deed — is invisible. This result set is UNUSABLE for deed "
                "selection: do not report a deed chosen from it. Narrow the search "
                "(property address search, or a more specific party name). Common cause: "
                "the party is a municipality or other high-volume entity."
            )
    return rows


def _same_instrument(a: dict, b: dict) -> bool:
    """Two grid rows refer to the same recorded instrument."""
    return (
        a.get("book") == b.get("book")
        and a.get("doc_number") == b.get("doc_number")
        and a.get("name") == b.get("name")
    )


async def _plymouth_ensure_row_visible(
    page: Page,
    target: dict,
    research,
    cols: dict = None,
    anchor: str = "Book",
) -> str:
    """
    Make sure `target`'s row is on the CURRENTLY DISPLAYED pager page, and return
    its live ctl.

    ctl numbers are unique only WITHIN a pager page, and the pager walk leaves
    the grid parked on the LAST page.  So a row selected from page 1 can no
    longer be clicked by the ctl it was read with — that ctl now addresses a
    different row on the last page.  Clicking it would open the detail panel and
    image viewer for the WRONG DEED.  (_open_detail_panel's expected_book check
    would catch it and fail, but failing is not the same as being right.)

    Strategy:
      1. If the row is already on screen (common case: single-page result set,
         or the row happened to be on the last page), just re-derive its ctl.
      2. Otherwise replay the search and SCAN pages from the first until the row
         is found, matching on instrument identity — never on the stale ctl.

    The scan deliberately does not jump straight to the row's recorded
    `_pager_page`: the replayed grid is re-sorted from scratch, and if its row
    order differs at all from the walk's, that page number points somewhere else.
    Scanning is a couple of extra postbacks and is correct regardless of ordering.

    Returns the live ctl, or "" if the row could not be brought back.
    """
    for r in await _read_all_result_rows(page, cols=cols, anchor=anchor):
        if _same_instrument(r, target):
            return r["ctl"]

    await research()
    await _avenu_set_page_size_100(page)
    for _ in range(_AVENU_MAX_PAGES):
        for r in await _read_all_result_rows(page, cols=cols, anchor=anchor):
            if _same_instrument(r, target):
                return r["ctl"]
        if not await _avenu_click_next_page(page):
            break
    return ""


def _town_matches_filter(tf: str, t: str) -> bool:
    """
    Return True if grid town abbreviation `t` matches filter string `tf`.

    Tries three strategies in order:
    1. Substring in either direction — handles SCIT/SCITUATE, PLYM/PLYMOUTH, etc.
    2. Known-abbreviation lookup — handles HLFX/HALIFAX, DXBY/DUXBURY, etc.
    3. Reverse lookup (abbreviation passed as tf, full name in grid) — safety net.

    Both `tf` and `t` must already be uppercased by the caller.
    """
    if tf in t or t in tf:
        return True
    abbrev = _PLYMOUTH_TOWN_ABBREVS.get(tf)
    if abbrev and abbrev == t:
        return True
    # reverse: caller may have passed an abbreviation; check if it maps to t's full name
    for full, ab in _PLYMOUTH_TOWN_ABBREVS.items():
        if ab == tf and full == t:
            return True
    return False


def _plymouth_town_code_is_known(code: str) -> bool:
    """
    v3.51 — True if grid town code `code` is recognisably SOME Plymouth County
    town (substring or dictionary match). False means the script cannot read
    the code at all — a dictionary gap, which says nothing about which town
    the row is in.
    """
    c = (code or "").strip().upper()
    if c in _PLYMOUTH_TOWNLESS_CODES:
        return False
    return any(_town_matches_filter(full, c) for full in _PLYMOUTH_TOWNS)


def _plymouth_unknown_town_codes(rows: list) -> list:
    """v3.51 — distinct grid town codes in `rows` that name no known town."""
    seen: list = []
    for r in rows:
        c = (r.get("town") or "").strip().upper()
        if (c and c not in _PLYMOUTH_TOWNLESS_CODES and c not in seen
                and not _plymouth_town_code_is_known(c)):
            seen.append(c)
    return seen


def _plymouth_scope_rows_to_town(
    rows: list,
    town: str,
    notes: list,
    label: str,
    seller_rows: list | None = None,
) -> list:
    """
    v3.51 (item 50) — scope ADDRESS-search rows to the subject town before a
    row is picked from them.

    The address search has been county-wide since v3.42 (the Towns dropdown
    filter never applied and was removed), and v3.42 said town scoping would
    happen afterwards against the grid. It never did: every address pick took
    the highest Book across the county, so a same-numbered street in another
    town could win — live 2026-09-22, a LAKEVILLE subject returned the same
    house number on a same-named road in MARION at exit 0 (the Lakeville row
    carried 'LKVL', which the dictionary did not know).

    Tiers, first non-empty wins:
      1. rows whose town code matches `town`;
      2. rows at a Bk/Pg that the seller's own grantee search also returned
         (`seller_rows`) — the seller's deed at this address, whatever its
         town code says; this is what survives a future dictionary gap;
      3. rows with no town indexed (blank / NONE / SEEBK) — not provably in
         another town, but unverified, and said so;
      4. otherwise every row is indexed to another town: returned unchanged
         with a CRITICAL note, and the final town guard flags the selection.
    """
    if not town or not rows:
        return rows
    tf = town.strip().upper()

    def _code(r: dict) -> str:
        return (r.get("town") or "").strip().upper()

    def _fmt(rs: list) -> str:
        return ", ".join(
            f"Bk{r.get('book')}/{r.get('page')} {r.get('street')!r} town={_code(r)!r}"
            for r in rs[:10]
        ) + (f", ...(+{len(rs) - 10} more)" if len(rs) > 10 else "")

    matched = [r for r in rows
               if _code(r) not in _PLYMOUTH_TOWNLESS_CODES
               and _town_matches_filter(tf, _code(r))]
    if matched:
        dropped = [r for r in rows if r not in matched]
        if dropped:
            notes.append(
                f"{label}: scoped to town '{town}' — kept {len(matched)} of "
                f"{len(rows)} row(s); set aside {len(dropped)} indexed to other "
                f"towns or none: {_fmt(dropped)}.")
        return matched

    unknown = _plymouth_unknown_town_codes(rows)
    if seller_rows:
        keys = {(str(r.get("book")), str(r.get("page"))) for r in seller_rows}
        linked = [r for r in rows
                  if (str(r.get("book")), str(r.get("page"))) in keys]
        if linked:
            notes.append(
                f"WARNING: {label}: no row is indexed to town '{town}', but "
                f"{len(linked)} row(s) at this address are ALSO in the seller's "
                f"own grantee search — using those: {_fmt(linked)}."
                + (f" Town code(s) {unknown} are unknown to the script — if one "
                   f"is '{town}', add it to _PLYMOUTH_TOWN_ABBREVS."
                   if unknown else ""))
            return linked

    townless = [r for r in rows if _code(r) in _PLYMOUTH_TOWNLESS_CODES]
    if townless:
        notes.append(
            f"WARNING: {label}: no row is indexed to town '{town}'; using the "
            f"{len(townless)} row(s) with NO town indexed and setting aside "
            f"{len(rows) - len(townless)} indexed to other towns. The town of "
            f"the selection is UNVERIFIED — confirm it on the deed.")
        return townless

    notes.append(
        f"CRITICAL: {label}: EVERY row is indexed to a town other than "
        f"'{town}' ({_fmt(rows)}). The selection below is probably a "
        f"same-numbered street in ANOTHER TOWN — do not use it until the deed "
        f"itself shows the subject town."
        + (f" Town code(s) {unknown} are unknown to the script; if one of them "
           f"is '{town}', add it to _PLYMOUTH_TOWN_ABBREVS and re-run."
           if unknown else ""))
    return rows


def _street_matches_filter(street_filter: str, street: str) -> bool:
    """
    Return True if the grid's Street cell `street` refers to the street named by
    `street_filter` (the first street-name word parsed from --base-name).

    The grid renders the street as "18 KESTREL AVE", "23 HARROWGATE DR",
    "18 KESTREL AVE &OTHERS", etc., so a substring check on the street-name word
    is sufficient and tolerates the varying suffix (AVE/AVENUE/DR/ST) and the
    "&OTHERS" multi-parcel marker.  Both arguments are uppercased here, so the
    caller need not.
    """
    sf = _addr_norm(street_filter).strip()   # v3.47 — apostrophes dropped both sides
    s = _addr_norm(street).strip()
    if not sf or not s:
        return False
    return sf in s


def _select_best_row(
    rows: list,
    town_filter: str,
    prefer_first: bool = False,
    street_filter: str = "",
) -> dict | None:
    """
    Pick the best-matching result row given an optional town filter string and
    (v3.12) an optional street filter.

    When town_filter is provided, always try to find a town-matching row first —
    even after a date-descending sort (prefer_first=True).  The seller may own
    property in multiple towns; without a town filter the most-recently-recorded
    deed could be for the wrong property.

    v3.12 — street_filter narrows the town-matched set further.  A seller who owns
    several properties in the SAME town defeats the town filter entirely: every
    candidate row matches the town, so the most-recently-recorded one wins even if
    it is a different parcel.  (Reference: Peter Grant, Hingham, 2026-07-13 — the
    name search selected a DEED for 23 Harrowgate Dr while the subject property was
    18 Kestrel Ave; both rows carried town HNGHM, so the town-mismatch retry never
    fired.)  When street_filter is supplied, rows whose Street cell names that
    street are preferred; if none do, the town-matched set is used unchanged so a
    property with missing/odd street data still selects as before.

    prefer_first=True  — rows are expected to be date-sorted descending (e.g. by
                         Python sort in run_plymouth v2.7+); return the first
                         matching row (most recently recorded for the correct
                         town/street), or rows[0] if no match.
    prefer_first=False — fallback when sort unavailable: pick the row with the
                         highest book number as a proxy for most-recently-recorded.

    Town matching: uses _town_matches_filter(), which handles substring cases
    ("Scituate" ↔ "SCIT", "Plymouth" ↔ "PLYMO") and known non-substring
    abbreviations ("Halifax" ↔ "HLFX", "Duxbury" ↔ "DXBY").
    Street matching: uses _street_matches_filter() (substring on the street-name word).
    """
    if not rows:
        return None

    def _pick(candidates: list) -> dict:
        if prefer_first:
            return candidates[0]  # first = most recently recorded (rows are date-desc)
        try:
            return max(candidates, key=lambda r: int(r["book"]))
        except (ValueError, TypeError):
            return candidates[0]

    if town_filter:
        tf = town_filter.upper()

        def town_matches(row: dict) -> bool:
            t = (row.get("town") or "").upper()
            return bool(t) and t != "NONE" and _town_matches_filter(tf, t)

        matched = [r for r in rows if town_matches(r)]
        if matched:
            # v3.12 — same-town multi-property disambiguation.  Fall back to the
            # town-only set when no row names the expected street, so this can
            # only ever narrow a genuinely ambiguous set, never zero it out.
            if street_filter:
                street_matched = [
                    r for r in matched
                    if _street_matches_filter(street_filter, r.get("street", ""))
                ]
                if street_matched:
                    matched = street_matched
            return _pick(matched)
        # No town match — fall through; caller handles the warning and retry

    if prefer_first:
        return rows[0]

    try:
        return max(rows, key=lambda r: int(r["book"]))
    except (ValueError, TypeError):
        return rows[0]


async def _open_detail_panel(page: Page, ctl: str = "02", expected_book: str = "",
                             anchor_col: str = "Book") -> bool:
    """
    Click a cell link for the given ctl row to open the detail panel.
    If expected_book is provided, waits until the panel's Book/Page header
    contains that book number — prevents reading stale panel data left over
    from a previous row click (e.g., after a sort re-render).

    v3.40: `anchor_col` names the column whose link is clicked.  Any
    ButtonRow_ link in the row opens the same panel, but the default 'Book'
    does not EXIST on a Land Court grid (no Book column), so the click threw
    and the panel silently never opened — parties, consideration and the
    certificate reference all came back empty at exit 0.  Land Court callers
    pass anchor_col='Type Desc'.
    """
    try:
        await page.click(
            f'a[href*="GridView_Document$ctl{ctl}$ButtonRow_{anchor_col}"]')
        await page.wait_for_selector('a[href*="TabController1"]', timeout=10000)
        if expected_book:
            # Wait up to 5s for the panel to show the correct book number
            try:
                await page.wait_for_function(
                    f"() => document.body.innerText.includes('{expected_book}')",
                    timeout=5000
                )
            except Exception:
                pass  # proceed anyway — panel text check is best-effort
        return True
    except Exception:
        return False


async def _read_detail_panel(page: Page) -> dict:
    """
    Extract full grantor/grantee list and Consideration from the detail panel.
    Panel is #DocDetails1 region (AJAX, same page).
    """
    grantors = []
    grantees = []

    gg_links = await page.query_selector_all('a[href*="DocDetails1$GridView_GrantorGrantee"]')
    for link in gg_links:
        name = (await link.inner_text()).strip()
        if not name:
            continue
        # Role ("Grantor" / "Grantee") is in the last <td> of the same <tr>
        try:
            row_handle = await link.evaluate_handle("el => el.closest('tr')")
            tds = await row_handle.query_selector_all("td")
            role = (await tds[-1].inner_text()).strip() if tds else ""
        except Exception:
            role = ""
        if "Grantor" in role:
            grantors.append(name)
        elif "Grantee" in role:
            grantees.append(name)

    # Consideration — in the header table of the detail panel
    consideration = ""
    references = []
    try:
        panel_text = await page.inner_text('[id*="DocDetails"]')
        m = re.search(r"([\d,]+\.\d{2})\s*$", panel_text.strip(), re.MULTILINE)
        if not m:
            m = re.search(r"Consideration.*?([\d,]+\.\d{2})", panel_text, re.IGNORECASE | re.DOTALL)
        if m:
            consideration = m.group(1)
    except Exception:
        pass

    # v3.24 — the panel's References cross-ref list, naming later
    # homesteads, discharges, death certificates and related deeds against
    # this instrument. v3.50 — read the GRID, every pager page of it (see
    # _avenu_read_references); the v3.24 400-character text slice saw
    # page 1 only.
    refs = await _avenu_read_references(page)

    return {
        "grantors": grantors,
        "grantees": grantees,
        "consideration": consideration,
        "references": refs["references"],
        "references_expected": refs["expected"],
        "references_complete": refs["complete"],
        "references_note": refs["note"],
    }


# v3.50 — the detail panel's References grid and its pager. Same markup on
# every Avenu/20-20 site the plugin drives (Plymouth, Middlesex South,
# Suffolk — measured live 2026-09-16), and read once, by _read_detail_panel,
# which all three runners call.
_AVENU_REFS_GRID = '[id$="GridView_Document_Refs"]'
_AVENU_REFS_MAX_PAGES = 50   # 500 references; a guard, not a cap to reach

_AVENU_REFS_JS = """() => {
    const g = document.querySelector('[id$="GridView_Document_Refs"]');
    if (!g) return null;
    const rows = [];
    for (const tr of g.querySelectorAll('tr')) {
        // Data rows carry a ButtonRow link; the header and pager rows do not.
        if (!tr.querySelector('a[href*="ButtonRow"]')) continue;
        rows.push([...tr.children].map(td => td.innerText.trim())
                                  .filter(s => s).join(' '));
    }
    const pages = [...g.querySelectorAll('a[href*="Page$"]')]
        .map(a => (a.getAttribute('href').match(/Page\\$(\\d+)/) || [])[1])
        .filter(Boolean).map(Number);
    return {rows, pages};
}"""


async def _avenu_read_references(page: Page) -> dict:
    """
    v3.50 — read EVERY row of the detail panel's References grid.

    The grid shows 10 rows per page behind its own ASP.NET pager
    (__doPostBack('DocDetails1$GridView_Document_Refs','Page$N')), and the
    v3.24 reader took a fixed 400-character slice of the panel text — page
    1 only, and shorter still when the instrument names are long
    ("DECLARATION OF HOMESTEAD"). An instrument with 11+ references lost
    the rest SILENTLY: a subdivision covenant's 11th reference was the
    unconditional release of a lot, and a phased condominium's master deed
    showed 10 of its 19 amendments.

    Walks the pager by requesting Page$(k+1) until it is absent (the
    "..." link after a 10-page window carries that same argument), waits
    on grid CONTENT rather than a selector (the old grid stays in the DOM
    until the UpdatePanel re-render lands), and checks the total against
    the panel's own "References - N" caption. A short read is reported,
    never passed off as the whole list.

    Returns {"references": [str], "expected": int|None,
             "complete": bool|None, "note": str|None}. Never raises.
    """
    out = {"references": [], "expected": None, "complete": None, "note": None}
    try:
        panel_text = await page.inner_text('[id*="DocDetails"]')
        mc = re.search(r"References\s*-\s*(\d+)", panel_text)
        if mc:
            out["expected"] = int(mc.group(1))
        snap = await page.evaluate(_AVENU_REFS_JS)
        if snap is None:
            if out["expected"]:
                out["complete"] = False
                out["note"] = (
                    f"WARNING: the detail panel says References - "
                    f"{out['expected']} but the References grid could not be "
                    "read — the cross-reference list is MISSING, not empty.")
            else:
                out["complete"] = True if mc is None or out["expected"] == 0 else None
            return out

        seen = list(snap["rows"])
        current = 1
        stopped = ""
        while current < _AVENU_REFS_MAX_PAGES:
            if (current + 1) not in snap["pages"]:
                break
            before = snap["rows"]
            await page.evaluate(
                "(n) => __doPostBack('DocDetails1$GridView_Document_Refs',"
                " 'Page$' + n)", current + 1)
            changed = False
            for _ in range(60):          # up to ~15 s
                await page.wait_for_timeout(250)
                nxt = await page.evaluate(_AVENU_REFS_JS)
                if nxt and nxt["rows"] and nxt["rows"] != before:
                    # settle: take two identical reads (same rule as the grid)
                    await page.wait_for_timeout(300)
                    again = await page.evaluate(_AVENU_REFS_JS)
                    snap = again if again and again["rows"] == nxt["rows"] else nxt
                    changed = True
                    break
            if not changed:
                stopped = (f"page {current + 1} did not load")
                break
            seen += snap["rows"]
            current += 1
        else:
            stopped = f"stopped at the {_AVENU_REFS_MAX_PAGES}-page guard"

        out["references"] = seen
        if out["expected"] is not None:
            out["complete"] = len(seen) >= out["expected"] and not stopped
            if not out["complete"]:
                out["note"] = (
                    f"WARNING: the detail panel says References - "
                    f"{out['expected']} but only {len(seen)} were read"
                    + (f" ({stopped})" if stopped else "")
                    + ". The cross-reference list is INCOMPLETE — do not "
                    "read a missing reference as the absence of one.")
        else:
            out["complete"] = not stopped
        if current > 1 and out["complete"]:
            out["note"] = (f"References: read all {len(seen)} across "
                           f"{current} pager page(s).")
    except Exception as e:
        out["complete"] = False
        out["note"] = (f"WARNING: reading the References grid failed "
                       f"({type(e).__name__}: {e}) — "
                       f"{len(out['references'])} read; the list may be "
                       "INCOMPLETE.")
    return out


# ---------------------------------------------------------------------------
# Name parsing helpers
# ---------------------------------------------------------------------------

def _parse_name_for_search(full_name: str) -> str:
    """
    Convert a user-provided name in 'First [Middle] Last' order to Plymouth
    'LAST FIRSTMIDDLE' search format (no spaces between first/middle parts).

    Examples:
      'William J. Marchetti'    → 'MARCHETTI WILLIAMJ'
      'Thomas A. Marchetti'     → 'MARCHETTI THOMASA'
      'A. Ralph Marchetti, Jr.' → 'MARCHETTI ARALPH'

    Use this ONLY for user-provided seller names (--last / --first args).
    Do NOT use for names returned by the registry (detail panel) — use
    _clean_registry_name() instead.
    """
    name = full_name.upper().strip()
    name = re.sub(r'\b(JR|SR|II|III|IV|ESQ|PHD|MD)\.?\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[,.]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    parts = name.split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    last = parts[-1]
    first_parts = ''.join(parts[:-1])
    return f"{last} {first_parts}"


def _clean_registry_name(registry_name: str) -> str:
    """
    Clean a name already in Plymouth registry format ('LAST FIRST MI' or
    'LAST FIRST MI JR') for use as a Grantor search term.

    Strips suffixes (JR, SR, etc.) and punctuation; does NOT reorder parts.

    Examples:
      'MARCHETTI WILLIAM J'    → 'MARCHETTI WILLIAM J'
      'MARCHETTI THOMAS A'     → 'MARCHETTI THOMAS A'
      'MARCHETTI A RALPH JR'   → 'MARCHETTI A RALPH'
    """
    name = registry_name.upper().strip()
    name = re.sub(r'\b(JR|SR|II|III|IV|ESQ|PHD|MD)\.?\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[,.]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _parse_street_from_base_name(base_name: str) -> tuple:
    """
    Parse street number and first street-name word from a base_name string.
    Format: "NUM STREET [REST] - LASTNAME"
    Returns (street_number, street_name_first_word_uppercase) or ("", "").

    Examples:
      "121 Wexford Avenue Hingham - Castellano" → ("121", "WEXFORD")
      "62 Halyard Way Plymouth - Donnelly"     → ("62",  "HALYARD")
      "12 Cranmore Hill Lane Unit 203 Scituate - Marchetti" → ("12", "CRANMORE")
    """
    part = base_name.split(" - ")[0].strip()
    tokens = part.split()
    # Accept "155", "155R", "12A" etc. — Massachusetts rear-lot addresses use letter suffixes
    if len(tokens) >= 2 and re.match(r'^\d+[A-Za-z]{0,2}$', tokens[0]):
        # v3.47 (47d) — registries index "Baker's Lane" as BAKERS; a street
        # word carrying the apostrophe matched nothing downstream (the
        # index street guard fired a false mismatch and a needless
        # address-search retry, and the extracted-address check reported
        # ADDRESS MISMATCH on the correct parcel).
        return tokens[0], _addr_norm(tokens[1])
    return "", ""


def _street_words_from_base_name(base_name: str) -> str:
    """
    Street NAME + SUFFIX from a base name, with the house number and the
    trailing town token dropped — the input the combined address search wants
    (the suffix is then stripped by _alis_address_queries, which
    queries the prefix-matched stem).

    Stops at the first recognised suffix so a unit designator or the town does
    not leak into the query:
      "12 Birchwood Drive Dedham - Smith"          -> "BIRCHWOOD DRIVE"
      "39 Larkspur Road Unit 17C Osterville - Doe" -> "LARKSPUR ROAD"
      "7 Sycamore Weymouth - Roe"                  -> "SYCAMORE"   (no suffix)

    Returns "" when no street number leads the base name, which the caller
    must treat as "not asked", never as "nothing there".
    """
    num, first_word = _parse_street_from_base_name(base_name)
    if not (num and first_word):
        return ""
    tokens = base_name.split(" - ")[0].strip().split()[1:]
    words = []
    for tok in tokens:
        clean = _addr_norm(re.sub(r"[.,]", "", tok))   # v3.47 — apostrophes dropped
        words.append(clean)
        if clean in _STREET_SUFFIX_ALIASES or clean in _STREET_SUFFIX_EXPAND:
            break
    else:
        # no suffix seen — keep the first word only, since everything after it
        # may be the town (or a unit) and a wrong word narrows the query.
        words = words[:1]
    return " ".join(words).strip()


def _parse_deed_date(date_str: str) -> tuple:
    """
    Parse a Plymouth deed recorded-date string into a sortable (year, month, day) tuple.
    Plymouth format: "M/D/YYYY" (e.g. "9/27/1978", "8/5/2002").
    Falls back to year-only extraction. Returns (0, 0, 0) on total failure.
    Used for Python-side date sort — more reliable than book-number comparison.
    """
    s = (date_str or "").strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return (dt.year, dt.month, dt.day)
        except ValueError:
            continue
    m = re.search(r'\b(19|20)\d{2}\b', s)
    return (int(m.group()), 0, 0) if m else (0, 0, 0)


def _parse_town_from_base_name(base_name: str) -> str:
    """
    Extract the town name from a base_name string formatted as
    '[Address] [Town] - [LastName]'.  Returns the last purely-alphabetic
    token before the ' - ' separator (typically the town name).

    Examples:
      "155R Seabright Road Scituate - Marston"            → "SCITUATE"
      "62 Halyard Way Plymouth - Donnelly"           → "PLYMOUTH"
      "12 Cranmore Hill Lane Unit 203 Scituate - Marchetti" → "SCITUATE"
    """
    part = base_name.split(" - ")[0].strip()
    alpha_tokens = [t for t in part.split() if t.isalpha() and len(t) > 1]
    return alpha_tokens[-1].upper() if alpha_tokens else ""


# v3.29 — Plymouth ACSDropDownList_DocumentType option values for the
# all-years LIEN SWEEP: instruments against the PERSON that can reach
# after-acquired property, and so are NOT answered by a date window starting
# at acquisition. Enumerated live 2026-08-13 from the 586-entry listbox.
#
# PLYMOUTH CARRIES TWO PARALLEL VOCABULARIES and you need both. The 100xxx
# range holds the terse codes the results grid actually displays; the 301xxx
# range holds spelled-out names for the same concepts. They are DIFFERENT
# options and selecting one does not select the other. The first cut of this
# list took "301058 = BANKRUPTCY" and missed "100021 = BKCY" — the code this
# seller's four bankruptcy filings (1990/1995/1999/2001) are actually indexed
# under — so the live sweep returned two attachments and silently no
# bankruptcies. A sweep that quietly misses the thing it exists to find is
# worse than no sweep: pair every concept across both ranges.
#
# Creating and continuing instruments only. Terminations (DIS ATT, DIS LIEN,
# REL ATT, PAR REL OF LIEN, the *EXON exoneration variants, DISCHARGE OF
# ATTACHMENT) are excluded — they cannot encumber, and this workflow does not
# verify discharges either way. Power-of-attorney entries (P OF ATTY, DEED &
# P OF ATTY, REVOCATION OF P OF ATTY) match a naive "ATT" pattern and are
# deliberately NOT here. Parcel-level tax title/receipt entries are also out:
# they run with the land, so a pre-acquisition one belongs to a prior owner
# and this seller's grantor index would not carry it anyway.
_PLYMOUTH_LIEN_DOC_TYPES = [
    # Attachment family — terse (100xxx) and spelled (301xxx)
    "100019",   # ATTACHMENT
    "301056",   # ATTACHEMENT  (the registry's own misspelling, a real option)
    "100344",   # CERTIFICATE OF ATTACHMENT
    "100128",   # AFFT ATT
    "100153",   # AMDT ATT
    "100219",   # ASST ATT
    "100381",   # DCRE ATT
    "100435",   # EXTN ATT
    "100470",   # MDFN ATT
    "100486",   # MOTN ATT
    "100507",   # NOTC ATT
    "301162",   # NOTICE OF ATT
    "100524",   # ORDR ATT
    "100585",   # PR ATT
    # Execution / judgment
    "301127",   # EXECUTION
    "301047",   # ASST EXECUTION
    "301134",   # JUDGMENT
    # Bankruptcy — BOTH spellings (see note above)
    "100021",   # BKCY      ← the code the grid actually shows
    "301058",   # BANKRUPTCY
    # Liens
    "100042",   # LIEN
    "301052",   # ASST LIEN
    "300955",   # TAX LIEN
    "300994",   # PR LIEN
    "100663",   # SUBD LIEN
    "100672",   # SUBD TAX LIEN
    # Levy
    "100088",   # LEVY
]


async def _grantor_check_search(
    g_page: Page,
    search_name: str,
    original_book: str,
    original_doc: str = "",
    date_from: tuple = None,
    doc_type_values: list = None,
) -> list:
    """
    Run a Grantor search for search_name, return rows that are NOT the original deed.
    Fixes vs v2.0:
      - No '_0' suffix on column name (matches 'ButtonRow_Doc. #_0' correctly)
      - ctl numbering uses f'{n:02d}' (handles n >= 10)
    v3.6: rows are read via the atomic _read_all_result_rows snapshot, and the
    original-deed skip requires a doc-number match when available (book alone
    wrongly excluded same-book purchase-money mortgages).
    """
    await _plymouth_search(g_page, search_name, "D", date_from=date_from,
                           doc_type_values=doc_type_values)
    rows = []
    if not await _has_results(g_page, timeout_ms=15000):
        return rows

    # Sort descending so post-acquisition deeds appear first (most relevant to title)
    await _sort_results_by_date_desc(g_page)  # best-effort; non-fatal if header not found

    # v3.6: atomic grid snapshot (see _read_all_result_rows).  The prior
    # per-cell loop here had the same UpdatePanel race as the grantee grid —
    # a blank Book cell read mid-render caused an early break that silently
    # dropped grantor-check rows (observed 2026-07-08: 7 hits on run 1 vs 4
    # on run 3 for the identical KDM REALTY CORP search).
    # v3.7: reads all rendered rows (up to 50/page) and walks pager pages if
    # present — the old ctl11 cap hid the oldest instruments (1989 MTG, 1994
    # ASST, 1995 Commonwealth TKG) on the 36-year-held KDM parcel.
    for r in await _read_all_result_rows_paginated(g_page):
        # Skip only the original deed itself (indexed under both party
        # types).  Matching on book alone is too aggressive: it dropped a
        # same-day purchase-money mortgage recorded in the same book as the
        # vesting deed (Bk08827 Doc#41887 MTG vs deed Doc#41886).
        if r["book"] == original_book and (
            not original_doc or not r["doc_number"] or r["doc_number"] == original_doc
        ):
            continue
        rows.append({
            "book":          r["book"],
            "page":          r.get("page", ""),   # v3.50 — for --verify-grantor-hit
            "doc_number":    r["doc_number"],
            "deed_type":     r["deed_type"],
            "recorded_date": r["recorded_date"],
            "grantee":       r["reverse_party"],
            "street":        r["street"],
            "town":          r["town"],
            "searched_name": search_name,
        })

    return rows


# v3.21 — Plymouth grantor-hit classification, most-relevant tier first.
# The ORDER of this tuple is the report/JSON sort order.
_PLYMOUTH_HIT_TIERS = (
    "subject",             # street number AND name match the subject street
    "possible_subject",    # street name matches, number missing/unconfirmed
    "unknown_same_town",   # no address indexed, but the subject town
    "other_same_town",     # a different street in the subject town
    "other_parcel",        # a different street in a different town
    "other_town",          # no address indexed, and a different town
)

_PLYMOUTH_HIT_TAGS = {
    "subject":           "SUBJECT PROPERTY",
    "possible_subject":  "possible subject — street name matches, number unconfirmed",
    "unknown_same_town": "parcel unknown (no address indexed) — subject town",
    "other_same_town":   "other street, subject town",
    "other_parcel":      "other parcel",
    "other_town":        "other town, no address indexed",
}


def _plymouth_classify_grantor_hit(row: dict, st_num: str, st_word: str,
                                   subject_town: str, acq_date: tuple) -> dict:
    """
    v3.21 — classify ONE Plymouth grantor-check hit against the subject
    parcel. Ported from the ALIS grantor-check filters (v3.11/v3.16) and
    strengthened: the Plymouth results grid carries a street + town cell
    per row, so the parcel question is answerable straight from the index
    with no PDF sampling (ALIS has no address in its index at all).

    Motivating run: James Merrick / 52 Kingsbury Rd, Hingham (2026-08-12).
    A grantor search on the common name `MERRICK JAMES` returned 93
    instruments — about forty of them 1870s Hull deeds belonging to a
    19th-century namesake — and every one had to be assessed by hand. Only
    three touched the subject parcel.

    NOTHING IS EVER DROPPED. Plymouth runs full-name searches only (named
    seller + each grantee off the deed), and per the ALIS rule a full-name
    hit is kept regardless of type or date — the seller's OWN mortgages,
    homesteads and liens arrive through exactly these searches. This
    classifies and ORDERS the hits instead, and marks the short set that
    genuinely needs judgment.

    Returns {parcel, pre_acquisition, conveyance, needs_review, tag}.

    `needs_review` is True when the hit is at (or cannot be excluded from)
    the subject parcel, OR when it is a conveyance-type instrument recorded
    on/after the acquisition date — the two ways a deed-out can present. A
    row with no indexed address is NEVER treated as a different parcel on
    that basis alone; it is only deprioritised when its TOWN also differs
    (the Keegan lesson: missing information is not a non-match).
    """
    street = (row.get("street") or "").strip()
    town   = (row.get("town") or "").strip().upper()
    # v3.53 (item 56) — `SEEBK` / `NONE` are PLACEHOLDERS the registry writes
    # on trust instruments, not towns. Read as a town, a placeholder counted
    # as positive evidence of ANOTHER town, so a same-day Trustee's
    # Certificate was demoted out of needs_review — and trustee changes are
    # exactly what decide WHO MUST SIGN. A placeholder now reads as blank.
    townless_code = bool(town) and town in _PLYMOUTH_TOWNLESS_CODES
    if townless_code:
        town = ""
    town_match = bool(subject_town) and _town_matches_filter(subject_town.upper(), town)

    if _alis_address_matches(st_num, st_word, street):
        parcel = "subject"
    elif _alis_street_word_matches(st_word, street):
        parcel = "possible_subject"
    elif street:
        parcel = "other_same_town" if town_match else "other_parcel"
    else:
        parcel = "unknown_same_town" if town_match else "other_town"

    row_date = _parse_deed_date(row.get("recorded_date") or "")
    # A row whose date will not parse is treated as post-acquisition — the
    # safe direction for a deed-out check.
    pre_acq = bool(acq_date > (0, 0, 0) and (0, 0, 0) < row_date < acq_date)
    # v3.36 (item 0a): three-way. 'unknown' is a middle tier — the CRITICAL
    # deed-out note keys on a KNOWN conveyance only; an unrecognised type
    # gets its own WARNING in finalize and stays in needs_review (never a
    # false CRITICAL — item 13 — and never dropped).
    instrument_class = _classify_instrument(row.get("deed_type") or "")
    conveyance = instrument_class == "conveyance"
    significance = _instrument_significance(row.get("deed_type") or "")

    # v3.37 (item 18) — a post-acquisition conveyance is promoted to
    # needs_review REGARDLESS of parcel, which is right when nothing locates
    # the hit and wrong when something does. On a common surname the
    # broad pass fills the review set with other people's parcels (Whittaker:
    # 33 of 34 rows, against v3.21's stated goal of "5 rows instead of 93").
    #
    # Demote ONLY on POSITIVE EVIDENCE that the hit is somewhere else.
    # Keying on the tier name would be wrong: `other_town` is reached BOTH
    # by "indexed in another town" AND by "no town cell at all" (a blank
    # town cannot match, so it falls through to the same tier), and
    # demoting the second is missing-information-read-as-a-non-match — the
    # defect this whole codebase is built against. So require a locating
    # signal to actually exist: a street (which by construction did not
    # match the subject) or a town (which did not match either).
    #
    # The KDM counter-fixture is what constrains this: its 8
    # `parcel unknown — subject town` rows are a CORRECT flood and must
    # stay, because the Plymouth index simply carries no address for them.
    # Demote ONLY on a TOWN mismatch, and only when a town was actually
    # indexed. Two deliberate narrowings:
    #  * `other_same_town` (same town, different street) is NOT demoted —
    #    same-town is exactly where this workflow's documented wrong-parcel
    #    traps live (a seller with two properties in one town; a street
    #    whose suffix the index ignores, Chestnut St vs Chestnut Pl). An
    #    address mismatch inside the subject town is not strong enough
    #    evidence to stop looking.
    #  * a BLANK town is not evidence of anything.
    located_elsewhere = (
        parcel in ("other_parcel", "other_town") and bool(town)
    )
    needs_review = (
        parcel in ("subject", "possible_subject", "unknown_same_town")
        # unknown counts like a conveyance here: membership must not shrink
        # for want of a recognised type.
        or (instrument_class != "non_conveyance" and not pre_acq
            and not located_elsewhere)
        # v3.38 — an instrument that can change WHO OWNS or WHO SIGNS is
        # never demoted for being a non-conveyance: a death certificate is
        # how a survivor takes title with no deed recorded.
        or (significance == "ownership_change" and not pre_acq
            and not located_elsewhere)
    )
    if townless_code and parcel == "unknown_same_town" and pre_acq:
        # v3.53 (item 56) — before this fix a placeholder row was never in
        # review; keep that for PRE-acquisition rows (a 1990s BKCY or an old
        # trust's paperwork cannot convey the subject away) so the fix can
        # only ADD post-acquisition rows, never flood the set with history.
        needs_review = False
    tag = _PLYMOUTH_HIT_TAGS[parcel]
    if townless_code and parcel == "unknown_same_town":
        # A blank town matches the subject town by substring, so the tier is
        # right (cannot be excluded) but "— subject town" would overstate it.
        tag = "parcel unknown (no address or town indexed)"
    tag += " | pre-acquisition" if pre_acq else ""
    return {
        "parcel": parcel,
        "pre_acquisition": pre_acq,
        "conveyance": conveyance,
        "instrument_class": instrument_class,
        "significance": significance,             # v3.38 ownership_change|burden|''
        "located_elsewhere": located_elsewhere,   # v3.37 (item 18) evidence
        "needs_review": needs_review,
        "tag": tag,
    }


# v3.38 (item 10 scope work) — instruments that are NOT conveyances but
# still bear on the two questions this workflow actually answers: does the
# purported owner still own it, and WHO are all the current owners /
# signers. Being filed under the generic "assess as an encumbrance, not a
# deed-out" note buried exactly the things that cause bad intake:
#   * a joint tenant or tenant-by-the-entirety DIES — the survivor owns the
#     whole parcel and NO DEED IS EVER RECORDED;
#   * a trust still owns it but a DIFFERENT TRUSTEE now signs (certificate,
#     appointment, resignation);
#   * a taking DIVESTS title with no deed from the owner at all;
#   * a probate decree / court order vests or confirms title.
# These are already returned by every full-name search (those are not
# type-restricted), so this is a SURFACING fix, not a search fix.
_OWNERSHIP_CHANGE_SUBSTR = (
    "DEATH", "DECEASED", "PROBATE", "ESTATE OF", "ADMINISTRAT", "EXECUT",
    "TAKING", "TRUSTEE", "GUARDIAN", "CONSERVATOR", "PARTITION",
    "DECREE", "ORDER", "DIVORCE", "SURVIVORSHIP", "HEIR",
    # v3.52 — foreclosure by entry: a recorded Certificate of Entry starts
    # the 3-year clock after which the lender holds title with NO deed.
    "CERTIFICATE OF ENTRY", "FORECLOS",
)
_OWNERSHIP_CHANGE_CODES = {
    "TT", "TKG",                      # tax taking / taking
    "DEATH CRTF", "DEATH CR",         # death certificate (+8-char grid form)
    "TR CRTF",                        # trustee's certificate
    "ACPT TR", "RSGN TR",             # acceptance / resignation of trustee
    "APPT ACPT TR", "APPT ACP",       # appointment & acceptance of a trustee
    "DCRE", "ORDR", "JGMT",           # decree / order / judgment
    "CRTF ENTRY", "CRTF ENT",         # v3.52 certificate of entry (+8-char)
}

# Instruments that burden the parcel without changing who owns it. The user
# asked for these alongside the ownership set (2026-08-14): a post-
# acquisition easement or restriction granted BY the owner is a real title
# matter to know about before closing, even though it conveys nothing.
_BURDEN_SUBSTR = ("EASEMENT", "COVENANT", "RESTRICTION", "RSTN")
_BURDEN_CODES = {"ESMT", "RSTNS"}


def _instrument_significance(deed_type: str, desc: str = "") -> str:
    """
    v3.38 — for an instrument that is NOT a conveyance, say WHY it might
    still matter: 'ownership_change' | 'burden' | ''.

    Deliberately independent of `_classify_instrument`: a DECREE is still
    'unknown' (it is not in the conveyance/non-conveyance vocabulary and
    must keep warning), and it is ALSO ownership-relevant. The two answer
    different questions — "did this convey?" and "does this change who owns
    or signs?" — and collapsing them is what buried the death certificate.

    v3.39 (item 22a) — `desc` is the registry's Document Description cell,
    and WITHOUT IT this function could not see a death certificate on ALIS.
    Plymouth indexes the terse code `DEATH CRTF` as the TYPE, but ALIS Land
    Court indexes a GENERIC type — `CERTIFICATE`, `AFFIDAVIT`, `DOCUMENT` —
    and puts the instrument's real nature in Desc ("DEATH OF <name>",
    "AFFIDAVIT NO DIVORCE"). Every substring in _OWNERSHIP_CHANGE_SUBSTR was
    therefore unreachable on that platform, and the v3.38 needs_review clause
    that depends on this answer never fired on the very case it was written
    for: the seller had died, title had passed to the survivor with no deed,
    and the death certificate was demoted out of the review set.

    SUBSTRINGS match type+desc; CODES stay keyed on the TYPE ALONE. Desc is
    staff-typed low-signal text — the v3.23 rule is that it may ESCALATE a
    hit, never dismiss one — and allowing an exact code match out of free
    text would let a Desc that merely mentions "TT" masquerade as a taking.
    Escalation is the safe direction: reading Desc can only ADD rows to
    needs_review, never remove one.
    """
    t = (deed_type or "").upper().strip()
    hay = (t + " " + (desc or "").upper().strip()).strip()
    if not hay:
        return ""
    if t in _OWNERSHIP_CHANGE_CODES or any(s in hay for s in _OWNERSHIP_CHANGE_SUBSTR):
        return "ownership_change"
    if t in _BURDEN_CODES or any(s in hay for s in _BURDEN_SUBSTR):
        return "burden"
    return ""


def _significance_note(rid: str, deed_type: str, date: str, where: str,
                       desc: str = "") -> str | None:
    """v3.38 — the elevated note for a non-conveyance that still bears on
    ownership or burdens the parcel. Returns None when neither applies, so
    the caller falls through to the generic encumbrance wording.

    v3.39 (item 22a) — takes the registry's Desc cell for the same reason
    the classifier does; without it an ALIS death certificate got the
    generic "assess as an encumbrance" wording, which is the opposite of
    the truth."""
    sig = _instrument_significance(deed_type, desc)
    if sig == "ownership_change":
        return (
            f"OWNERSHIP-RELEVANT: grantor hit {rid} ({deed_type} {date}) at "
            f"the SUBJECT property{where} is not a conveyance, but this "
            f"instrument type can change WHO OWNS the parcel or WHO MUST "
            f"SIGN — a death certificate vests a survivor with no deed ever "
            f"recorded; a trustee certificate/appointment/resignation changes "
            f"the signer; a decree or order can vest or confirm title; a "
            f"certificate of entry starts a foreclosure by entry that "
            f"passes title to the lender after three years with no deed."
            + _taking_caveat(deed_type)
            + " Confirm the CURRENT owners and signatories before drafting."
        )
    if sig == "burden":
        return (
            f"BURDEN ON THE PARCEL: grantor hit {rid} ({deed_type} {date}) at "
            f"the SUBJECT property{where} conveys nothing, but an easement, "
            f"covenant or restriction granted after the seller acquired the "
            f"parcel runs with the land — read it and disclose it."
        )
    return None


def _taking_caveat(deed_type: str) -> str:
    """
    v3.36 (item 0a, pre-existing caveat surfaced during the design) — a
    TAKING is classified non-conveyance so it never fires the deed-out
    CRITICAL, but unlike a mortgage or homestead it CAN divest title (tax
    taking, eminent domain). When one sits at the subject parcel, the
    encumbrance note must not describe it as a mere encumbrance. Returns
    the caveat sentence, or '' for non-taking types.
    """
    t = (deed_type or "").upper().strip()
    if "TAKING" in t or t in ("TKG", "TT"):
        return (" NOTE: a TAKING can divest title (tax taking / eminent "
                "domain) — check redemption or disposition status; do not "
                "treat as a mere encumbrance.")
    return ""


def _plymouth_grantor_sort_key(row: dict) -> tuple:
    """
    v3.21 — order grantor hits most-relevant first: subject parcel before
    unknown before other; post-acquisition before pre-acquisition;
    conveyances before non-conveyances; then newest first. Without this the
    one row that matters sits wherever the registry's date sort left it
    (Merrick: the three subject-parcel rows were #3, #4 and #5 of 93).
    """
    c = row.get("classification") or {}
    try:
        tier = _PLYMOUTH_HIT_TIERS.index(c.get("parcel", "other_town"))
    except ValueError:
        tier = len(_PLYMOUTH_HIT_TIERS)
    y, m, d = _parse_deed_date(row.get("recorded_date") or "")
    return (tier, c.get("pre_acquisition", False), not c.get("conveyance", False),
            -y, -m, -d)


def _plymouth_grantor_hit_str(row: dict) -> str:
    """v3.21 — one grantor-check hit as its report/JSON line, classification
    tag appended when the hit could be classified."""
    c = row.get("classification")
    return (
        f"Bk{row['book']} {row['deed_type']} {row['recorded_date']} "
        f"| Grantee: {row['grantee']} | {row['street']}, {row['town']} "
        f"| Doc#{row['doc_number']} | [found via: {row['searched_name']}]"
        + (f" | {c['tag']}" if c else "")
    )


def _plymouth_broaden_prefix_name(name: str) -> str:
    """
    v3.30 (item 11) — drop a trailing middle initial from a Plymouth
    grantor-search name.

    Plymouth's party field is a PREFIX match: the index entry must START
    WITH the query. So 'GRANT LAUREN S' cannot reach an instrument indexed
    as 'GRANT LAUREN', while the bare 'GRANT LAUREN' reaches both — 49 rows
    vs 14 on log 2026-08-13-001. The broad form is a strict superset, so it
    REPLACES the narrow one instead of adding a second search. This matters
    most for co-owner names, which come from the detail panel in whatever
    form THAT deed used, while the co-owner's later deed-out may be indexed
    without the initial. Same trap as the v3.5 compound-surname limitation,
    different axis.

    Only a trailing single letter (optionally with a period) is dropped,
    and only while at least two tokens remain: 'GRANT LAUREN' and
    'DE SOUSA MARIA' are returned untouched.
    """
    toks = name.split()
    if len(toks) >= 3:
        tail = toks[-1].rstrip(".")
        if len(tail) == 1 and tail.isalpha():
            return " ".join(toks[:-1])
    return name


def _plymouth_record_searches(result: dict, search_log: list) -> None:
    """
    v3.30 (item 11) — record what each grantor search actually ran and
    returned, into grantor_check.searches plus one readable note.

    Hits are de-duplicated across searches and tagged with the first search
    that found them, so a co-owner who signed the same instruments as the
    named seller contributes no visibly-new lines. Without this record,
    "searched, every row a duplicate" and "never searched" produce byte-
    identical output, and the only way to tell them apart is to re-run the
    co-owner's search by hand — which is exactly what the Grant / 23
    Harrowgate Dr run cost. Reporting zero rows as a clean answer when the
    search never ran is the recurring v3.20/v3.23/v3.29 failure.
    """
    gc = result.setdefault("grantor_check", {})
    gc["searches"] = search_log
    if not search_log:
        return
    errored = [s for s in search_log if s.get("status", "").startswith("ERROR")]
    lines = [f"Grantor searches: {len(search_log) - len(errored)} of "
             f"{len(search_log)} completed."]
    for s in search_log:
        if s.get("status", "").startswith("ERROR"):
            outcome = f"DID NOT RUN — {s['status']}; this name is an OPEN question"
        elif s["rows_returned"] == 0:
            outcome = "0 rows — searched, nothing indexed for this name"
        elif s["rows_new"] == 0:
            outcome = (f"{s['rows_returned']} rows, 0 new — searched; every row "
                       f"was already found by an earlier search name "
                       f"(duplicate, NOT skipped)")
        else:
            outcome = f"{s['rows_returned']} rows, {s['rows_new']} new"
        lines.append(f"  - '{s['name']}' [{s['label']}]: {outcome}")
    result.setdefault("notes", []).append("\n".join(lines))


def _plymouth_finalize_grantor_check(result: dict, rows: list, st_num: str,
                                     st_word: str, subject_town: str) -> None:
    """
    v3.21 — classify, order and summarise the Plymouth grantor-check hits,
    mutating `result` in place. Ported from the ALIS grantor-check filters
    (v3.11/v3.16) after the Merrick / 52 Kingsbury Rd run (2026-08-12), where
    the common name `MERRICK JAMES` returned 93 instruments — about forty of
    them 1870s Hull deeds belonging to a namesake — and all 93 had to be
    read by hand. Only three touched the subject parcel.

    NOTHING IS DROPPED. grantor_check.deeds still lists every hit; it is now
    ordered most-relevant first and each line carries a parcel tag. The new
    grantor_check.needs_review holds the short set that actually needs
    judgment, and grantor_check.summary the tier counts. On the Merrick set
    this is 5 rows instead of 93.

    Classification needs a street parsed from --base-name; without one
    (entity sellers, unparseable base names) every hit is left unclassified
    and reported for manual assessment exactly as before v3.21.
    """
    acq_date = _parse_deed_date(result.get("recorded_date") or "")
    classified = bool(st_num and st_word)
    if classified:
        for r in rows:
            r["classification"] = _plymouth_classify_grantor_hit(
                r, st_num, st_word, subject_town, acq_date)
        rows.sort(key=_plymouth_grantor_sort_key)
    else:
        result["notes"].append(
            "Grantor-hit classification skipped: no street number/name parsed "
            "from the base name — every hit below must be assessed manually "
            "by parcel."
        )

    gc = result["grantor_check"]
    gc["has_subsequent_deed"] = len(rows) > 0
    gc["deeds"] = [_plymouth_grantor_hit_str(r) for r in rows]
    review = [r for r in rows
              if not classified or r["classification"]["needs_review"]]
    gc["needs_review"] = [_plymouth_grantor_hit_str(r) for r in review]

    if classified:
        counts = {t: 0 for t in _PLYMOUTH_HIT_TIERS}
        for r in rows:
            counts[r["classification"]["parcel"]] += 1
        gc["summary"] = {
            "total": len(rows),
            "needs_review": len(review),
            "pre_acquisition": sum(
                1 for r in rows if r["classification"]["pre_acquisition"]),
            # v3.37 (item 18) — how many post-acquisition conveyance-type
            # hits were kept OUT of needs_review because an address or town
            # positively located them at another parcel. This is the
            # evidence behind a short review set: without it, "needs_review
            # is small" and "the classifier lost rows" look identical.
            "demoted_located_elsewhere": sum(
                1 for r in rows
                if r["classification"].get("located_elsewhere")
                and not r["classification"]["needs_review"]
                and r["classification"]["instrument_class"] != "non_conveyance"
                and not r["classification"]["pre_acquisition"]),
            **counts,
        }
        # A conveyance at the subject parcel recorded on/after the
        # acquisition date is the deed-out this whole check exists to find.
        for r in rows:
            c = r["classification"]
            if c["parcel"] != "subject" or c["pre_acquisition"]:
                continue
            if c["conveyance"]:
                result["notes"].append(
                    f"CRITICAL: grantor hit Bk{r['book']} Doc#{r['doc_number']} "
                    f"({r['deed_type']} {r['recorded_date']}) is a conveyance-type "
                    f"instrument at the SUBJECT property ({r['street']}, {r['town']}) "
                    "recorded on/after the acquisition — the seller may have deeded "
                    "the subject parcel out. Verify before closing."
                )
            elif c.get("instrument_class") == "unknown":
                # v3.36 (item 0a): the middle tier. Before this, an
                # unrecognised type here fired the CRITICAL above — a false
                # deed-out costing a browser verification trip (item 13,
                # CONTN UC). One line to read instead of a browser session.
                result["notes"].append(
                    f"WARNING: grantor hit Bk{r['book']} Doc#{r['doc_number']} "
                    f"has UNRECOGNISED type {r['deed_type']!r} at the SUBJECT "
                    f"property ({r['street']}, {r['town']}) — not classified. "
                    "Read the instrument (or its detail panel) to determine "
                    "whether it conveys or encumbers, and add the type to the "
                    "script vocabulary so future runs classify it."
                )
            else:
                # v3.38 — elevate the non-conveyances that still bear on WHO
                # OWNS / WHO SIGNS (death cert, trustee change, taking,
                # decree) and the ones that burden the parcel (easement,
                # covenant, restriction). Everything else keeps the generic
                # encumbrance wording.
                sig_note = _significance_note(
                    f"Bk{r['book']} Doc#{r['doc_number']}", r.get("deed_type"),
                    r.get("recorded_date"), f" ({r['street']}, {r['town']})")
                result["notes"].append(sig_note or (
                    f"Grantor hit Bk{r['book']} Doc#{r['doc_number']} "
                    f"({r['deed_type']} {r['recorded_date']}) affects the SUBJECT "
                    "property but is not a conveyance — assess as an encumbrance "
                    "(homestead/lien/mortgage), not as a deed-out."
                ))
        # v3.53 (item 56) — the note above keys on a SUBJECT address, so an
        # ownership-change instrument the index does not locate (a trustee
        # certificate carries no address) reached needs_review in silence.
        # Missing information is not a different parcel: say what it is.
        for r in rows:
            c = r["classification"]
            if (c["parcel"] == "subject" or c["pre_acquisition"]
                    or c.get("conveyance") or not c["needs_review"]
                    or c.get("significance") != "ownership_change"):
                continue
            result["notes"].append(
                f"OWNERSHIP-RELEVANT: grantor hit Bk{r['book']} "
                f"Doc#{r['doc_number']} ({r['deed_type']} {r['recorded_date']}) "
                f"could NOT be located to a parcel ({c['tag']}) — it may be at "
                "the subject property. This instrument type can change WHO "
                "OWNS the parcel or WHO MUST SIGN (a trustee certificate, "
                "appointment or resignation changes the signer; a death "
                "certificate vests a survivor with no deed). Read it and "
                "confirm the CURRENT owners and signatories before drafting."
            )

    if not rows:
        result["notes"].append(
            "Grantor check: no subsequent deeds found across all grantees — clean title."
        )
    elif classified:
        s = gc["summary"]
        result["notes"].append(
            f"Grantor check: {s['total']} instrument(s) found; {s['needs_review']} "
            f"need review (subject parcel: {s['subject']}, possible subject: "
            f"{s['possible_subject']}, unknown parcel in the subject town: "
            f"{s['unknown_same_town']}, plus any post-acquisition conveyance "
            f"that could NOT be located elsewhere). The other "
            f"{s['total'] - s['needs_review']} are other parcels/towns or "
            "pre-acquisition and are still listed in full in "
            "grantor_check.deeds, ordered most-relevant first. READ "
            "grantor_check.needs_review FIRST. A 'parcel unknown' tag means the "
            "index carried no address — that row was NOT ruled out."
            + (f" {s['demoted_located_elsewhere']} post-acquisition "
               "conveyance-type hit(s) were kept OUT of the review set because "
               "the index positively located them at a DIFFERENT parcel "
               "(street or town) — they are still in grantor_check.deeds; a "
               "row with no locating information at all is never demoted."
               if s.get("demoted_located_elsewhere") else "")
        )
    else:
        result["notes"].append(
            f"Grantor check: {len(rows)} subsequent deed(s) found — "
            "Claude must assess title flags."
        )


# ---------------------------------------------------------------------------
# Plymouth County — main workflow
# ---------------------------------------------------------------------------

async def run_plymouth(
    seller_last: str,
    seller_first: str,
    base_name: str,
    output_folder: Path,
    headless: bool,
    town: str = "",
    street_number: str = "",
    street_name: str = "",
    force_address_search: bool = False,
    lien_sweep: bool = False,
    target_book: str = "",
    target_page: str = "",
    verify_grantor_hit: str = "",
    on_images_ready=None,
) -> dict:
    """
    Plymouth County Registry of Deeds — full workflow:
    1. Grantee search → results grid → extract metadata
    2. Detail panel → full grantor/grantee list + consideration
    3. View Images → ImageViewerEx.aspx → download all pages
    4. Grantor check
    """
    result = {
        "status": "error",
        "registry": "Plymouth County",
        "registry_url": PLYMOUTH_SEARCH,
        "registry_system": "Avenu/20-20 (ASP.NET)",
        "book": None,
        "page": None,
        "document_number": None,
        "recorded_date": None,
        "deed_type": None,
        "consideration": None,
        "grantors": [],
        "grantees": [],
        "deed_property_address": None,
        # v3.21 — needs_review/summary are populated by the grantor-check
        # classifier; needs_review is the short set requiring judgment.
        # v3.30 — `searches` records what each grantor search actually ran
        # and returned, so a co-owner pass whose rows all duplicate the
        # named seller's is distinguishable from one that never ran.
        "grantor_check": {"has_subsequent_deed": False, "deeds": [],
                          "needs_review": [], "summary": None, "searches": []},
        # v3.24 — the detail panel's References cross-ref list (later
        # homesteads/discharges/related deeds against the selected deed).
        "detail_references": [],
        # v3.26 — the same data normalised into the shared cross-reference
        # shape used by every registry (leads, NOT discharge verification).
        "cross_references": [],
        "files": [],
        "total_pages_in_viewer": None,
        "found_via_address_search": False,
        "found_via_compound_surname": False,
        "selected_row_is_not_a_deed": False,
        # v3.51 (item 50) — the selected row is indexed to another town.
        "selected_row_town_mismatch": False,
        "results_truncated_at_cap": False,
        # v3.50 — set when --book/--page pinned the instrument via Book Search.
        "pinned_by_book_page": False,
        "grantor_hit_verification": None,
        "notes": [],
        "errors": [],
    }
    pinned = bool(target_book)

    # v3.47 (47c) — per-stage timings, as the ALIS flow has had since v3.31.
    _tm = _Timings()
    _tm.mark("STEP 1 - grantee search")

    # Plymouth name format: "LAST FIRST" (no comma, no spaces in compound first names)
    first_normalized = seller_first.upper().replace(" ", "")
    # v3.50 — .strip(): an entity seller passes --first "", which left a
    # trailing space, so the grantor check searched the entity TWICE
    # ("NAME " as the named seller and "NAME" off the detail panel). The
    # stripped string prefix-matches everything the spaced one did.
    combined_name = f"{seller_last.upper()} {first_normalized}".strip()
    # First token of the seller's first name, used to filter surname-only retry
    # results (e.g. "ALAN" matched against grantee "WHITFIELD-BARROW ALAN D").
    first_token = (seller_first.upper().split() or [""])[0]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # -----------------------------------------------------------
            # STEP 1 — GRANTEE SEARCH (with address-search fallback)
            # -----------------------------------------------------------
            found_via_address = False
            first_name_filter = ""  # set when the compound-surname retry fires

            if pinned:
                # v3.50 — --book/--page: open the named instrument by Book
                # Search. Exact and name-independent, so every name-search
                # trap (prefix match, misindexed name, the 1000-row cap
                # applied before the sort, same-town multi-parcel sellers)
                # is out of the path. The pin is reported, and the seller
                # and address are still CHECKED against it below — a pin is
                # an instruction about which instrument, not a guarantee it
                # is the right one.
                if not target_page:
                    result["errors"].append(
                        "--book on Plymouth needs --page too (Recorded Land "
                        "is addressed by Book AND Page).")
                    await browser.close()
                    return result
                pin_rows = []
                for attempt in (1, 2):
                    try:
                        pin_rows = await _plymouth_book_search(
                            page, target_book, target_page)
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise
                        result["notes"].append(
                            f"Book Search attempt 1 failed ({type(e).__name__}) "
                            "— retrying in a fresh browser context.")
                        await page.close()
                        context = await browser.new_context(accept_downloads=True)
                        page = await context.new_page()
                if not pin_rows:
                    result["status"] = "deed_not_found"
                    result["notes"].append(
                        f"--book {target_book} --page {target_page}: Book Search "
                        "found NO Recorded Land instrument at that Book/Page. "
                        "Check the citation (and whether the parcel is "
                        "Registered Land, which has no Book/Page).")
                    await browser.close()
                    return result
                result["pinned_by_book_page"] = True
                result["notes"].append(
                    f"PINNED (v3.50): --book {target_book} --page {target_page} "
                    f"opened by Book Search — {len(pin_rows)} party row(s): "
                    + " | ".join(f"{r.get('party') or '?'} {r['name']} "
                                 f"{r['deed_type']} Doc#{r['doc_number']}"
                                 for r in pin_rows)
                    + ". The grantee name search and its wrong-parcel "
                    "retries were NOT run; the seller-name, conveyance-type "
                    "and address checks below still apply.")
            elif force_address_search:
                if not street_number or not street_name:
                    result["status"] = "error"
                    result["errors"].append(
                        "--force-address-search requires --street-number and --street "
                        "(or a --base-name starting with 'NUM STREET')."
                    )
                    await browser.close()
                    return result
                result["notes"].append(
                    f"Force address search: skipping name search, "
                    f"searching directly for {street_number} {street_name} (town={town!r})."
                )
                await _plymouth_address_search(page, street_number, street_name, result=result)
                if not await _has_results(page):
                    result["status"] = "deed_not_found"
                    result["notes"].append("Force address search: no results.")
                    await browser.close()
                    return result
                found_via_address = True
                result["found_via_address_search"] = True
            else:
                await _plymouth_search(page, combined_name, "I")

            if not pinned and not force_address_search and not await _has_results(page):
                body = await page.inner_text("body")
                result["notes"].append(
                    f"No results for '{combined_name}' as Grantee. "
                    f"Page text snippet: {body[:200]}"
                )

                # v3.5 — HYPHENATED / COMPOUND-SURNAME RETRY (before address fallback)
                # Plymouth's combined "LAST FIRST" field prefix-matches the index,
                # so a partial surname on a hyphenated name fails ("WHITFIELD ALAN" does
                # not prefix-match "WHITFIELD-BARROW ALAN D"). Retry with the surname
                # ONLY — "WHITFIELD" prefix-matches "WHITFIELD-BARROW ..." — then filter
                # the returned rows by first name so an unrelated same-prefix surname
                # is not selected.
                compound_found = await _plymouth_compound_surname_retry(
                    page, seller_last, result
                )
                if compound_found:
                    result["found_via_compound_surname"] = True
                    first_name_filter = first_token
                    result["notes"].append(
                        f"Compound-surname retry active — filtering results by first "
                        f"name token '{first_token}'."
                    )

                # Property may be trust-vested or LLC-vested: the grantee on the
                # deed is an entity, not the individual seller. Fall back to a
                # property address search which returns all instruments at that address.
                if compound_found:
                    pass  # results already loaded by the surname-only retry
                elif street_number and street_name:
                    result["notes"].append(
                        f"Trying address search fallback: "
                        f"street_number={street_number!r} street_name={street_name!r}."
                    )
                    await _plymouth_address_search(page, street_number, street_name, result=result)
                    if not await _has_results(page):
                        result["status"] = "deed_not_found"
                        result["notes"].append(
                            "Address search fallback also returned no results."
                        )
                        await browser.close()
                        return result
                    found_via_address = True
                    result["found_via_address_search"] = True
                    result["notes"].append(
                        "Address search found results — property may be trust-vested or "
                        "LLC-vested. Verify grantee entity and confirm signing authority."
                    )
                else:
                    result["status"] = "deed_not_found"
                    result["notes"].append(
                        "Address search fallback unavailable (no street number/name). "
                        "Pass --street-number and --street, or ensure --base-name starts "
                        "with 'NUM STREET' so street info can be auto-parsed."
                    )
                    await browser.close()
                    return result

            # -----------------------------------------------------------
            # STEP 2 — SORT BY DATE DESC, THEN EXTRACT METADATA
            # Sorting descending puts the most recently recorded deed first.
            # -----------------------------------------------------------
            # v3.13 — replay the search that is currently on screen.  Needed by
            # _plymouth_relocate_row(): the pager walk parks the grid on the LAST
            # page, so a row selected from an earlier page must have its page
            # brought back before its Book link can be clicked.
            async def _replay_search():
                if pinned:
                    await _plymouth_book_search(page, target_book, target_page)
                    return
                if found_via_address:
                    await _plymouth_address_search(page, street_number, street_name)
                elif result["found_via_compound_surname"]:
                    await _plymouth_search(page, seller_last.upper().strip(), "I")
                else:
                    await _plymouth_search(page, combined_name, "I")
                await _has_results(page, timeout_ms=20000)

            # v3.13 — page size FIRST, then sort.  The 100/Page postback re-renders
            # the grid from the default index order, which DISCARDS the Rec Date
            # sort — so sorting first and paging second silently returns rows in
            # ascending/default order (observed live: a date-sorted GRANT PETER
            # search came back starting at 1757 once the page-size switch landed).
            # Selection does not depend on this (the name path re-sorts in Python
            # and the address path picks by max book/doc), but the on-screen order
            # must still match what the notes claim, and prefer_first= relies on it.
            _tm.mark("STEP 2 - page size, sort, pager walk, select row")
            await _avenu_set_page_size_100(page)
            sorted_desc = await _sort_results_by_date_desc(page)
            result["notes"].append(
                f"Date sort descending: {'applied' if sorted_desc else 'not applied (header not found — using book-number fallback)'}."
            )
            # v3.13 — read EVERY pager page, not just the first.  The grid defaults
            # to 20 rows/page; the walk switches it to 100 and follows the Next
            # button to the last page.  Previously only page 1 was read, so an older
            # vesting deed on a busy seller was invisible (live 2026-07-13: the
            # GRANT PETER grantee search reports 122 rows; the script saw 20).
            all_rows = await _read_all_result_rows_paginated(
                page, notes=result["notes"], flags=result
            )
            search_label = ("Book Search (pinned)" if pinned
                            else "Address search" if found_via_address
                            else "Grantee search")
            result["notes"].append(
                f"{search_label} returned {len(all_rows)} row(s). "
                + " | ".join(
                    f"[p{r.get('_pager_page', 1)}/{r['ctl']}] Bk{r['book']} {r['deed_type']} "
                    f"{r['recorded_date']} addr={r['street']!r} town={r['town']!r}"
                    for r in all_rows[:40]
                )
                + (f" | ...(+{len(all_rows) - 40} more)" if len(all_rows) > 40 else "")
            )

            # v3.5 — first-name filter for the compound-surname retry.
            # The surname-only search returns every grantee whose surname begins
            # with the seller's last name (e.g. "WHITFIELD" matches "WHITFIELD-BARROW"
            # but could also match an unrelated "WHITFIELD"). Keep only rows whose
            # grantee Name column contains the seller's first name token.
            if first_name_filter and not found_via_address and all_rows:
                fn = first_name_filter.upper()
                fn_rows = [r for r in all_rows if fn in (r.get("name") or "").upper()]
                if fn_rows:
                    result["notes"].append(
                        f"Compound-surname retry: filtered {len(all_rows)} surname "
                        f"row(s) to {len(fn_rows)} matching first name '{first_name_filter}'."
                    )
                    all_rows = fn_rows
                else:
                    result["notes"].append(
                        f"Compound-surname retry: no rows matched first name "
                        f"'{first_name_filter}' among {len(all_rows)} surname row(s) — "
                        f"proceeding with all rows. VERIFY MANUALLY."
                    )

            # Address search returns all instrument types at the property
            # (mortgages, notices, discharges, etc.). Filter to deed-type rows
            # so _select_best_row() picks the vesting deed, not a mortgage.
            if found_via_address and all_rows:
                deed_rows = [
                    r for r in all_rows
                    if not _is_non_conveyance_instrument(r.get("deed_type", ""))
                ]
                if deed_rows:
                    excluded_types = [r["deed_type"] for r in all_rows if r not in deed_rows]
                    result["notes"].append(
                        f"Address search: filtered to {len(deed_rows)} deed-type row(s). "
                        f"Excluded: {excluded_types}"
                    )
                    all_rows = deed_rows
                else:
                    result["notes"].append(
                        "Address search: no rows survived deed-type filter — using all rows."
                    )

            # Name-search results can include non-conveyance instruments where the
            # seller is indexed as grantee — most commonly DIS (discharge of mortgage,
            # where the borrower/homeowner is the grantee beneficiary).  Filter these
            # out so _select_best_row() picks the actual vesting deed, not whatever
            # was most recently recorded.  Falls back to the unfiltered set if no
            # conveyance-type rows survive (prevents silent exit-2 on unusual indexes).
            if not found_via_address and not pinned and all_rows:
                # v3.4 — use the shared classifier so tax-title redemptions ("CR"),
                # tax takings, municipal lien certificates, easements, etc. are never
                # treated as a vesting deed (the 2026-06-23 run reported a redemption).
                deed_rows = [
                    r for r in all_rows
                    if not _is_non_conveyance_instrument(r.get("deed_type", ""))
                ]
                if deed_rows:
                    excluded = [r["deed_type"] for r in all_rows if r not in deed_rows]
                    result["notes"].append(
                        f"Name search: filtered {len(excluded)} non-deed row(s) "
                        f"before selection: {excluded}."
                    )
                    all_rows = deed_rows
                else:
                    result["notes"].append(
                        "Name search: no rows survived deed-type filter — using all rows as-is."
                    )

            # Python date sort (v2.7) — overrides browser-side sort for name-search path.
            # Browser sort validation using book numbers is unreliable when Plymouth
            # County's digitized old records have non-monotonic book numbers (e.g.
            # a 1978 deed at Bk32450 while a 2002 deed is at Bk22572).  Sorting in
            # Python by parsed date is always correct regardless of book numbering.
            if not found_via_address and all_rows:
                all_rows.sort(
                    key=lambda r: _parse_deed_date(r.get("recorded_date", "")),
                    reverse=True,
                )
                sorted_desc = True  # Python sort guarantees descending order

            if pinned:
                # v3.50 — every row is the pinned instrument (one per indexed
                # party); only rows at this Bk/Pg survived the Book Search.
                # If more than one DOCUMENT shares the Bk/Pg, prefer a
                # conveyance and say so. The grantee (EE) row is preferred
                # because its Name cell is the grantee.
                docs = {r.get("doc_number") for r in all_rows}
                if len(docs) > 1:
                    result["notes"].append(
                        f"WARNING: {len(docs)} different documents are indexed at "
                        f"Bk {target_book}/Pg {target_page} (Doc# "
                        f"{', '.join(sorted(d or '?' for d in docs))}) — a "
                        "conveyance is preferred; confirm on the page images.")
                conv = [r for r in all_rows
                        if not _is_non_conveyance_instrument(r.get("deed_type", ""))]
                pool = conv or all_rows
                ee = [r for r in pool if (r.get("party") or "").upper() == "EE"]
                row = (ee or pool)[0] if pool else None
            elif found_via_address:
                # v3.51 — the address search is county-wide; scope to the
                # subject town before picking (item 50).
                all_rows = _plymouth_scope_rows_to_town(
                    all_rows, town, result["notes"], "Address search")
                # Address search: pick by (book, doc_number) descending so we get
                # the most recently recorded deed. Using doc_number as a tiebreaker
                # handles the case where multiple documents share the same book
                # (e.g. a Trustee's Certificate and the vesting deed recorded on the
                # same day — the deed has the higher doc number).
                try:
                    row = max(
                        all_rows,
                        key=lambda r: (int(r.get("book") or 0), int(r.get("doc_number") or 0))
                    )
                except (ValueError, TypeError):
                    row = all_rows[0] if all_rows else None
            else:
                row = _select_best_row(
                    all_rows, town, prefer_first=sorted_desc, street_filter=street_name,
                )
            if row is None:
                result["status"] = "deed_not_found"
                result["notes"].append("No result rows found after reading grid.")
                await browser.close()
                return result

            # -----------------------------------------------------------
            # WRONG-PARCEL DETECTION → ADDRESS-SEARCH RETRY
            # -----------------------------------------------------------
            # Two independent signals that the name search selected a deed for
            # the wrong property.  Both funnel into the same address-search
            # retry, which is more discriminating because it filters by street.
            #
            #   town mismatch   (v2.7) — seller owns property in another town.
            #   street mismatch (v3.12) — seller owns MULTIPLE PROPERTIES IN THE
            #       SAME TOWN, so the town filter matched every candidate and the
            #       most-recently-recorded one won regardless of street.
            #       (Peter Grant, Hingham, 2026-07-13: name search returned a DEED
            #       for 23 Harrowgate Dr; subject property was 18 Kestrel Ave.  Both rows
            #       carried town HNGHM, so the v2.7 town check never fired.)
            town_mismatch = False
            street_mismatch = False

            if not found_via_address and not pinned:
                if town and (row.get("town") or "").upper() not in ("", "NONE"):
                    town_mismatch = not _town_matches_filter(
                        town.upper(), (row.get("town") or "").upper()
                    )
                # Only meaningful when the town is right — a town mismatch is the
                # stronger signal and is reported on its own terms below.
                if street_name and not town_mismatch and (row.get("street") or "").strip():
                    street_mismatch = not _street_matches_filter(
                        street_name, row.get("street", "")
                    )

            if town_mismatch:
                if len(all_rows) == 1:
                    # Single result — no ambiguity to resolve.  The town filter
                    # failed only because this abbreviation isn't in the dict yet.
                    # Accept the row as-is and prompt to update the dict.
                    result["notes"].append(
                        f"NOTE: town abbreviation '{(row.get('town') or '').upper()}' not yet in "
                        f"_PLYMOUTH_TOWN_ABBREVS for '{town}'. "
                        f"Add entry \"{town}\": \"{(row.get('town') or '').upper()}\" to the dict. "
                        f"Single result — proceeding without retry."
                    )
                else:
                    # Multiple results and none matched the expected town —
                    # genuine multi-property ambiguity; retry with address search.
                    result["notes"].append(
                        f"WARNING: no name-search result matched town '{town}'. "
                        f"Best available row is Bk{row['book']} town={row['town']!r} "
                        f"(possible wrong property — seller may own multiple Plymouth Co. properties)."
                    )
                    # v3.51 (item 50) — the single-row NOTE above was the ONLY
                    # place a dictionary gap was reported, i.e. only where it
                    # is harmless. Here it decides the parcel: say so.
                    _gap = _plymouth_unknown_town_codes(all_rows)
                    if _gap:
                        result["notes"].append(
                            f"WARNING: town filter matched 0 of {len(all_rows)} "
                            f"name-search row(s), and town code(s) {_gap} are "
                            f"unknown to the script — probably a DICTIONARY GAP, "
                            f"not a different town. If one of them is '{town}', "
                            f"add it to _PLYMOUTH_TOWN_ABBREVS. The address-search "
                            f"retry below is scoped to '{town}' and to the "
                            f"seller's own rows so it cannot cross town lines."
                        )
            elif street_mismatch:
                result["notes"].append(
                    f"WARNING: name-search selected row street {row.get('street')!r} does not "
                    f"match expected street '{street_name}' (town {row.get('town')!r} DID match) — "
                    f"seller likely owns multiple properties in {town or 'this town'}."
                )

            # Retry on either signal.  A town mismatch on a single-row result is
            # an unknown-abbreviation artifact, not real ambiguity, so it is
            # excluded (v2.9) — but a street mismatch is meaningful even with one
            # row, since the deed plainly names a different street.
            retry_reason = ""
            if town_mismatch and len(all_rows) > 1:
                retry_reason = "town mismatch"
            elif street_mismatch:
                retry_reason = "street mismatch"

            if retry_reason and not found_via_address and street_number and street_name:
                result["notes"].append(
                    f"{retry_reason.capitalize()}: retrying with address search "
                    f"({street_number} {street_name}, town={town!r})."
                )
                await _plymouth_address_search(page, street_number, street_name, result=result)
                if await _has_results(page, timeout_ms=15000):
                    found_via_address = True
                    result["found_via_address_search"] = True
                    result["notes"].append(
                        f"Address search ({retry_reason} retry) returned results."
                    )
                    # v3.13 — page size before sort, then walk every pager page
                    # (a busy street can exceed one page just like a busy seller).
                    await _avenu_set_page_size_100(page)
                    await _sort_results_by_date_desc(page)
                    addr_rows = await _read_all_result_rows_paginated(
                        page, notes=result["notes"], flags=result
                    )
                    result["notes"].append(
                        f"Address search ({retry_reason} retry) returned {len(addr_rows)} row(s). "
                        + " | ".join(
                            f"[p{r.get('_pager_page', 1)}/{r['ctl']}] Bk{r['book']} {r['deed_type']} "
                            f"{r['recorded_date']} addr={r['street']!r} town={r['town']!r}"
                            for r in addr_rows[:40]
                        )
                        + (f" | ...(+{len(addr_rows) - 40} more)" if len(addr_rows) > 40 else "")
                    )
                    addr_deed_rows = [
                        r for r in addr_rows
                        if not _is_non_conveyance_instrument(r.get("deed_type", ""))
                    ]
                    if addr_deed_rows:
                        result["notes"].append(
                            f"Address search ({retry_reason} retry): filtered to "
                            f"{len(addr_deed_rows)} deed-type row(s)."
                        )
                        addr_rows = addr_deed_rows
                    addr_rows = _plymouth_scope_rows_to_town(
                        addr_rows, town, result["notes"],
                        f"Address search ({retry_reason} retry)",
                        seller_rows=all_rows,
                    )
                    try:
                        row = max(
                            addr_rows,
                            key=lambda r: (
                                int(r.get("book") or 0),
                                int(r.get("doc_number") or 0),
                            ),
                        )
                    except (ValueError, TypeError):
                        row = addr_rows[0] if addr_rows else row
                    result["notes"].append(
                        f"Address search ({retry_reason} retry): selected "
                        f"Bk{row['book']} {row['deed_type']} {row['recorded_date']} "
                        f"town={row['town']!r} addr={row.get('street')!r}."
                    )
                else:
                    result["notes"].append(
                        f"Address search ({retry_reason} retry): no results — "
                        "proceeding with name-search selection. VERIFY MANUALLY."
                    )
            elif street_mismatch:
                # Street mismatch detected but no address search possible (street
                # info unparseable).  Never fail silently on a known wrong parcel.
                result["notes"].append(
                    "WARNING: street mismatch detected but address-search retry "
                    "unavailable (no street number/name parsed). VERIFY MANUALLY — "
                    "the selected deed may be for a different property."
                )

            # -----------------------------------------------------------
            # v3.3 — MISINDEXED-NAME / NO-DEED FALLBACK
            # -----------------------------------------------------------
            # If the row selected from the grantee name search is NOT a
            # conveyance deed (e.g. the only HENNIGAN hit was a Certificate of
            # Redemption because the real deed was misindexed as "HANNIGAN"),
            # retry with an address search.  Address search is index-name-
            # independent, so it recovers the vesting deed — or, if the seller
            # has since sold, the out-conveyance, which flags that the seller is
            # no longer the record owner.  Reference: 60 Aldergate St, Middleborough
            # (run 2026-06-23-001 reported the redemption; 2026-06-24-001 fixed it).
            if (
                not found_via_address
                and not pinned
                and row is not None
                and _is_non_conveyance_instrument(row.get("deed_type", ""))
            ):
                if street_number and street_name:
                    result["notes"].append(
                        f"Name-search selection {row.get('deed_type')!r} is not a "
                        f"conveyance deed (grantee may be misindexed under a "
                        f"misspelled name) — retrying with address search."
                    )
                    fb_row = await _plymouth_address_fallback(
                        page, street_number, street_name, result,
                        town=town, seller_rows=all_rows,
                    )
                    if fb_row is not None:
                        found_via_address = True
                        result["found_via_address_search"] = True
                        row = fb_row
                    else:
                        result["notes"].append(
                            "Address-search fallback found no deed — proceeding with "
                            "name-search selection. VERIFY MANUALLY: vesting deed may be "
                            "misindexed; check the registry by book/page or address."
                        )
                else:
                    result["notes"].append(
                        f"WARNING: name-search selection {row.get('deed_type')!r} is not "
                        f"a conveyance deed and no street info is available for an "
                        f"address-search fallback. The vesting deed may be misindexed "
                        f"under a misspelled grantee name — VERIFY MANUALLY by book/page."
                    )

            # -----------------------------------------------------------
            # v3.12 — FINAL-SELECTION CONVEYANCE GUARD (path-independent)
            # -----------------------------------------------------------
            # The v3.3 fallback above only guards the NAME-search path
            # (`not found_via_address`).  Any row reached via an address search —
            # including the v3.12 street-mismatch retry — skipped that guard, so a
            # non-conveyance instrument could be reported as the vesting deed with
            # status "success" and no warning.  The address-search row filter falls
            # back to "using all rows" when no DEED-type row is present at the
            # address, which is exactly when this bites.
            #
            # Surfaced live 2026-07-13 (18 Kestrel Ave, Hingham): the street-mismatch
            # retry correctly moved to the right parcel, but the address results held
            # only MTG/DISCHARGE/ASSIGNMENT rows — no DEED — so an ASSIGNMENT was
            # selected.  A vesting deed that is absent from BOTH the grantee name
            # index and the address index usually means the parcel is Registered Land
            # (Land Court) or the deed is misindexed; either way it must never be
            # reported as the deed.
            if row is not None and _is_non_conveyance_instrument(row.get("deed_type", "")):
                result["selected_row_is_not_a_deed"] = True
                # v3.36 (item 0a): an UNRECOGNISED type now trips this guard
                # too — previously the bool's fall-through called it a
                # conveyance, so an unknown type could be reported as the
                # vesting deed and pass this check silently. Word the two
                # cases differently: "not a deed" and "we could not tell"
                # call for different follow-up.
                if _classify_instrument(row.get("deed_type", "")) == "unknown":
                    result["notes"].append(
                        f"CRITICAL: the selected instrument has an UNRECOGNISED type "
                        f"{row.get('deed_type')!r} — the script cannot confirm it is a "
                        f"conveyance deed. DO NOT report it as the vesting deed or "
                        f"extract a legal description from it until you have read it. "
                        f"If it IS a conveyance, add the type to the script vocabulary; "
                        f"if not, check Plymouth Registered Land (Land Court) and check "
                        f"for a misindexed grantee name."
                    )
                else:
                    result["notes"].append(
                        f"CRITICAL: the selected instrument is a {row.get('deed_type')!r}, NOT a "
                        f"conveyance deed. No DEED-type row for this property was found in the "
                        f"grantee name index or the property address index. DO NOT report this as "
                        f"the vesting deed or extract a legal description from it. Check Plymouth "
                        f"Registered Land (Land Court), and check for a misindexed grantee name."
                    )
            else:
                result["selected_row_is_not_a_deed"] = False

            # -----------------------------------------------------------
            # v3.51 (item 50) — FINAL-SELECTION TOWN GUARD (path-independent)
            # -----------------------------------------------------------
            # Same idea as the conveyance guard above: whatever path chose the
            # row, a row indexed to a DIFFERENT known town is flagged. An
            # unknown code is a dictionary gap and gets a NOTE, not the flag.
            _sel_town = (row.get("town") or "").strip().upper() if row else ""
            if (town and row is not None
                    and _sel_town not in _PLYMOUTH_TOWNLESS_CODES
                    and not _town_matches_filter(town.upper(), _sel_town)):
                if _plymouth_town_code_is_known(_sel_town):
                    result["selected_row_town_mismatch"] = True
                    if not pinned:  # the pin has its own WARNING (pinned)
                        result["notes"].append(
                            f"CRITICAL: the selected instrument Bk{row.get('book')}/"
                            f"{row.get('page')} is indexed to town {_sel_town!r}, "
                            f"NOT '{town}' (address {row.get('street')!r}). It is "
                            f"probably ANOTHER PARCEL. DO NOT report it as the "
                            f"vesting deed until the deed itself shows the subject "
                            f"town; if the seller's deed is absent, check Plymouth "
                            f"Registered Land and a misindexed grantee name.")
                else:
                    result["notes"].append(
                        f"NOTE: town code {_sel_town!r} on the selected row is not "
                        f"known to the script, so the selection's town could not be "
                        f"checked against '{town}'. If {_sel_town!r} is '{town}', add "
                        f"it to _PLYMOUTH_TOWN_ABBREVS; otherwise treat the parcel "
                        f"as UNVERIFIED and confirm the town on the deed.")

            result["book"]           = row["book"]
            result["page"]           = row["page"]
            result["document_number"] = row["doc_number"]
            result["deed_type"]      = row["deed_type"]
            result["recorded_date"]  = row["recorded_date"]
            result["deed_property_address"] = (
                f"{row['street']}, {row['town']}" if row["street"] else row["town"]
            )
            # v3.50 — a Book Search lists the instrument under EITHER party:
            # on a grantor (OR) row the Name cell is the GRANTOR and Reverse
            # Party the grantee — the reverse of a grantee name search.
            _row_is_or = (row.get("party") or "").upper() == "OR"
            _row_grantor = row["name"] if _row_is_or else row["reverse_party"]
            _row_grantee = row["reverse_party"] if _row_is_or else row["name"]
            result["notes"].append(
                f"Selected row: {row['deed_type']} Doc#{row['doc_number']} "
                f"Bk{row['book']}/Pg{row['page']} {row['recorded_date']} | "
                f"Grantor: {_row_grantor} | Grantee: {_row_grantee} | "
                f"Address: {row['street']}, {row['town']}"
            )
            if pinned:
                # v3.50 — the pin skipped the town/street retries, so the
                # index address is CHECKED here instead (a note, never a
                # retarget: the operator named this instrument).
                idx_street = (row.get("street") or "").strip()
                idx_town = (row.get("town") or "").strip().upper()
                if street_name and idx_street:
                    if not _street_matches_filter(street_name, idx_street):
                        result["notes"].append(
                            f"WARNING (pinned): the index address of Bk "
                            f"{target_book}/Pg {target_page} is {idx_street!r}, "
                            f"which does not name '{street_name}'. Confirm the "
                            "pin is the subject parcel before using it.")
                elif street_name:
                    result["notes"].append(
                        f"NOTE (pinned): Bk {target_book}/Pg {target_page} has "
                        "no street indexed, so the pin could not be checked "
                        "against the subject street from the index — the "
                        "extracted deed address check below is the check.")
                if (town and idx_town and idx_town not in ("NONE", "SEEBK")
                        and not _town_matches_filter(town.upper(), idx_town)):
                    result["notes"].append(
                        f"WARNING (pinned): Bk {target_book}/Pg {target_page} is "
                        f"indexed to town {idx_town!r}, not {town!r}.")

            # -----------------------------------------------------------
            # v3.13 — BRING THE SELECTED ROW BACK ON SCREEN BEFORE CLICKING IT
            # -----------------------------------------------------------
            # ctl numbers are unique only within a pager page, and the pager walk
            # leaves the grid parked on the LAST page.  Clicking the selected row's
            # recorded ctl now would address a DIFFERENT row and open the wrong
            # deed's detail panel and images.  Re-derive the live ctl (replaying the
            # search and paging forward if the row is not currently displayed).
            live_ctl = await _plymouth_ensure_row_visible(page, row, _replay_search)
            if live_ctl:
                if live_ctl != row["ctl"]:
                    result["notes"].append(
                        f"Re-located selected row for clicking: pager page "
                        f"{row.get('_pager_page', 1)}, ctl {row['ctl']} -> {live_ctl}."
                    )
                row["ctl"] = live_ctl
            else:
                result["notes"].append(
                    f"WARNING: could not bring the selected row (Bk{row['book']} "
                    f"Doc#{row['doc_number']}) back on screen after the pager walk — "
                    f"detail panel and images may be unavailable."
                )

            # -----------------------------------------------------------
            # STEP 3 — DETAIL PANEL (full parties + consideration)
            # -----------------------------------------------------------
            _tm.mark("STEP 3 - detail panel")
            panel_opened = await _open_detail_panel(page, ctl=row["ctl"], expected_book=row["book"])
            if panel_opened:
                detail = await _read_detail_panel(page)
                result["grantors"]     = detail["grantors"]
                result["grantees"]     = detail["grantees"]
                result["consideration"] = detail["consideration"]
                result["notes"].append(
                    f"Grantors: {detail['grantors']} | Grantees: {detail['grantees']} | "
                    f"Consideration: {detail['consideration']}"
                )
                # v3.24 — surface the panel's cross-reference list (later
                # homesteads / discharges / related deeds against this deed);
                # same treatment as Middlesex South's detail-panel References.
                result["detail_references"] = detail.get("references") or []
                # v3.50 — the panel's own count, and whether every pager page
                # of the References grid was read.
                result["detail_references_expected"] = detail.get("references_expected")
                result["detail_references_complete"] = detail.get("references_complete")
                if detail.get("references_note"):
                    result["notes"].append(detail["references_note"])
                if result["detail_references"]:
                    result["notes"].append(
                        "Detail panel references (cross-refs against this "
                        "deed — homesteads/discharges/related instruments): "
                        + " | ".join(result["detail_references"])
                    )
                    # v3.26 — normalised into the shared cross_references
                    # shape so every registry reads the same downstream.
                    result["cross_references"] = _normalize_cross_references(
                        result["detail_references"], "Plymouth detail panel")
                    xnote = _cross_reference_note(result["cross_references"])
                    if xnote:
                        result["notes"].append(xnote)
            else:
                # Fall back to single grantor from results row
                result["grantors"] = [_row_grantor] if _row_grantor else []
                result["grantees"] = [_row_grantee] if _row_grantee else []
                result["notes"].append("Detail panel did not open — using results-row party data only.")

            if pinned:
                # v3.50 — a pin bypasses the grantee NAME search, so nothing
                # yet says the seller took title by this instrument. Check it.
                ee_names = list(result["grantees"]) or [
                    (r["reverse_party"] if (r.get("party") or "").upper() == "OR"
                     else r["name"])
                    for r in all_rows if r.get("name")]
                surname = re.sub(r"[^A-Z]", "", seller_last.upper())
                if surname and not any(
                        surname in re.sub(r"[^A-Z]", "", n.upper())
                        for n in ee_names):
                    result["notes"].append(
                        f"WARNING (pinned): the seller '{seller_last}' is NOT "
                        f"named as a grantee of Bk {target_book}/Pg "
                        f"{target_page} (grantees: {ee_names or 'none read'}). "
                        "Either the pin is the wrong instrument, or title is "
                        "held under another name (a trust, an entity, a "
                        "former name). Resolve before relying on this deed.")
                else:
                    result["notes"].append(
                        f"Pinned instrument names the seller '{seller_last}' "
                        f"as grantee ({', '.join(ee_names)}).")

            # -----------------------------------------------------------
            # STEP 4 — VIEW IMAGES → download deed pages
            # -----------------------------------------------------------
            _tm.mark("STEP 4 - page images")
            # Click "View Images" tab to set up server session (no popup fires)
            try:
                view_images_link = await page.query_selector('a[href*="TabController1$ImageViewertabitem"]')
                if view_images_link:
                    await view_images_link.click()
                    await page.wait_for_timeout(1500)  # let server register the session
                else:
                    result["notes"].append("View Images tab not found — navigating directly to viewer.")
            except Exception as e:
                result["notes"].append(f"View Images tab click error (non-fatal): {e}")

            # Navigate to viewer (session holds document context)
            await page.goto(PLYMOUTH_VIEWER, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector("#ImageViewer1_docImage", timeout=20000)
                await page.wait_for_timeout(1500)  # let image fully render
            except Exception:
                result["errors"].append("Image viewer did not load #ImageViewer1_docImage.")
                await browser.close()
                return result

            total_pages = await _parse_page_count(page)
            result["total_pages_in_viewer"] = total_pages

            # All pages — loop from 1 through total_pages
            for page_num in range(1, total_pages + 1):
                if page_num > 1:
                    try:
                        await page.click("#ImageViewer1_BtnNext")
                        await page.wait_for_timeout(2000)
                    except Exception as e:
                        result["notes"].append(f"Page {page_num} navigation error (stopping): {e}")
                        break
                p_path = output_folder / f"{base_name} - deed_p{page_num}.jpg"
                method = await _download_viewer_image(page, p_path)
                if method != "failed":
                    result["files"].append(str(p_path))
                    result["notes"].append(f"Page {page_num} saved ({method}): {p_path.name}")
                else:
                    result["errors"].append(f"Page {page_num} download failed.")

            # v3.47 (47a) — say it when a page is NOT the hi-res render. The
            # saved images are the audit copy; a thumbnail that passes
            # silently is the same missing-information-read-as-a-pass shape
            # as every other silent degrade in this file.
            _default_res = [
                n for n in result["notes"]
                if n.startswith("Page ")
                and ("(src_download)" in n or "(screenshot)" in n)
            ]
            if _default_res:
                result["notes"].append(
                    f"WARNING: {len(_default_res)} page image(s) were saved at "
                    "the viewer's DEFAULT (thumbnail, ~527x682 px) resolution, "
                    "not the 2000 px render — the hi-res rewrite did not apply. "
                    "Small type may not be legible enough to audit the "
                    "transcription; open the instrument in the registry viewer "
                    "to verify."
                )

        except Exception as e:
            result["errors"].append(f"Main workflow failed: {e}")
            await browser.close()
            return result
        finally:
            try:
                await page.close()
            except Exception:
                pass

        # -----------------------------------------------------------
        # STEP 5 — GRANTOR CHECK (all grantees)
        # Checks every grantee on the deed as a potential Grantor, not just
        # the named seller.  Catches subsequent deeds by joint tenant co-owners.
        # -----------------------------------------------------------
        # v3.54 (item 57) — the page images are final here and the grantor
        # check below reads only index data, so hand the images to the caller
        # now: main() starts the extraction API call on a worker thread and
        # joins it after this runner returns.
        if on_images_ready is not None and result["files"]:
            try:
                on_images_ready(result)
            except Exception as e:
                result["notes"].append(
                    f"Early extraction not started (non-fatal): {e}")

        _tm.mark("STEP 5 - grantor check")
        all_grantor_rows: list[dict] = []   # v3.50 — read by --verify-grantor-hit
        try:
            g_page = await context.new_page()
            original_book = result.get("book", "")
            original_doc = result.get("document_number", "") or ""

            # Build set of names to check: named seller + all grantees from detail panel.
            # named seller: already in Plymouth format (LAST FIRST) from --last/--first args.
            # detail panel grantees: already in Plymouth format (LAST FIRST MI) — use
            #   _clean_registry_name (strip suffixes only, do NOT reorder).
            names_to_check: dict[str, str] = {}  # search_name → display label

            def _add_search_name(raw: str, label: str) -> None:
                # v3.30 (item 11) — broaden past a trailing middle initial
                # before de-duplicating, because Plymouth prefix-matches.
                broad = _plymouth_broaden_prefix_name(raw)
                if broad != raw:
                    label = (f"{label} [searched as '{broad}' — Plymouth "
                             f"prefix match; '{raw}' would miss an entry "
                             f"indexed without the initial]")
                names_to_check.setdefault(broad, label)

            _add_search_name(combined_name, f"named seller ({combined_name})")
            for grantee_display in result.get("grantees", []):
                cleaned = _clean_registry_name(grantee_display)
                if cleaned and cleaned != combined_name:
                    _add_search_name(cleaned, grantee_display)

            seen_docs: set[tuple] = set()

            # v3.29 — server-side date window (see _GRANTOR_WINDOW_LOOKBACK_DAYS).
            # GRANT PETER / 23 Harrowgate Dr: 218 rows back to 1704 → 41, with the
            # earliest returned row being the deed's own recording date, so the
            # acquisition batch survives. An unknown acquisition date leaves the
            # window off entirely rather than guessing one.
            g_window = _grantor_window_start(
                _parse_deed_date(result.get("recorded_date") or ""))
            result.setdefault("grantor_check", {})["search_window"] = {
                "from": (f"{g_window[1]}/{g_window[2]}/{g_window[0]}"
                         if g_window > (0, 0, 0) else None),
                "lookback_days": (_GRANTOR_WINDOW_LOOKBACK_DAYS
                                  if g_window > (0, 0, 0) else None),
                "basis": ("acquisition date less lookback" if g_window > (0, 0, 0)
                          else "no window — acquisition date unknown, all years searched"),
                "lien_sweep": "document-type restricted, ALL YEARS",
            }

            # (search_name, label, date_from, doc_types) — the main windowed
            # pass per name, then the all-years lien sweep per name. The sweep
            # recovers exactly what the window hides: liens against the person
            # that can reach after-acquired property. Skipped when no window
            # was applied, because the main pass then already covers all years.
            passes = [(n, l, g_window, None) for n, l in names_to_check.items()]
            # v3.38 — the lien sweep is OPT-IN (--lien-sweep). It answers a
            # different question from this workflow's, and when it does not
            # run the notes SAY so: a sweep that silently did not run must
            # never read as a sweep that found nothing.
            if g_window > (0, 0, 0) and lien_sweep:
                passes += [(n, f"{l} [lien sweep, all years]", None,
                            _PLYMOUTH_LIEN_DOC_TYPES)
                           for n, l in names_to_check.items()]
            elif g_window > (0, 0, 0):
                result["grantor_check"]["lien_sweep"] = (
                    "not run (--lien-sweep not passed)")
                result["notes"].append(
                    "Grantor check: the all-years LIEN SWEEP did NOT run (it "
                    "is opt-in since v3.38 — pass --lien-sweep). This run "
                    "therefore says nothing about tax liens, executions, "
                    "attachments or bankruptcies against the owners "
                    "personally; those can reach after-acquired property and "
                    "belong to /title-rundown. The deed-out and current-owner "
                    "questions are unaffected."
                )

            # v3.30 (item 11) — per-search accounting. Hits are de-duplicated
            # by (book, doc#) and labelled with the FIRST search that found
            # them, so on a co-owned parcel where both owners signed every
            # instrument, every line reads "via: <named seller>" and the
            # co-owner pass is INDISTINGUISHABLE FROM NEVER HAVING RUN — the
            # Grant / 23 Harrowgate Dr run had to be re-verified by hand
            # before the report could say the co-owner had not conveyed. This
            # log makes "searched, all rows duplicate" visibly different from
            # "searched, zero rows" and from "never searched". Same
            # missing-information-read-as-a-negative-answer family as v3.20.
            search_log: list[dict] = []

            for search_name, label, win, doc_types in passes:
                try:
                    rows = await _grantor_check_search(
                        g_page, search_name, original_book, original_doc,
                        date_from=win, doc_type_values=doc_types)
                except Exception as e:
                    # Never let one pass silently vanish — a sweep that did not
                    # run must not read as a sweep that found nothing.
                    result["notes"].append(
                        f"WARNING: grantor search [{label}] FAILED "
                        f"(non-fatal): {e}. That question is OPEN, not clean."
                    )
                    search_log.append({
                        "name": search_name, "label": label,
                        "rows_returned": None, "rows_new": 0,
                        "status": f"ERROR — {type(e).__name__}: {e}",
                    })
                    continue
                rows_new = 0
                for row in rows:
                    key = (row["book"], row["doc_number"])
                    if key not in seen_docs:
                        seen_docs.add(key)
                        # v3.29 — carry the sweep marker into the row so the
                        # "[found via: …]" tag on every line in
                        # grantor_check.deeds distinguishes an all-years lien
                        # sweep hit from a windowed one. Without this the row
                        # only knows the search NAME and the two passes are
                        # indistinguishable in the output.
                        if doc_types:
                            row["searched_name"] = (
                                f"{row.get('searched_name', search_name)} (lien sweep)")
                        all_grantor_rows.append(row)
                        rows_new += 1
                        result["notes"].append(
                            f"Grantor check hit [{label}]: "
                            f"Bk{row['book']} {row['deed_type']} {row['recorded_date']} "
                            f"| Grantee: {row['grantee']} | {row['street']}, {row['town']} "
                            f"| Doc#{row['doc_number']}"
                        )
                    # else: duplicate deed already captured via another grantee's search
                search_log.append({
                    "name": search_name, "label": label,
                    "rows_returned": len(rows), "rows_new": rows_new,
                    "status": "ok",
                })

            _plymouth_record_searches(result, search_log)
            _plymouth_finalize_grantor_check(
                result, all_grantor_rows, street_number, street_name, town)

            await g_page.close()
        except Exception as e:
            result["notes"].append(f"Grantor check failed (non-fatal): {e}")

        # -----------------------------------------------------------
        # v3.50 — --verify-grantor-hit BOOK/PAGE (Plymouth)
        # -----------------------------------------------------------
        if verify_grantor_hit:
            _tm.mark("STEP 5b - verify grantor hit")
            vb, _, vp = verify_grantor_hit.partition("/")
            vb = vb.strip().lstrip("0")
            vp = vp.strip().lstrip("0")
            target_hit = next(
                (r for r in all_grantor_rows
                 if (r.get("book") or "").lstrip("0") == vb
                 and (not vp or (r.get("page") or "").lstrip("0") == vp)),
                None)
            if target_hit is None:
                result["grantor_hit_verification"] = {
                    "status": "not_found", "requested": verify_grantor_hit}
                result["notes"].append(
                    f"--verify-grantor-hit {verify_grantor_hit} did not match "
                    "any grantor-check hit, so it was NOT verified. Hits "
                    "found: " + (", ".join(
                        f"Bk{r['book']}/{r.get('page') or '?'} {r['deed_type']}"
                        for r in all_grantor_rows) or "none")
                    + ". (The hit must come from the check's own searches.)")
            elif not vp:
                result["grantor_hit_verification"] = {
                    "status": "not_performed", "requested": verify_grantor_hit,
                    "reason": "Plymouth needs BOOK/PAGE — Book Search is "
                              "addressed by both"}
                result["notes"].append(
                    f"--verify-grantor-hit {verify_grantor_hit}: pass BOOK/PAGE "
                    f"on Plymouth (e.g. {vb}/"
                    f"{target_hit.get('page') or 'PAGE'}). NOT verified.")
            else:
                label = f"grantor_hit_Bk{vb}_Pg{vp}"
                fetched = await _plymouth_open_and_download_instrument(
                    context, vb, vp, base_name, label, output_folder,
                    result["notes"], result["errors"])
                det = fetched.get("detail") or {}
                result["grantor_hit_verification"] = {
                    "status": ("downloaded" if fetched["ok"]
                               else "download_incomplete" if fetched["files"]
                               else "download_failed"),
                    "requested": verify_grantor_hit,
                    "book": vb, "page": vp,
                    "document_number": target_hit.get("doc_number"),
                    "doc_type": target_hit.get("deed_type"),
                    "recorded_date": target_hit.get("recorded_date"),
                    "index_address": ", ".join(
                        x for x in (target_hit.get("street"), target_hit.get("town")) if x),
                    "grantors": det.get("grantors") or [],
                    "grantees": det.get("grantees") or [],
                    "consideration": det.get("consideration"),
                    "files": fetched["files"],
                    "extraction": None,
                }
                if not fetched["ok"]:
                    result["notes"].append(
                        f"WARNING: --verify-grantor-hit {verify_grantor_hit}: "
                        "the instrument's pages were NOT all downloaded — the "
                        "verification is INCOMPLETE; see errors.")

        await browser.close()

    result["status"] = "success" if result["files"] else "error"
    if not result["files"] and not result["errors"]:
        result["errors"].append("No files downloaded.")
    _tm.finish(result)
    return result


# (Suffolk County is implemented after Middlesex South, below.)

# ---------------------------------------------------------------------------
# Middlesex South District — masslandrecords.com (Avenu/20-20, Incapsula WAF)
# ---------------------------------------------------------------------------
#
# Probed live 2026-07-09. Differences vs Plymouth (titleview.org):
#   * Incapsula bot protection: headless browsers get 403 on the search POST
#     (initial GET succeeds, postbacks blocked). Headful real Chrome
#     (channel="chrome") passes. The run function forces headful.
#   * Name search uses SEPARATE LastName1 / FirstName1 fields (Plymouth
#     concatenates "LAST FIRST" into the last-name field).
#   * Grid columns: Type | Name/ Corporation | Book | Page | Type Desc. |
#     File Date | Street # | Property Descr.  No Town, Doc #, or Reverse
#     Party columns. 'Type Desc.' is spelled out (DEED / MORTGAGE / ...) so
#     _is_non_conveyance_instrument's ALIS substring vocabulary applies.
#   * No 'Sort$Rec Date' header — Python date sort handles selection.
#   * Street # cell holds the full street ("10 ASHGROVE PL"), which stands
#     in for the missing Town column when disambiguating multi-property
#     sellers (expected street parsed from --base-name).
#   * Detail panel header table: Doc. # | File Date | Rec Time | Type Desc. |
#     # of Pgs. | Book/Page | Consideration | Doc. Status — parsed
#     structurally (the generic consideration regex would match the Rec Time
#     value '10:38:19.043' first). Also shows a References list (cross-refs
#     such as discharges) captured into notes.
#   * Image viewer: View Images tab click, then direct navigation to
#     ImageViewerEx.aspx (same trick as Plymouth Option A). Image src is an
#     ACSResource.axd URL whose CNTWIDTH/CNTHEIGHT params control SERVER-SIDE
#     render size — rewriting CNTHEIGHT to 2000 yields a fully legible scan
#     (~5x the default 682px render; verified on a 1969 deed).

MSOUTH_SEARCH = "https://www.masslandrecords.com/MiddlesexSouth/D/Default.aspx"
MSOUTH_VIEWER = "https://www.masslandrecords.com/MiddlesexSouth/D/ImageViewerEx.aspx"

_MSOUTH_COLS = {
    "book": "Book", "page": "Page", "doc_number": "Doc",  # no Doc # column → ''
    "deed_type": "Type Desc", "recorded_date": "File Date",
    "street": "Street", "town": "Town",                   # no Town column → ''
    "reverse_party": "Reverse Party",                     # absent → ''
    "name": "Name",
}

# Tokens that mark a registry name as an entity (search whole string in the
# Business/Last Name field) rather than a person (split LAST / FIRST).
def _alis_same_party_reconveyance(entry: dict) -> bool:
    """
    v3.20 — True when a candidate row's indexed grantor and grantee are the
    same party (surname + first given-name token both match): a re-vesting
    deed — a self-conveyance after marriage, adding a spouse, or a trust
    transfer. Such a deed routinely SUPERSEDES the purchase deed as the
    operative vesting instrument. Keegan/402 Sedgefield St: 'KEEGAN, RICHARD H
    (&AL)' → 'KEEGAN, RICHARD H. (&AL)' — the 2002 re-vesting deed
    (Bk 15978/412) superseded the 1998 purchase deed (Bk 11873/154).
    """
    or_last, or_first = _alis_indexed_name_pair(entry.get("grantor") or "")
    ee_last, ee_first = _alis_indexed_name_pair(entry.get("grantee") or "")
    if not (or_last and ee_last and or_last == ee_last):
        return False
    t_or = re.sub(r"[^A-Z0-9]", "", (or_first.split() or [""])[0])
    t_ee = re.sub(r"[^A-Z0-9]", "", (ee_first.split() or [""])[0])
    return bool(t_or) and t_or == t_ee


# v3.20 — pages fetched per candidate by the deep-sampling fallback: page 1
# plus up to 3 more, enough to reach an attached exhibit/legal page.
_CANDIDATE_SAMPLE_MAX_PAGES = 4


def _alis_extend_candidate_samples(
    session, base_url: str, result: dict, cand_rows: list, idxs: list,
    base_name: str, output_folder: Path,
) -> None:
    """
    v3.20 — deeper sampling for candidates whose page-1 sample produced no
    property address. Keegan/402 Sedgefield St (2026-08-10): the operative 2002
    deed's page 1 read only "SEE ATTACHED FULL LEGAL" — its address lived
    on an attached exhibit page the page-1 sample never downloaded, so its
    sample address came back null and the v3.14 auto-retarget silently
    dropped it, reporting the superseded 1998 deed at exit 0.

    For each candidate index in `idxs`: downloads the instrument's first
    _CANDIDATE_SAMPLE_MAX_PAGES pages (page 1 is re-fetched so the _pN file
    names stay aligned with actual page numbers) and re-runs the light
    extraction over all of them. Mutates the candidate entries in place
    (sample_file, sample_files, sample_extraction). Fails soft per
    candidate — a candidate that still has no address stays UNVERIFIED and
    the caller must warn about it, never drop it quietly.
    """
    client, reason = _anthropic_client()
    if client is None:
        result["notes"].append(
            f"Candidate deep-sampling skipped ({reason}) — candidates whose "
            "page-1 sample had no address could not be address-checked."
        )
        return
    for i in idxs:
        cand = cand_rows[i]
        entry = result["multiple_deed_candidates"][i]
        rid = _alis_row_id(cand)
        try:
            info = _alis_get_pdf_hrefs_http(session, base_url, cand["img_href"])
            hrefs = info["pdf_hrefs"][:_CANDIDATE_SAMPLE_MAX_PAGES]
            if len(hrefs) <= 1:
                result["notes"].append(
                    f"Candidate {rid}: page-1 sample had no property address "
                    "and the instrument has no further pages to sample — it "
                    "remains UNVERIFIED."
                )
                continue
            label = ("candidate_Doc" + (cand["document_number"] or cand["ctl_num"])
                     if cand.get("land_court")
                     else f"candidate_Bk{cand['book']}_Pg{cand['page']}")
            saved, errs = _alis_download_pdfs_http(
                session, base_url, hrefs, base_name, output_folder, label=label,
            )
            result["errors"] += errs
            if not saved:
                continue
            entry["sample_file"] = saved[0]
            entry["sample_files"] = saved
            entry["sample_extraction"] = _extract_pdf_fields_light(
                client, saved, _CANDIDATE_SCHEMA,
                f"These are the first {len(saved)} page(s) of a candidate "
                "deed, possibly including attached exhibit or legal-"
                "description pages. Extract the property address (check the "
                "attached pages if page 1 refers to an attached legal), "
                "lot/unit, and grantees so the subject property can be "
                "identified.",
            )
            addr = (entry["sample_extraction"] or {}).get("property_address")
            result["notes"].append(
                f"Candidate {rid}: page-1 sample had no property address — "
                f"deep-sampled {len(saved)} page(s); address now: "
                + (repr(addr) if addr else "STILL NOT FOUND (candidate "
                   "remains UNVERIFIED)")
                + "."
            )
        except Exception as e:
            result["notes"].append(
                f"Candidate {rid}: deep sampling failed (non-fatal) — it "
                f"remains UNVERIFIED. ({type(e).__name__}: {e})"
            )


_ENTITY_NAME_TOKENS = {
    "TRUST", "TR", "LLC", "CORP", "INC", "REALTY", "COMPANY", "CO",
    "PARTNERSHIP", "LP", "LLP", "ASSOCIATES", "DEVELOPMENT", "BANK",
    "NOMINEE", "CONDOMINIUM", "HOMES", "PROPERTIES", "INVESTMENTS",
}


def _msouth_split_name(display: str) -> tuple:
    """
    Split a registry-format name ('LAST FIRST MI' or an entity name) into
    (last, first) for Middlesex South's two-field search form.
    Entities go entirely into the Business/Last Name field.
    """
    cleaned = _clean_registry_name(display)
    tokens = cleaned.split()
    if not tokens:
        return "", ""
    if any(t in _ENTITY_NAME_TOKENS for t in tokens):
        return cleaned, ""
    return tokens[0], " ".join(tokens[1:])


async def _msouth_launch(p, headless: bool, result: dict):
    """
    Launch a browser that passes masslandrecords.com's Incapsula WAF.
    Headless (any flavor) gets 403 on postbacks; headful real Chrome passes.
    """
    try:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        if headless:
            result["notes"].append(
                "Incapsula WAF on masslandrecords.com blocks headless browsers — "
                "launched headful real Chrome (channel='chrome') instead. A Chrome "
                "window will appear for the duration of the run."
            )
        return browser
    except Exception as e:
        result["notes"].append(
            f"Real-Chrome launch failed ({e}); falling back to bundled Chromium "
            "headful — Incapsula may still return 403s."
        )
        return await p.chromium.launch(headless=False)


async def _msouth_search(page: Page, last: str, first: str, party_type: str) -> None:
    """Navigate to the Middlesex South search form and submit a name search."""
    await page.goto(MSOUTH_SEARCH, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_selector("#SearchFormEx1_ACSTextBox_LastName1", timeout=25000)
    await page.select_option("#SearchFormEx1_ACSRadioButtonList_PartyType1", party_type)
    await page.fill("#SearchFormEx1_ACSTextBox_LastName1", last.upper().strip())
    await page.fill("#SearchFormEx1_ACSTextBox_FirstName1", first.upper().strip())
    await page.click("#SearchFormEx1_btnSearch")


async def _msouth_read_detail(page: Page) -> dict:
    """
    Structurally parse the Middlesex South detail-panel header table.
    Returns {doc_number, num_pages, consideration, references} ('' / [] when
    absent). Party lists come from _read_detail_panel (same gg-link markup as
    Plymouth); its consideration value must NOT be used here — the panel's
    Rec Time value (e.g. '10:38:19.043') matches the generic regex first.
    """
    data = await page.evaluate(
        """() => {
            const panel = document.querySelector('[id*="DocDetails1"]');
            if (!panel) return null;
            let out = null;
            // Tables are returned outermost-first; keep scanning so the
            // INNERMOST match wins — outer wrapper tables report the whole
            // header block as one cell, misaligning every value.
            for (const tbl of panel.querySelectorAll('table')) {
                const rows = tbl.querySelectorAll(':scope > tbody > tr, :scope > tr');
                if (rows.length < 2) continue;
                const hdr = Array.from(rows[0].querySelectorAll(':scope > th, :scope > td'))
                    .map(c => c.innerText.trim());
                if (hdr.length < 4) continue;
                if (!hdr.some(h => h === 'Doc. #' || h.startsWith('Doc. #'))) continue;
                const val = Array.from(rows[1].querySelectorAll(':scope > td'))
                    .map(c => c.innerText.trim());
                out = {};
                hdr.forEach((h, i) => { out[h] = val[i] !== undefined ? val[i] : ''; });
            }
            return {header: out};
        }"""
    )
    # v3.50 — References are no longer read here. This used a 400-character
    # slice of the panel text, which kept page 1 of a grid that pages 10
    # rows at a time (a master deed with 47 references came back with 10).
    # _read_detail_panel reads the whole grid, and the runner takes the list
    # from there — re-reading here after that pager walk would see only the
    # LAST page.
    if not data:
        return {"doc_number": "", "num_pages": "", "consideration": ""}
    hdr = data.get("header") or {}

    def _get(*keys):
        for k in keys:
            for h, v in hdr.items():
                if k in h:
                    return v
        return ""

    return {
        "doc_number":    _get("Doc. #"),
        "num_pages":     _get("# of Pgs"),
        "consideration": _get("Consideration"),
    }


async def _msouth_download_viewer_image(page: Page, output_path: Path) -> str:
    """
    Download the image currently shown in the Middlesex South viewer.
    Rewrites the ACSResource.axd src to a 2000px server-side render
    (masslandrecords' default render is container-sized, ~682px).
    Returns 'hires_src_download' | 'src_download' | 'screenshot' | 'failed'.
    """
    src = await page.evaluate(
        "() => { const i = document.querySelector('#ImageViewer1_docImage');"
        " return i ? i.src : null; }"
    )
    if src and "ACSResource" in src:
        hi = re.sub(r"CNTHEIGHT=\d+", "CNTHEIGHT=2000", src)
        hi = re.sub(r"CNTWIDTH=\d+", "CNTWIDTH=1550", hi)
        try:
            resp = await page.request.get(hi)
            if resp.ok:
                body = await resp.body()
                if len(body) > 5000:  # sanity: not an error page / placeholder
                    output_path.write_bytes(body)
                    return "hires_src_download"
        except Exception:
            pass
    if src:
        try:
            resp = await page.request.get(src)
            if resp.ok:
                output_path.write_bytes(await resp.body())
                return "src_download"
        except Exception:
            pass
    img_el = await page.query_selector("#ImageViewer1_docImage")
    if img_el:
        try:
            await img_el.screenshot(path=str(output_path))
            return "screenshot"
        except Exception:
            pass
    return "failed"


_MSOUTH_IMG_READY_JS = (
    "() => { const i = document.querySelector('#ImageViewer1_docImage');"
    " return !!(i && i.src && !i.src.includes('loading') && i.naturalWidth > 100); }"
)


async def _msouth_grantor_check(
    g_page: Page,
    last: str,
    first: str,
    original_book: str,
    original_page: str,
    searched_label: str,
) -> list:
    """
    Grantor search on Middlesex South; returns rows that are not the original
    deed. No Reverse Party column exists on this grid, so 'grantee' is ''.
    """
    await _msouth_search(g_page, last, first, "D")
    if not await _has_results(g_page, timeout_ms=40000):
        return []
    rows = []
    for r in await _read_all_result_rows_paginated(g_page, cols=_MSOUTH_COLS):
        if r["book"] == original_book and r["page"] == original_page:
            continue  # the vesting deed itself, indexed under both party types
        rows.append({
            "book":          r["book"],
            "page":          r["page"],
            "doc_number":    r["doc_number"],
            "deed_type":     r["deed_type"],
            "recorded_date": r["recorded_date"],
            "grantee":       "",  # grid has no Reverse Party column
            "street":        r["street"],
            "town":          "",
            "searched_name": searched_label,
        })
    return rows


async def run_middlesex_south(
    seller_last: str,
    seller_first: str,
    base_name: str,
    output_folder: Path,
    headless: bool,
    street_number: str = "",
    street_name: str = "",
    on_images_ready=None,
) -> dict:
    """
    Middlesex South District Registry of Deeds (masslandrecords.com) —
    Recorded Land fast path:
      1. Grantee name search (separate last/first fields)
      2. Non-conveyance filter + street-aware selection + Python date sort
      3. Detail panel → Doc #, # of pages, consideration, parties, references
      4. View Images tab → ImageViewerEx.aspx → hi-res download of all pages
      5. Grantor check (seller + all deed grantees)
    Registered Land (Land Court) is NOT searched — same limitation as the
    other fast paths; fall back to the manual workflow on deed_not_found.
    """
    result = {
        "status": "error",
        "registry": "Middlesex South District",
        "registry_url": MSOUTH_SEARCH,
        "registry_system": "Avenu/20-20 (ASP.NET, masslandrecords.com)",
        "book": None,
        "page": None,
        "document_number": None,
        "recorded_date": None,
        "deed_type": None,
        "consideration": None,
        "grantors": [],
        "grantees": [],
        "deed_property_address": None,
        "grantor_check": {"has_subsequent_deed": False, "deeds": []},
        # v3.26 — normalised detail-panel References (shared shape across
        # registries); leads for the discharge / title-rundown workflows.
        "cross_references": [],
        "files": [],
        "total_pages_in_viewer": None,
        "found_via_address_search": False,
        "found_via_compound_surname": False,
        "notes": [],
        "errors": [],
    }

    street_token = (street_name or "").upper().strip()

    # v3.48 (item 42) — per-stage timings, same as Suffolk and Plymouth.
    # finish() is called from the `finally` below to cover this runner's
    # early `return result` paths; it is idempotent and never raises.
    _tm = _Timings()
    _tm.mark("STEP 1 - grantee search")

    async with async_playwright() as p:
        browser = await _msouth_launch(p, headless, result)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # -----------------------------------------------------------
            # STEP 1 — GRANTEE SEARCH
            # -----------------------------------------------------------
            await _msouth_search(page, seller_last, seller_first, "I")
            if not await _has_results(page, timeout_ms=40000):
                result["status"] = "deed_not_found"
                result["notes"].append(
                    f"No results for last='{seller_last}' first='{seller_first}' "
                    "as Grantee on Middlesex South. NOTE: 403s from Incapsula "
                    "render as empty pages — if this repeats, verify the browser "
                    "passed the WAF (see launch note)."
                )
                await browser.close()
                return result

            all_rows = await _read_all_result_rows(page, cols=_MSOUTH_COLS)
            result["notes"].append(
                f"Grantee search returned {len(all_rows)} row(s). " + " | ".join(
                    f"[{r['ctl']}] Bk{r['book']}/Pg{r['page']} {r['deed_type']} "
                    f"{r['recorded_date']} street={r['street']!r}"
                    for r in all_rows
                )
            )

            deed_rows = [r for r in all_rows
                         if not _is_non_conveyance_instrument(r["deed_type"])]
            if len(deed_rows) < len(all_rows):
                result["notes"].append(
                    "Name search: filtered "
                    f"{len(all_rows) - len(deed_rows)} non-deed row(s): "
                    f"{[r['deed_type'] for r in all_rows if r not in deed_rows]}."
                )
            if not deed_rows:
                result["status"] = "deed_not_found"
                # v3.36 (item 0a): name the UNRECOGNISED types separately.
                # An unknown type is no longer kept as a deed candidate (it
                # would otherwise be reported as the vesting deed with no
                # warning), but "we did not recognise these" is a different
                # statement from "these are all non-conveyances" — and this
                # registry has no selected_row_is_not_a_deed flag to carry it.
                unknown_types = sorted({
                    r["deed_type"] for r in all_rows
                    if _classify_instrument(r.get("deed_type") or "") == "unknown"
                    and (r.get("deed_type") or "").strip()
                })
                result["notes"].append(
                    "All result rows are non-conveyance instruments — the vesting "
                    "deed may be under a different name spelling or in Registered "
                    "Land (not searched by this fast path)."
                )
                if unknown_types:
                    result["notes"].append(
                        f"NOTE: {len(unknown_types)} of the excluded type(s) were "
                        f"UNRECOGNISED rather than known non-conveyances: "
                        f"{unknown_types}. They were NOT reported as the vesting "
                        "deed (an unknown type must not be), but check them by "
                        "hand before concluding no deed exists, and add any real "
                        "conveyance type to the script vocabulary."
                    )
                await browser.close()
                return result

            # Street-aware selection: Middlesex South's grid has no Town
            # column; the Street # cell ('10 ASHGROVE PL') stands in when a
            # seller owns multiple properties in the district.
            candidates = deed_rows
            if street_token:
                matched = [r for r in deed_rows
                           if street_token in (r["street"] or "").upper()]
                if matched:
                    if street_number:
                        num_matched = [
                            r for r in matched
                            if (r["street"] or "").upper().startswith(street_number.upper())
                        ]
                        if num_matched:
                            matched = num_matched
                    candidates = matched
                elif len(deed_rows) > 1:
                    result["notes"].append(
                        f"WARNING: no deed row's street matched {street_token!r} — "
                        "selecting most recent deed regardless; VERIFY the deed "
                        "image shows the expected property."
                    )

            candidates = sorted(
                candidates,
                key=lambda r: _parse_deed_date(r["recorded_date"]),
                reverse=True,
            )
            row = candidates[0]
            result["book"]          = row["book"]
            result["page"]          = row["page"]
            result["recorded_date"] = row["recorded_date"]
            result["deed_type"]     = row["deed_type"]
            result["deed_property_address"] = row["street"]
            result["notes"].append(
                f"Selected row: {row['deed_type']} Bk{row['book']}/Pg{row['page']} "
                f"{row['recorded_date']} | Name: {row['name']} | Street: {row['street']}"
            )

            _tm.mark("STEP 2 - detail panel")
            # -----------------------------------------------------------
            # STEP 2 — DETAIL PANEL (Doc #, pages, consideration, parties)
            # -----------------------------------------------------------
            panel_opened = await _open_detail_panel(page, ctl=row["ctl"], expected_book=row["book"])
            detail_pages = ""
            if panel_opened:
                parties = await _read_detail_panel(page)   # parties + references
                msouth  = await _msouth_read_detail(page)  # header table
                result["grantors"]        = parties["grantors"]
                result["grantees"]        = parties["grantees"]
                result["document_number"] = msouth["doc_number"] or None
                result["consideration"]   = msouth["consideration"] or None
                detail_pages              = msouth["num_pages"]
                result["notes"].append(
                    f"Detail panel: Doc#{msouth['doc_number']} pages={msouth['num_pages']} "
                    f"consideration={msouth['consideration']} | "
                    f"Grantors: {parties['grantors']} | Grantees: {parties['grantees']}"
                )
                # v3.50 — the complete References list, every pager page.
                msouth_refs = parties.get("references") or []
                result["detail_references"] = msouth_refs
                result["detail_references_expected"] = parties.get("references_expected")
                result["detail_references_complete"] = parties.get("references_complete")
                if parties.get("references_note"):
                    result["notes"].append(parties["references_note"])
                if msouth_refs:
                    result["notes"].append(
                        "Detail panel references (cross-refs — discharges etc.): "
                        + " | ".join(msouth_refs[:8])
                        + (f" | ...(+{len(msouth_refs) - 8} more — all in "
                           "cross_references)" if len(msouth_refs) > 8 else "")
                    )
                    # v3.26 — normalised into the shared cross_references
                    # shape (full list, not the note's first 8).
                    result["cross_references"] = _normalize_cross_references(
                        msouth_refs, "Middlesex South detail panel")
                    xnote = _cross_reference_note(result["cross_references"])
                    if xnote:
                        result["notes"].append(xnote)
            else:
                result["grantors"] = []
                result["grantees"] = [row["name"]] if row["name"] else []
                result["notes"].append(
                    "Detail panel did not open — party/doc#/consideration data limited "
                    "to the results row."
                )

            _tm.mark("STEP 3 - page images")
            # -----------------------------------------------------------
            # STEP 3 — VIEW IMAGES → ImageViewerEx.aspx → hi-res download
            # -----------------------------------------------------------
            try:
                vi_tab = await page.query_selector('a[href*="TabController1$ImageViewertabitem"]')
                if vi_tab:
                    await vi_tab.click()
                    await page.wait_for_timeout(1500)
            except Exception as e:
                result["notes"].append(f"View Images tab click error (non-fatal): {e}")

            await page.goto(MSOUTH_VIEWER, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_function(_MSOUTH_IMG_READY_JS, timeout=45000)
            except Exception:
                result["errors"].append("Image viewer did not load a document image.")
                await browser.close()
                return result

            total_pages = await _parse_page_count(page)
            result["total_pages_in_viewer"] = total_pages
            if detail_pages and str(total_pages) != str(detail_pages).strip():
                result["notes"].append(
                    f"NOTE: viewer page count ({total_pages}) differs from detail "
                    f"panel # of Pgs. ({detail_pages}) — verify all pages captured."
                )

            for page_num in range(1, total_pages + 1):
                if page_num > 1:
                    prev_src = await page.evaluate(
                        "() => document.querySelector('#ImageViewer1_docImage').src")
                    try:
                        await page.click("#ImageViewer1_BtnNext")
                        await page.wait_for_function(
                            "(prev) => { const i = document.querySelector('#ImageViewer1_docImage');"
                            " return !!(i && i.src && i.src !== prev &&"
                            " !i.src.includes('loading') && i.naturalWidth > 100); }",
                            arg=prev_src, timeout=45000,
                        )
                    except Exception as e:
                        result["notes"].append(f"Page {page_num} navigation error (stopping): {e}")
                        break
                p_path = output_folder / f"{base_name} - deed_p{page_num}.jpg"
                method = await _msouth_download_viewer_image(page, p_path)
                if method != "failed":
                    result["files"].append(str(p_path))
                    result["notes"].append(f"Page {page_num} saved ({method}): {p_path.name}")
                else:
                    result["errors"].append(f"Page {page_num} download failed.")

            # v3.54 (item 57) — the page images are final here and the grantor
            # check below reads only index data, so hand the images to the caller
            # now: main() starts the extraction API call on a worker thread and
            # joins it after this runner returns.
            if on_images_ready is not None and result["files"]:
                try:
                    on_images_ready(result)
                except Exception as e:
                    result["notes"].append(
                        f"Early extraction not started (non-fatal): {e}")

            _tm.mark("STEP 4 - grantor check")
            # -----------------------------------------------------------
            # STEP 4 — GRANTOR CHECK (seller + all deed grantees)
            #
            # v3.32 (item 21a): per-search error isolation + accounting.
            # One try/except used to wrap every search, so a failure in
            # search #1 silently cancelled the co-owner searches while the
            # run still reported success; and with no per-search record,
            # "searched, all rows duplicate" and "never searched" produced
            # byte-identical output (the item 11 defect, third platform).
            # An errored search now lands in incomplete_searches and the
            # closing note says INCOMPLETE — never "no subsequent
            # instruments found".
            # -----------------------------------------------------------
            names_to_check: dict[tuple, str] = {}
            seller_key = (seller_last.upper().strip(), seller_first.upper().strip())
            names_to_check[seller_key] = f"named seller ({seller_last} {seller_first})".strip()
            for grantee_display in result.get("grantees", []):
                key = _msouth_split_name(grantee_display)
                # v3.32 (item 11b, first-name axis): the first-name field is
                # a PREFIX match (proven live: querying 'ALAN' reached
                # 'ALAN GEORGE'), so a co-owner queried with a full
                # multi-token first name ('ANNA MARIE') can never reach an
                # instrument indexed under the bare 'ANNA'. Truncate to the
                # first token — a strict superset under prefix matching,
                # the same move as Plymouth's middle-initial drop.
                first_tok = key[1].split()[0] if key[1] else ""
                bkey = (key[0], first_tok)
                if key[0] and bkey != seller_key and bkey not in names_to_check:
                    names_to_check[bkey] = f"{grantee_display} (co-owner from detail panel)"

            search_log: list[dict] = []
            all_grantor_rows: list[dict] = []
            seen: set[tuple] = set()
            g_page = None
            try:
                g_page = await context.new_page()
            except Exception as e:
                for label in names_to_check.values():
                    search_log.append({
                        "name": "", "label": label, "rows_returned": None,
                        "rows_new": 0,
                        "status": f"ERROR — could not open search page: {e}",
                    })
                    result["grantor_check"].setdefault(
                        "incomplete_searches", []).append(label)
            if g_page is not None:
                for (g_last, g_first), label in names_to_check.items():
                    disp = f"{g_last} {g_first}".strip()
                    entry = {"name": disp, "label": label,
                             "rows_returned": None, "rows_new": 0, "status": "ok"}
                    try:
                        rows = await _msouth_grantor_check(
                            g_page, g_last, g_first,
                            result["book"] or "", result["page"] or "", label,
                        )
                        entry["rows_returned"] = len(rows)
                        for r in rows:
                            rkey = (r["book"], r["page"])
                            if rkey not in seen:
                                seen.add(rkey)
                                entry["rows_new"] += 1
                                all_grantor_rows.append(r)
                                result["notes"].append(
                                    f"Grantor check hit [{label}]: Bk{r['book']}/Pg{r['page']} "
                                    f"{r['deed_type']} {r['recorded_date']} | {r['street']}"
                                )
                    except Exception as e:
                        # This name was NOT searched — an open question, not
                        # a clean answer. Keep going: the remaining names'
                        # searches are independent of this failure.
                        entry["status"] = f"ERROR — {type(e).__name__}: {e}"
                        result["grantor_check"].setdefault(
                            "incomplete_searches", []).append(label)
                    search_log.append(entry)
                try:
                    await g_page.close()
                except Exception:
                    pass

            # Platform-generic recorder (Plymouth-named for historical
            # reasons; nothing in it is Plymouth-specific).
            _plymouth_record_searches(result, search_log)
            result["grantor_check"]["has_subsequent_deed"] = len(all_grantor_rows) > 0
            result["grantor_check"]["deeds"] = [
                f"Bk{r['book']}/Pg{r['page']} {r['deed_type']} {r['recorded_date']} "
                f"| {r['street']} | [found via: {r['searched_name']}]"
                for r in all_grantor_rows
            ]
            errored = [s for s in search_log
                       if str(s.get("status", "")).startswith("ERROR")]
            if errored:
                result["notes"].append(
                    f"CRITICAL: grantor check is INCOMPLETE — {len(errored)} of "
                    f"{len(search_log)} search(es) did not run "
                    f"({', '.join(s['label'] for s in errored)}). The hits above "
                    "are from the searches that completed. NEVER report clean "
                    "title from this run; re-run the failed name(s) before "
                    "concluding anything."
                )
            elif all_grantor_rows:
                result["notes"].append(
                    f"Grantor check: {len(all_grantor_rows)} instrument(s) found — "
                    "Claude must assess title flags. (No Reverse Party column on "
                    "this registry: open the detail panel or deed image for the "
                    "counterparty of any DEED-type hit.)"
                )
            else:
                result["notes"].append(
                    f"Grantor check: no subsequent instruments found "
                    f"(all {len(search_log)} search(es) completed)."
                )

        except Exception as e:
            result["errors"].append(f"Main workflow failed: {e}")
            await browser.close()
            return result
        finally:
            _tm.finish(result)
            try:
                await page.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    result["status"] = "success" if result["files"] else "error"
    return result


# ---------------------------------------------------------------------------
# Suffolk County — masslandrecords.com/suffolk (Avenu/20-20, Incapsula WAF)
# ---------------------------------------------------------------------------
#
# Probed live 2026-08-18. Suffolk runs the SAME Avenu/20-20 build as Middlesex
# South — identical form IDs (SearchFormEx1_ACSTextBox_LastName1 /
# _FirstName1, PartyType1 as a select with ''/D/I, btnSearch), the same
# Incapsula WAF (a plain HTTP GET returns a 212-byte block page, so there is
# no pure-HTTP engine here: headful real Chrome only), the same
# ImageViewerEx.aspx viewer and the same ACSResource.axd hi-res rewrite.
#
# What is NOT like Middlesex South, and is the reason this is its own runner:
#
#   * TWO OFFICES on one page. A single Office dropdown
#     (SearchCriteriaOffice1_DDL_OfficeName, postback on change) switches
#     between "Recorded Land" and "Registered Land (Land Court)". Suffolk has
#     a great deal of Registered Land, and a Land Court parcel's vesting deed
#     is INVISIBLE to a Recorded Land search — searching only the default
#     office would report deed_not_found on a parcel whose deed is right
#     there under the other option. The default here searches BOTH and
#     selects across the combined candidates.
#
#   * The Land Court grid has NO Book/Page columns. Its columns are
#     Type | Name/Corporation | Doc. # | Type Desc. | File Date | Street # |
#     Property Descr. The shared row reader anchored on 'Book' and therefore
#     returned ZERO rows against it (and _open_detail_panel clicked a Book
#     link that does not exist, so the panel never opened) — both now take an
#     anchor parameter, and the Land Court paths pass 'Type Desc'.
#
#   * Land Court instruments are cited by Document No. + Certificate of
#     Title, never by Book/Page. The panel's Book/Page cell on a Land Court
#     document is the Land Court REGISTRATION book/page, which is not a
#     Recorded Land citation and must never be emitted as one.
#
# Cover sheets track ELECTRONIC RECORDING, not the office: a 2026 Land Court
# deed (Doc 812445) opens with "Suffolk County Registry of Deeds /
# Electronically Recorded Document / This is the first page of the document",
# while a 2001 Land Court deed (Doc 604118) begins with the deed itself.
# Nothing may assume page 1 is — or is not — a cover sheet; the legal
# description is found by reading, not by page number.
#
# Image resolution: the old manual note ("~217x281 px, some text illegible")
# described the on-page render. The scripted path rewrites the ACSResource.axd
# request to CNTHEIGHT=2000 and gets a 1542x2000 JPEG (measured live
# 2026-08-18) — fully legible. Do not repeat the low-resolution warning.
# ---------------------------------------------------------------------------

SUFFOLK_SEARCH = "https://www.masslandrecords.com/suffolk/D/Default.aspx"
SUFFOLK_VIEWER = "https://www.masslandrecords.com/suffolk/D/ImageViewerEx.aspx"

_SUFFOLK_OFFICE_SELECT     = "#SearchCriteriaOffice1_DDL_OfficeName"
_SUFFOLK_OFFICE_RECORDED   = "Recorded Land"
_SUFFOLK_OFFICE_REGISTERED = "Registered Land (Land Court)"

# Recorded Land grid: Type | Name/ Corporation | Book | Page | Type Desc. |
# File Date | Street # | Property Descr  (no Town, Doc #, or Reverse Party —
# unmatched columns read as ''), i.e. Middlesex South's layout exactly.
_SUFFOLK_RL_COLS = {
    # "Type_" not "Type": the row reader matches the column name as a
    # SUBSTRING of the cell link's href, and bare "Type" also matches
    # "ButtonRow_Type Desc._N" (the document type). The trailing underscore
    # is the row-index separator, so "Type_" hits the role column only.
    "party_role": "Type_",
    "book": "Book", "page": "Page", "doc_number": "Doc",
    "deed_type": "Type Desc", "recorded_date": "File Date",
    "street": "Street", "town": "Town",
    "reverse_party": "Reverse Party", "name": "Name",
    "descr": "Property Descr",
}

# Land Court grid: no Book/Page. Keys are OMITTED rather than mapped to '' —
# an empty column name would make the reader's href*="...ButtonRow_" selector
# match the row's FIRST link, silently filling `book` with the Type code.
_SUFFOLK_LC_COLS = {
    "party_role": "Type_",
    "doc_number": "Doc. #",
    "deed_type": "Type Desc", "recorded_date": "File Date",
    "street": "Street #", "name": "Name", "descr": "Property Descr",
}

# NO TOWN FILTER, AND NO DATE WINDOW — both were built, both were measured
# doing the wrong thing live on 2026-08-18, and both are deliberately gone.
#
#   Towns: the multi-select offers BOSTON/CHELSEA/REVERE/WINTHROP with option
#   values (100001, ...) read off the RECORDED LAND form. Those values do not
#   carry across an Office switch, so a Registered Land search submitted with
#   town=BOSTON returned ZERO ROWS for a party with 17 indexed Land Court
#   instruments — a silent, total suppression that reads exactly like
#   "this seller has no Land Court records". Boston also swallows every one
#   of its neighbourhoods, so the filter never bought much anyway.
#
#   Recorded Date From/To: the boxes exist on the basic form but are only
#   honoured through the Advanced panel. Filling DateFrom on the basic form
#   was ignored on one search (a 1/1/2020 window returned 1987 rows) and
#   appeared to zero another — nondeterministic either way, and a date filter
#   that silently does not apply is worse than no date filter at all.
#
# Both are the Plymouth municipality-cap failure mode: a narrowing control
# that hides rows without saying so. The grantor check therefore searches
# every year, which on this registry is fast (1-3s per search).


def _suffolk_office_cols(office: str) -> tuple:
    """(column map, row-anchor column) for an Office selection."""
    if office == _SUFFOLK_OFFICE_REGISTERED:
        return _SUFFOLK_LC_COLS, "Type Desc"
    return _SUFFOLK_RL_COLS, "Book"


def _suffolk_normalize_row(row: dict, office: str) -> dict:
    """
    Give every row the full key set regardless of which office produced it,
    so downstream selection and reporting never branch on a missing key.
    Land Court rows carry land_court=True and empty book/page.
    """
    is_lc = office == _SUFFOLK_OFFICE_REGISTERED
    return {
        "ctl":           row.get("ctl", ""),
        "party_role":    (row.get("party_role", "") or "").strip().upper(),
        "book":          row.get("book", "") or "",
        "page":          row.get("page", "") or "",
        "doc_number":    row.get("doc_number", "") or "",
        "deed_type":     row.get("deed_type", "") or "",
        "recorded_date": row.get("recorded_date", "") or "",
        "street":        row.get("street", "") or "",
        "descr":         row.get("descr", "") or "",
        "name":          row.get("name", "") or "",
        "town":          row.get("town", "") or "",
        "reverse_party": row.get("reverse_party", "") or "",
        "land_court":    is_lc,
        "office":        office,
        "_pager_page":   row.get("_pager_page", 1),
    }


def _suffolk_row_id(row: dict) -> str:
    """Human-readable instrument id, correct for the row's own office."""
    if row.get("land_court"):
        return f"Doc {row.get('doc_number') or '?'} (Land Court)"
    return f"Bk{row.get('book') or '?'}/Pg{row.get('page') or '?'}"


def _suffolk_row_key(row: dict) -> tuple:
    """Identity of an instrument, used to skip the vesting deed on re-find."""
    if row.get("land_court"):
        return ("LC", row.get("doc_number") or "")
    return ("RL", row.get("book") or "", row.get("page") or "")


# Certificate of Title numbers as they appear in Suffolk's index description
# and detail panel: "CERT 3915", "CERTIFICATE OF TITLE NO. 119850", "CTF 81744".
_SUFFOLK_CERT_RE = re.compile(
    r"\b(?:CERTIFICATE\s+OF\s+TITLE|CERT(?:IFICATE)?|CTF)\b[\s.]*"
    r"(?:NO\.?|NUMBER|#)?[\s.]*(\d{3,7})\b",
    re.IGNORECASE,
)


def _suffolk_parse_certificates(*texts) -> list:
    """
    Certificate-of-Title numbers mentioned in the given index/panel text, in
    order of first appearance and de-duplicated.

    These are the certificate numbers appearing in the INDEX DESCRIPTION, and
    they are NOT the operative certificate for the deed. Confirmed against the
    images 2026-08-18: the description's number is the certificate the land is
    described on — the one being transferred OUT of, often the original
    registration certificate for the plan lot — while the certificate the deed
    is actually noted on is the detail panel's Certificate/Encumbrance
    reference.

      Doc 812445 (2026): description "PL 19472-A CERT 64188"; panel reference
      198332; the deed's own cover sheet reads "Noted on Certificate: 198332".
      Doc 604118 (2001): description "CERT 3915"; panel reference 121904; the
      deed recites the grantor's title as Certificate No. 119850.

    So the caller uses the panel reference as certificate_of_title and keeps
    these as a secondary, clearly-labelled field.
    """
    found: list = []
    for t in texts:
        for m in _SUFFOLK_CERT_RE.finditer(t or ""):
            n = m.group(1).lstrip("0") or m.group(1)
            if n not in found:
                found.append(n)
    return found


def _suffolk_prefix_name_warning(indexed: str, want_first: str) -> str:
    """
    v3.40 — the warning for a row whose indexed first name merely STARTS WITH
    the requested one.

    Suffolk's First Name box is a prefix match, so a search for JULIAN also
    returns JULIANA, JULIANNE and JULIANO. Live 2026-08-18 that is exactly how
    a run for 'Julian Hollister' at 15 Larkspur Road selected HOLLISTER JULIANA's
    2020 deed for 52 Bayard St — a different person and a different parcel,
    and nothing in the output said so.

    Returns '' when the indexed first name equals the requested one (or when
    either is unavailable, which is not evidence of a mismatch).
    """
    want = (want_first or "").upper().strip().split()
    toks = _clean_registry_name(indexed or "").upper().split()
    if not want or len(toks) < 2:
        return ""
    got_first, want_first_tok = toks[1], want[0]
    if got_first == want_first_tok or not got_first.startswith(want_first_tok):
        return ""
    return (f"NEEDS REVIEW: the selected row is indexed to {indexed!r}, whose "
            f"first name {got_first!r} only STARTS WITH the requested "
            f"{want_first_tok!r} — Suffolk's First Name box is a prefix match, "
            f"so this may be a DIFFERENT PERSON. Confirm the grantee on the "
            f"deed image before relying on this instrument.")


# The Search Type dropdown is rendered by the SERVER as "<office> Name
# Search", so it reflects the office the server will actually search. The
# Office dropdown is NOT a safe signal: select_option sets its value in the
# DOM instantly, ~0.5s before the __doPostBack it triggers comes back.
_SUFFOLK_SEARCHNAME_SELECT = "#SearchCriteriaName1_DDL_SearchName"


async def _suffolk_select_office(page: Page, office: str) -> bool:
    """
    Switch the Office dropdown and wait for its postback to actually land.

    Returns False when the select is missing or the switch does not take —
    never True on a guess.

    v3.40, and the reason this function is careful: the obvious check —
    re-read the Office dropdown until it equals the requested office —
    passes INSTANTLY and proves nothing, because select_option already set
    that value client-side. Measured live 2026-08-18: at t=0 the Office
    select read "Registered Land (Land Court)" while the server still had
    "Recorded Land Name Search" loaded; the switch only landed at ~0.5s.

    The consequence was not a slow search but a WRONG one. A run that
    searched Recorded Land first and then "Registered Land" got the RECORDED
    LAND grid back both times and reported those rows as Land Court results —
    and because the Land Court column map finds no "Doc. #" column on a
    Recorded Land grid, they arrived as documentless rows that still looked
    like ordinary Land Court hits. The parcel's real Land Court deed was
    never seen. So the wait is on the server-rendered Search Type value.
    """
    try:
        read = ("(sel) => { const s = document.querySelector(sel);"
                " return s ? s.value : null; }")
        cur = await page.evaluate(read, _SUFFOLK_OFFICE_SELECT)
        if cur is None:
            return False
        # Even when the Office select already reads the target, confirm the
        # SERVER agrees before returning True.
        if cur != office:
            await page.select_option(_SUFFOLK_OFFICE_SELECT, office)
            await page.wait_for_selector(
                "#SearchFormEx1_ACSTextBox_LastName1", timeout=30000)
        for _ in range(60):  # up to 15s
            name = await page.evaluate(read, _SUFFOLK_SEARCHNAME_SELECT)
            if name and name.startswith(office):
                return True
            await page.wait_for_timeout(250)
        return False
    except Exception:
        return False


# Search Type is per-office: the dropdown's values are "<office> <kind>", and
# switching Office resets it to "<office> Name Search". Both offices offer a
# Property (address) search over Street Number + Street Name, reached from the
# Search Criteria menu; Registered Land additionally offers a Certificate
# Search, which this workflow does not yet use.
_SUFFOLK_KIND_NAME     = "Name Search"
_SUFFOLK_KIND_PROPERTY = "Property Search"


# The PROPERTY search grid is a different shape from the name grid, and is
# the SAME in both offices: Street Name | File Date | Book/Page | Type Desc. |
# # of Pgs. Note what is missing — no Name/Corporation, and no Doc. # even on
# Land Court, so an address hit carries no party name and no document number
# until its detail panel is opened.
_SUFFOLK_PROP_COLS = {
    "street":        "Street Name",
    "recorded_date": "File Date",
    "book_page":     "Book/Page",
    "deed_type":     "Type Desc",
    "num_pages":     "# of Pgs",
}


def _suffolk_normalize_prop_row(row: dict, office: str) -> dict:
    """
    Normalise a PROPERTY-search row into the same shape as a name-search row.

    The grid's combined "Book/Page" cell means different things per office and
    is split accordingly: on Recorded Land it is the real Book/Page citation;
    on Land Court it is the LAND COURT REGISTRATION book/page, which is not a
    citation at all and is kept out of `book`/`page` so nothing downstream can
    print it as one. The document number is simply not available here — it
    comes from the detail panel.
    """
    is_lc = office == _SUFFOLK_OFFICE_REGISTERED
    bp = (row.get("book_page") or "").strip()
    book = page_ = ""
    if bp and not is_lc:
        parts = bp.split("/", 1)
        book = parts[0].strip()
        page_ = parts[1].strip() if len(parts) > 1 else ""
    return {
        "ctl":           row.get("ctl", ""),
        "book":          book,
        "page":          page_,
        "doc_number":    "",
        "deed_type":     row.get("deed_type", "") or "",
        "recorded_date": row.get("recorded_date", "") or "",
        "street":        row.get("street", "") or "",
        "descr":         "",
        "name":          "",
        "town":          "",
        "reverse_party": "",
        "land_court":    is_lc,
        "office":        office,
        "via_address":   True,
        "lc_book_page":  bp if is_lc else "",
        "_pager_page":   row.get("_pager_page", 1),
    }


def _suffolk_prop_row_key(row: dict) -> tuple:
    """
    Identity of a property-search row. Book/Page + date + type, because the
    property grid gives no document number and no party name to key on.
    """
    return (row.get("office", ""),
            row.get("lc_book_page") or f"{row.get('book','')}/{row.get('page','')}",
            row.get("recorded_date", ""),
            (row.get("deed_type") or "").upper())


async def _suffolk_select_search_type(page: Page, office: str, kind: str) -> bool:
    """
    Switch the Search Type dropdown within the current office.

    Same postback race as the Office dropdown, and the same rule: the value is
    server-rendered, so wait for it rather than trusting the select. Returns
    False if the switch does not take — the caller must not read the grid,
    because a Property Search that silently stayed on Name Search submits an
    EMPTY name and returns the whole index.
    """
    want = f"{office} {kind}"
    read = ("(sel) => { const s = document.querySelector(sel);"
            " return s ? s.value : null; }")
    try:
        if await page.evaluate(read, _SUFFOLK_SEARCHNAME_SELECT) == want:
            return True
        await page.select_option(_SUFFOLK_SEARCHNAME_SELECT, want)
        for _ in range(60):  # up to 15s
            if await page.evaluate(read, _SUFFOLK_SEARCHNAME_SELECT) == want:
                return True
            await page.wait_for_timeout(250)
        return False
    except Exception:
        return False


async def _suffolk_open(page: Page, office: str, kind: str) -> bool:
    """Load the search page and put it on the requested office + search type."""
    await page.goto(SUFFOLK_SEARCH, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_selector(
        "#SearchFormEx1_ACSTextBox_LastName1, #SearchFormEx1_ACSTextBox_StreetName",
        timeout=30000)
    if not await _suffolk_select_office(page, office):
        return False
    return await _suffolk_select_search_type(page, office, kind)


async def _suffolk_address_search(
    page: Page, office: str, street_number: str, street_name: str,
) -> bool:
    """
    Property (address) search in the given office. Returns False if the office
    or search-type switch failed.

    Street Name is the only required field. The number is passed when known and
    narrows server-side; it is NOT relied on for correctness, because the
    registry's own Street # cell is free text ("15", "15-17", "" on older
    filings) and an over-narrow number can hide the parcel.
    """
    if not await _suffolk_open(page, office, _SUFFOLK_KIND_PROPERTY):
        return False
    await page.fill("#SearchFormEx1_ACSTextBox_StreetName", street_name.upper().strip())
    if street_number:
        await page.fill("#SearchFormEx1_ACSTextBox_StreetNumber",
                        street_number.upper().strip())
    await page.click("#SearchFormEx1_btnSearch")
    return True


# ---------------------------------------------------------------------------
# The 1,000-record cap (v3.41)
# ---------------------------------------------------------------------------
#
# An over-broad search is answered with a modal — "Your search results have
# been limited to the first 1,000 records. Please narrow your search criteria
# by clicking on the 'Advanced' button" — and the grid behind it renders ZERO
# rows. Measured live 2026-08-20 on a common surname, Recorded Land: Grantee
# alone 20+ rows, Grantor alone 20+ rows, Both 0 rows + this dialog.
#
# Read by code that waits for a grid link, that is indistinguishable from "this
# party has nothing indexed". In a GRANTOR check the two answers are "no deed
# out" and "we never looked" — this is the Plymouth v3.18 municipality-cap
# failure on a registry that actually TELLS you, so the message is consumed
# rather than thrown away. A capped search is never clean.
#
# Note the shape differs from Plymouth's: Plymouth returns the oldest 1,000
# rows (sorted after the cap, so the newest are missing but rows exist here);
# Suffolk returns NOTHING. That makes it more dangerous to miss and easier to
# detect.
_SUFFOLK_CAP_LABEL = "#MessageBoxCtrl1_ErrorLabel1"
_SUFFOLK_CAP_OK    = "#MessageBoxCtrl1_buttonmbatCLIENTOK"
_SUFFOLK_CAP_RE    = re.compile(
    r"limited to the first\s+([\d,]+)\s+record", re.IGNORECASE)


# The registry ALSO announces an empty result in the same dialog: "Search
# criteria resulted in 0 hits. Please verify the search criteria and try
# again." Nothing consumed that either, so every genuinely-empty search sat
# out the full grid timeout before being called empty by exhaustion.
#
# That was the real cost of this registry, not the search itself. Measured
# 2026-08-20 on a seller with no Land Court records: 28 s per search averaged
# over four searches, of which the two empty Land Court passes were ~45 s
# each — the registry had said "0 hits" about one second in, both times.
_SUFFOLK_ZERO_RE = re.compile(r"resulted in\s+0\s+hits", re.IGNORECASE)


async def _suffolk_dialog_text(page: Page) -> str:
    """Text of the registry's message dialog if one is up, else ''."""
    try:
        el = await page.query_selector(_SUFFOLK_CAP_LABEL)
        if not el or not await el.is_visible():
            return ""
        return (await el.inner_text()).strip()
    except Exception:
        return ""


async def _suffolk_cap_message(page: Page) -> str:
    """The dialog's text if it is the 1,000-record cap, else ''."""
    text = await _suffolk_dialog_text(page)
    return text if _SUFFOLK_CAP_RE.search(text) else ""


async def _suffolk_dismiss_dialog(page: Page) -> None:
    """Click Ok so the form is usable for whatever runs next."""
    try:
        btn = await page.query_selector(_SUFFOLK_CAP_OK)
        if btn and await btn.is_visible():
            await btn.click()
            await page.wait_for_timeout(400)
    except Exception:
        pass


async def _suffolk_search_outcome(page: Page, timeout_ms: int = 45000) -> str:
    """
    Resolve a submitted search: 'rows' | 'capped' | 'empty' | 'dialog: <text>'.

    Races the results grid against the registry's own message dialog rather
    than waiting for the grid alone. Waiting for the grid could only ever end
    in a timeout for the two cases the registry states outright — the 1,000
    record cap and a 0-hit search — and it then reported BOTH as "nothing
    indexed", which for a capped grantor search is the false clean this
    module most needs to avoid.

    An UNRECOGNISED dialog is returned as-is instead of being folded into
    'empty': a message this code does not understand is missing information,
    never evidence that a party has nothing on record.
    """
    waited = 0
    while waited < timeout_ms:
        if await page.query_selector(
                'a[href*="GridView_Document$ctl02$ButtonRow"]'):
            return "rows"
        text = await _suffolk_dialog_text(page)
        if text:
            if _SUFFOLK_CAP_RE.search(text):
                return "capped"
            if _SUFFOLK_ZERO_RE.search(text):
                return "empty"
            return f"dialog: {text[:200]}"
        await page.wait_for_timeout(250)
        waited += 250
    return "empty"


async def _suffolk_read_grid(page: Page, office: str, result: dict,
                            kind: str = _SUFFOLK_KIND_NAME) -> tuple:
    """
    Read the grid now on screen as `office`'s, for the given search kind.
    Shared by the name and address paths so neither can skip the check that
    the rows really belong to the office they are about to be filed under.

    The check is the SERVER-rendered Search Type ("<office> <kind>"), not the
    grid shape. Shape works for name searches — Recorded Land has a Book
    column and Land Court does not — but the PROPERTY grids of the two offices
    are identical, and their combined "Book/Page" column contains the
    substring "Book", so a shape test both fails to discriminate and misfires.
    """
    outcome = await _suffolk_search_outcome(page, timeout_ms=45000)
    if outcome == "capped":
        msg = await _suffolk_cap_message(page)
        await _suffolk_dismiss_dialog(page)
        if result is not None:
            result.setdefault("notes", []).append(
                f"{office}: the registry CAPPED this search and returned no "
                f"rows at all — {msg!r}. This is NOT 'nothing indexed'.")
        return [], "capped"
    if outcome.startswith("dialog:"):
        await _suffolk_dismiss_dialog(page)
        if result is not None:
            result.setdefault("notes", []).append(
                f"CRITICAL: {office}: the registry answered this search with a "
                f"message this script does not recognise — {outcome[8:]!r}. The "
                "search was NOT completed and its rows, if any, were not read. "
                "This is not 'nothing indexed'; read the message and re-run.")
        return [], "unknown_dialog"
    if outcome == "empty":
        await _suffolk_dismiss_dialog(page)
        return [], "no_results"
    stype = await page.evaluate(
        "(sel) => { const s = document.querySelector(sel);"
        " return s ? s.value : null; }", _SUFFOLK_SEARCHNAME_SELECT)
    if stype != f"{office} {kind}":
        return [], "office_mismatch"
    if kind == _SUFFOLK_KIND_PROPERTY:
        raw = await _read_all_result_rows_paginated(
            page, flags=result, cols=_SUFFOLK_PROP_COLS,
            notes=result.get("notes"), anchor="Type Desc")
        return [_suffolk_normalize_prop_row(r, office) for r in raw], "ok"
    # Name grid: keep the shape assertion too — it is what caught the
    # Office-switch race, and it is independent of the dropdown.
    has_book = await page.query_selector(
        'a[href*="GridView_Document$ctl02$ButtonRow_Book"]') is not None
    if has_book != (office == _SUFFOLK_OFFICE_RECORDED):
        return [], "office_mismatch"
    cols, anchor = _suffolk_office_cols(office)
    raw = await _read_all_result_rows_paginated(
        page, flags=result, cols=cols, notes=result.get("notes"), anchor=anchor)
    return [_suffolk_normalize_row(r, office) for r in raw], "ok"


async def _suffolk_relocate_prop_row(
    page: Page, office: str, result: dict, target: dict,
    street_number: str, street_name: str,
) -> str:
    """
    Replay the address search and return the live ctl of `target`.

    The name-search relocation cannot be reused here: it matches on
    (book, doc_number, name), and a property-grid row has no party name and no
    document number at all. Matching is on the property key instead —
    office + book/page + date + type.
    """
    if not await _suffolk_address_search(page, office, street_number, street_name):
        return ""
    if not await _has_results(page, timeout_ms=40000):
        return ""
    want = _suffolk_prop_row_key(target)
    await _avenu_set_page_size_100(page)
    for _ in range(_AVENU_MAX_PAGES):
        for r in await _read_all_result_rows(
                page, cols=_SUFFOLK_PROP_COLS, anchor="Type Desc"):
            if _suffolk_prop_row_key(
                    _suffolk_normalize_prop_row(r, office)) == want:
                return r["ctl"]
        if not await _avenu_click_next_page(page):
            break
    return ""


async def _suffolk_office_rows_by_address(
    page: Page, office: str, result: dict, street_number: str, street_name: str,
) -> tuple:
    """One office's rows for an address search. Same contract as the name path."""
    if not await _suffolk_address_search(page, office, street_number, street_name):
        return [], "office_switch_failed"
    return await _suffolk_read_grid(page, office, result,
                                    kind=_SUFFOLK_KIND_PROPERTY)


async def _suffolk_search(
    page: Page, last: str, first: str, party_type: str, office: str) -> bool:
    """
    Run a name search in the given Office. Returns False if the office or
    search-type switch failed — the caller must NOT read the grid then.

    Deliberately submits NO town and NO date narrowing; see the module note.
    """
    if not await _suffolk_open(page, office, _SUFFOLK_KIND_NAME):
        return False
    await page.select_option(
        "#SearchFormEx1_ACSRadioButtonList_PartyType1", party_type)
    await page.fill("#SearchFormEx1_ACSTextBox_LastName1", last.upper().strip())
    await page.fill("#SearchFormEx1_ACSTextBox_FirstName1", first.upper().strip())
    await page.click("#SearchFormEx1_btnSearch")
    return True


async def _suffolk_read_detail(page: Page) -> dict:
    """
    Structurally parse the Suffolk detail panel.

    Header table (both offices): Doc. # | File Date | Rec Time | Type Desc. |
    # of Pgs. | Book/Page | Consideration | Doc. Status. It MUST be read
    structurally, not by regex over the panel text: the generic consideration
    pattern matches the Rec Time value ('13:38:00.000') and a trailing
    '00.00' first — live 2026-08-18 it read a $412,500.00 deed as '00.00'.

    Also returns the property block (Street # / Street Name / Description
    lines, where a Land Court row's 'CERT 3915 LOT B-24' lives) and the
    'Certificate/Encumbrance references' list.
    """
    data = await page.evaluate(
        """() => {
            const panel = document.querySelector('[id*="DocDetails1"]');
            if (!panel) return null;
            let hdr = null;
            // Innermost matching table wins — outer wrapper tables report the
            // whole header block as one cell and misalign every value.
            for (const tbl of panel.querySelectorAll('table')) {
                const rows = tbl.querySelectorAll(':scope > tbody > tr, :scope > tr');
                if (rows.length < 2) continue;
                const h = Array.from(rows[0].querySelectorAll(':scope > th, :scope > td'))
                    .map(c => c.innerText.trim());
                if (h.length < 4) continue;
                if (!h.some(x => x === 'Doc. #' || x.startsWith('Doc. #'))) continue;
                const v = Array.from(rows[1].querySelectorAll(':scope > td'))
                    .map(c => c.innerText.trim());
                hdr = {};
                h.forEach((k, i) => { hdr[k] = v[i] !== undefined ? v[i] : ''; });
            }
            return {header: hdr, text: panel.innerText};
        }"""
    )
    empty = {"doc_number": "", "num_pages": "", "consideration": "",
             "book_page": "", "doc_status": "", "property_lines": [],
             "certificate_refs": []}
    if not data:
        return empty
    hdr = data.get("header") or {}
    full = data.get("text") or ""

    def _get(*keys):
        for k in keys:
            for h, v in hdr.items():
                if k in h:
                    return v
        return ""

    lines = [ln.strip() for ln in full.splitlines()]

    def _section(marker: str, stop_markers: tuple) -> list:
        """Non-empty lines after `marker`, up to the next section heading."""
        out = []
        started = False
        for ln in lines:
            if not started:
                if marker.lower() in ln.lower():
                    started = True
                continue
            if any(s.lower() in ln.lower() for s in stop_markers):
                break
            # Empty cells come back as U+FFFD; drop cell-padding noise.
            cleaned = ln.replace("�", "").strip()
            if cleaned:
                out.append(cleaned)
        return out

    prop = _section("Description",
                    ("Certificate/Encumbrance", "Grantor/Grantee", "References"))
    cert_refs = [t for t in _section("Certificate/Encumbrance references",
                                     ("Grantor/Grantee", "References"))
                 if re.fullmatch(r"\d{3,8}", t)]

    # v3.50 — References are read by _read_detail_panel (whole grid, every
    # pager page); the 400-character page-1 slice that lived here kept 10 of
    # a master deed's 683. See _avenu_read_references.
    return {
        "doc_number":       _get("Doc. #"),
        "num_pages":        _get("# of Pgs"),
        "consideration":    _get("Consideration"),
        "book_page":        _get("Book/Page"),
        "doc_status":       _get("Doc. Status"),
        "property_lines":   prop,
        "certificate_refs": cert_refs,
    }


async def _suffolk_office_rows(
    page: Page, last: str, first: str, party_type: str, office: str,
    result: dict,
) -> tuple:
    """
    One office's rows for one name. Returns (rows, status) where status is
    'ok' | 'office_switch_failed' | 'no_results'.

    An office that could not be selected returns 'office_switch_failed', NOT
    an empty row list — "we could not look" and "we looked and found nothing"
    must never collapse into the same value.
    """
    if not await _suffolk_search(page, last, first, party_type, office):
        return [], "office_switch_failed"
    return await _suffolk_read_grid(page, office, result)


_SUFFOLK_ROLE_GRANTEE = "GT"
_SUFFOLK_ROLE_GRANTOR  = "GR"


async def _suffolk_office_rows_both(
    page: Page, last: str, first: str, office: str, result: dict,
) -> tuple:
    """
    One office, ONE search, BOTH party roles. Returns (rows, status).

    PartyType '' ("Both") returns the party's grantee rows and grantor rows in
    a single postback, each tagged in the grid's leading Type column
    (GT = grantee, GR = grantor). Verified live 2026-08-20 against separate I
    and D searches on the same name: Both was EXACTLY their union, and the
    role tags matched the searches that produced them.

    Why it matters: the vesting-deed question and the deed-out question are
    the same index lookup asked twice. Every search here costs a full page
    navigation plus the Office-switch race, so folding them halves the
    scaffolding — on the common case (an ordinary seller, a handful of rows)
    that is most of the run's registry time.

    THE CAP IS THE CATCH. Both returns the union, so it reaches the 1,000-
    record cap sooner than either half — and a capped Suffolk search returns
    NOTHING (see the cap note above). The fallback is therefore the split
    itself: I and D run separately, which is a real narrowing axis (each is
    roughly half the rows) and is exactly the pre-v3.41 behaviour, so the
    worst case degrades to what this registry did before, never to silence.

    A half that STILL caps is reported as 'capped' with whatever the other
    half returned. Rows are never dropped and a cap is never smoothed over
    into 'no_results'.
    """
    rows, st = await _suffolk_office_rows(page, last, first, "", office, result)
    if st != "capped":
        # A grid with no role column at all cannot be split by role, and
        # guessing would risk reporting a deed OUT as the vesting deed.
        if st == "ok" and rows and not any(r.get("party_role") for r in rows):
            result.setdefault("notes", []).append(
                f"{office}: the Both search returned rows with NO party-role "
                "column — the grid layout changed. Falling back to separate "
                "Grantee and Grantor searches, which do not need it.")
        else:
            return rows, st
    else:
        result.setdefault("notes", []).append(
            f"{office}: the combined (Both) search hit the registry's "
            "1,000-record cap, which returns zero rows. Retrying as separate "
            "Grantee and Grantor searches — each is about half the result "
            "set, so the split is itself the narrowing step.")

    merged: list = []
    halves: list = []
    capped_halves: list = []
    for party, role, label in (("I", _SUFFOLK_ROLE_GRANTEE, "Grantee"),
                               ("D", _SUFFOLK_ROLE_GRANTOR, "Grantor")):
        # The cap has TWO shapes on this registry and only one of them is the
        # dialog. A search landing exactly ON the limit returns 1,000 rows and
        # says nothing; the shared reader detects that by row count and sets
        # results_truncated_at_cap. Measured 2026-08-20 on a common
        # surname, Recorded Land: Both -> dialog + 0 rows, then the Grantor
        # half -> 1,000 rows silently truncated. Watching only the dialog
        # would have called that half complete.
        _trunc_before = bool(result.get("results_truncated_at_cap"))
        got, st_h = await _suffolk_office_rows(page, last, first, party,
                                               office, result)
        truncated = (not _trunc_before
                     and bool(result.get("results_truncated_at_cap")))
        halves.append(
            f"{label}={st_h}({len(got)}{' TRUNCATED' if truncated else ''})")
        if st_h in ("office_switch_failed", "office_mismatch",
                    "unknown_dialog"):
            return merged, st_h
        # Rows are kept whether or not the half was capped — a truncated set
        # is incomplete, not wrong, and throwing away 1,000 real instruments
        # to signal "incomplete" would lose the very hits being looked for.
        for r in got:
            if not r.get("party_role"):
                r["party_role"] = role
        merged.extend(got)
        if st_h == "capped" or truncated:
            how = ("returned nothing" if st_h == "capped"
                   else "returned exactly %d rows, truncated" % len(got))
            capped_halves.append("%s (%s)" % (label, how))
    result.setdefault("notes", []).append(
        f"{office}: split search — {', '.join(halves)}.")
    if capped_halves:
        result.setdefault("notes", []).append(
            f"CRITICAL: {office}: after splitting by party type, the "
            f"{' and '.join(capped_halves)} search STILL hit the registry's "
            "1,000-record cap, so this name is NOT fully searched in "
            f"{office} and the rows below are a PARTIAL set. Never read this "
            "as a clean deed-out check. Narrow it by hand before relying on "
            "it — the Advanced panel offers a recorded-date range "
            "(ACSTextBox_DateFrom/_DateTo) and a 78-entry document-type "
            "list, either of which splits the set further.")
        return merged, "capped"
    return merged, ("ok" if merged else "no_results")


async def _suffolk_grantor_check(
    g_page: Page,
    last: str,
    first: str,
    selected_key: tuple,
    searched_label: str,
    offices: list,
    result: dict,
    prefetched: dict = None,
) -> tuple:
    """
    Grantor search for one name across the given offices.

    `prefetched` maps office -> grantor-role rows already obtained for this
    name by the combined (Both) name search, which are used instead of
    re-searching that office.

    Returns (rows, per_office_status). Both offices are searched regardless of
    which one the vesting deed came from: a seller can hold a second parcel in
    the other system, and the question this check answers — "does the
    purported owner still own it, and who are ALL the current owners" — is not
    answered by looking in one index only.

    Neither grid has a Reverse Party column, so `grantee` is '' on every hit
    and the counterparty must be read from the detail panel or the image.
    """
    rows: list = []
    status: dict = {}
    prefetched = prefetched or {}
    for office in offices:
        if office in prefetched:
            # v3.41: the seller's grantor rows already came back from the
            # combined (Both) name search in this office. Re-running the D
            # search would ask the registry a question it has already
            # answered — and would be a second chance to hit the cap.
            got, st = prefetched[office], "ok (from combined name search)"
        else:
            try:
                got, st = await _suffolk_office_rows(
                    g_page, last, first, "D", office, result)
            except Exception as e:
                status[office] = f"ERROR — {type(e).__name__}: {e}"
                continue
        status[office] = st
        if not st.startswith("ok"):
            continue
        for r in got:
            if _suffolk_row_key(r) == selected_key:
                continue  # the vesting deed itself, indexed under both parties
            r = dict(r)
            r["searched_name"] = searched_label
            rows.append(r)
    return rows, status


async def run_suffolk(
    seller_last: str,
    seller_first: str,
    base_name: str,
    output_folder: Path,
    headless: bool,
    town: str = "",
    street_number: str = "",
    street_name: str = "",
    office: str = "auto",
    force_address_search: bool = False,
    lien_sweep: bool = False,
    on_images_ready=None,
) -> dict:
    """
    Suffolk County Registry of Deeds (masslandrecords.com/suffolk) — fast path
    over BOTH offices:
      1. Grantee name search in Recorded Land AND Registered Land (Land Court)
      2. Non-conveyance filter + street-aware selection + Python date sort
      3. Detail panel → Doc #, pages, consideration, parties, certificate refs
      4. View Images → ImageViewerEx.aspx → hi-res download of all pages
      5. Grantor check (seller + all deed grantees) across both offices

    Unlike every other fast path, Registered Land is NOT skipped here — see
    the module comment above. `office` is 'auto' (both), 'recorded', or
    'registered'.
    """
    offices = {
        "auto":       [_SUFFOLK_OFFICE_RECORDED, _SUFFOLK_OFFICE_REGISTERED],
        "recorded":   [_SUFFOLK_OFFICE_RECORDED],
        "registered": [_SUFFOLK_OFFICE_REGISTERED],
    }.get((office or "auto").lower(), [_SUFFOLK_OFFICE_RECORDED,
                                       _SUFFOLK_OFFICE_REGISTERED])

    result = {
        "status": "error",
        "registry": "Suffolk County",
        "registry_url": SUFFOLK_SEARCH,
        "registry_system": "Avenu/20-20 (ASP.NET, masslandrecords.com)",
        "offices_searched": [],
        "office_of_record": None,
        "land_court": False,
        "book": None,
        "page": None,
        "document_number": None,
        "certificate_of_title": None,
        "certificate_in_index_description": None,
        "certificate_references": [],
        "land_court_registration_book_page": None,
        "recorded_date": None,
        "deed_type": None,
        "consideration": None,
        "grantors": [],
        "grantees": [],
        "deed_property_address": None,
        "grantor_check": {"has_subsequent_deed": False, "deeds": [],
                          "needs_review": [], "summary": None, "searches": []},
        "detail_references": [],
        "cross_references": [],
        "files": [],
        "total_pages_in_viewer": None,
        "found_via_address_search": False,
        "found_via_compound_surname": False,
        "selected_row_is_not_a_deed": False,
        "results_truncated_at_cap": False,
        "street_match": "not_checked",
        "wrong_parcel_risk": False,
        "needs_review": [],
        "notes": [],
        "errors": [],
    }

    if town:
        result["notes"].append(
            f"NOTE: --town {town!r} was IGNORED. Suffolk's Towns filter is not "
            "applied by this path — its option values do not survive an Office "
            "switch and silently returned zero rows on Registered Land (see "
            "module note). The search covers all four municipalities.")

    street_token = (street_name or "").upper().strip()

    # v3.48 (item 42) — per-stage timings, as Plymouth got at v3.47 and the
    # ALIS flow has had since v3.31. Without them --no-timings/show_timings
    # was a setting that silently did nothing on this registry, and
    # _timings_add_stage no-opped, so the inline-extraction stage went
    # unmeasured too. finish() is called from the `finally` below because
    # this runner has several early `return result` paths; it is idempotent
    # and swallows its own errors.
    _tm = _Timings()
    _tm.mark("STEP 1 - grantee search")

    async with async_playwright() as p:
        browser = await _msouth_launch(p, headless, result)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # -----------------------------------------------------------
            # STEP 1 — GRANTEE SEARCH, EVERY REQUESTED OFFICE
            #
            # Each office is recorded with its own outcome. An office that
            # could not be switched to is an OPEN QUESTION, never a quiet
            # zero: on a Land Court parcel, a failed Registered Land switch
            # plus an empty Recorded Land result would otherwise read as a
            # confident "no deed exists".
            # -----------------------------------------------------------
            all_rows: list = []
            failed_offices: list = []
            if force_address_search:
                result["notes"].append(
                    "--force-address-search: skipping the name search entirely; "
                    f"searching by address for {street_number or '(no number)'} "
                    f"{street_token or '(no street)'}.")
                offices_to_name_search: list = []
            else:
                offices_to_name_search = offices
            # v3.41: ONE search per office covers both roles. The grantee rows
            # answer "which deed vested title"; the grantor rows are the
            # seller's own half of the deed-out check and are handed to it
            # below instead of being searched for a second time.
            seller_grantor_rows: dict = {}
            capped_offices: list = []
            for off in offices_to_name_search:
                both_rows, st = await _suffolk_office_rows_both(
                    page, seller_last, seller_first, off, result)
                # Only GT rows may be considered for the vesting deed. A GR
                # DEED row is a conveyance OUT — selecting one as the vesting
                # deed would report the seller's own sale as their title.
                rows = [r for r in both_rows
                        if r.get("party_role") != _SUFFOLK_ROLE_GRANTOR]
                # Hand the grantor half to the deed-out check ONLY for an
                # office that was actually and completely searched. Recording
                # an empty list for an office that failed or capped would tell
                # the check "covered, nothing found" — the precise false
                # clean this whole change is meant to prevent.
                if st in ("ok", "no_results"):
                    seller_grantor_rows[off] = [
                        r for r in both_rows
                        if r.get("party_role") == _SUFFOLK_ROLE_GRANTOR]
                result["offices_searched"].append(
                    {"office": off, "status": st, "rows": len(rows),
                     "mode": "name (Both)",
                     "grantor_rows": len(seller_grantor_rows.get(off, []))})
                if st == "capped":
                    capped_offices.append(off)
                    result["needs_review"].append(
                        f"{off}: the seller's own name could not be fully "
                        "searched — result set exceeded the registry cap")
                if st in ("office_switch_failed", "office_mismatch",
                          "unknown_dialog"):
                    failed_offices.append(off)
                    result["notes"].append(
                        f"CRITICAL: {off!r} was NOT searched "
                        + ("(the Office dropdown never switched)."
                           if st == "office_switch_failed" else
                           "(the registry returned an unrecognised message "
                           "instead of results)."
                           if st == "unknown_dialog" else
                           "(the results grid came back with the OTHER "
                           "office's column layout, so its rows were "
                           "discarded rather than reported as this office's).")
                        + " Any conclusion below covers only the offices that "
                          "were searched.")
                    continue
                if st == "no_results":
                    result["notes"].append(
                        f"{off}: no results for last={seller_last!r} "
                        f"first={seller_first!r} as EITHER party (combined "
                        f"Grantor+Grantee search). NOTE: Incapsula 403s "
                        "render as empty pages — if this repeats, verify the "
                        "browser passed the WAF (see launch note).")
                    continue
                result["notes"].append(
                    f"{off}: grantee search returned {len(rows)} row(s). "
                    + " | ".join(
                        f"[{r['ctl']}] {_suffolk_row_id(r)} {r['deed_type']} "
                        f"{r['recorded_date']} street={r['street']!r}"
                        for r in rows[:25]))
                all_rows.extend(rows)

            if failed_offices and len(failed_offices) == len(offices):
                result["errors"].append(
                    "No office could be searched — the Office dropdown never "
                    "took. Nothing was looked at; this is not deed_not_found.")
                await browser.close()
                return result

            if not all_rows and not street_token:
                # Nothing found and no street to fall back on — this is the
                # end of the road. With a street, the address pass below still
                # gets its turn, so do NOT conclude deed_not_found here.
                result["status"] = "deed_not_found"
                result["notes"].append(
                    "No grantee rows in "
                    f"{' or '.join(o for o in offices if o not in failed_offices)}"
                    ", and no --street to fall back on for an address search."
                    + (" Offices NOT searched: " + ", ".join(failed_offices)
                       if failed_offices else ""))
                await browser.close()
                return result
            if not all_rows and not force_address_search:
                result["notes"].append(
                    "Name search returned no rows in "
                    f"{' or '.join(o for o in offices if o not in failed_offices)}"
                    " — continuing to the address search.")

            _tm.mark("STEP 2 - non-conveyance filter")
            # -----------------------------------------------------------
            # STEP 2 — NON-CONVEYANCE FILTER
            # -----------------------------------------------------------
            deed_rows = [r for r in all_rows
                         if not _is_non_conveyance_instrument(r["deed_type"])]
            if len(deed_rows) < len(all_rows):
                result["notes"].append(
                    f"Filtered {len(all_rows) - len(deed_rows)} non-deed row(s): "
                    f"{sorted({r['deed_type'] for r in all_rows if r not in deed_rows})}.")
            if not deed_rows:
                unknown_types = sorted({
                    r["deed_type"] for r in all_rows
                    if _classify_instrument(r.get("deed_type") or "") == "unknown"
                    and (r.get("deed_type") or "").strip()})
                result["notes"].append(
                    "Name search: all result rows are non-conveyance instruments "
                    "— the vesting deed may be under a different name spelling.")
                if unknown_types:
                    result["notes"].append(
                        f"NOTE: {len(unknown_types)} of the excluded type(s) were "
                        f"UNRECOGNISED rather than known non-conveyances: "
                        f"{unknown_types}. They were NOT reported as the vesting "
                        "deed, but check them by hand before concluding no deed "
                        "exists, and add any real conveyance type to the script "
                        "vocabulary.")

            _tm.mark("STEP 3 - select deed row")
            # -----------------------------------------------------------
            # STEP 3 — STREET-AWARE SELECTION ACROSS BOTH OFFICES
            # -----------------------------------------------------------
            def _filter_by_street(rows: list) -> tuple:
                """
                (candidates, matched) — the street filter, factored out so the
                address pass is judged by exactly the same test as the name
                pass. `matched` is None when there is no street to test.
                """
                if not street_token:
                    return rows, None
                hit = [r for r in rows
                       if street_token in (r["street"] or "").upper()]
                if not hit:
                    return rows, False
                if street_number:
                    numbered = [
                        r for r in hit
                        if (r["street"] or "").upper().startswith(
                            street_number.upper())]
                    if numbered:
                        hit = numbered
                return hit, True

            candidates, street_ok = _filter_by_street(deed_rows)

            # ADDRESS FALLBACK. A name search finding nothing for this parcel
            # is not the end of the search: Suffolk offers a Property search
            # (Street Number + Street Name) in BOTH offices, reached from the
            # Search Criteria menu. It answers the two ways a name search
            # misses — the seller indexed under a different spelling, and the
            # prefix-match trap that returned another person's parcel on the
            # live 2026-08-18 run.
            if street_token and street_ok is not True:
                result["notes"].append(
                    "Name search produced no deed row on "
                    f"{street_token!r} — falling back to an ADDRESS (Property) "
                    f"search for {street_number or '(no number)'} "
                    f"{street_token} across {', '.join(offices)}.")
                addr_rows: list = []
                for off in offices:
                    try:
                        got, st_a = await _suffolk_office_rows_by_address(
                            page, off, result, street_number, street_token)
                    except Exception as e:
                        result["notes"].append(
                            f"Address search on {off!r} failed (non-fatal): "
                            f"{type(e).__name__}: {e}")
                        continue
                    result["offices_searched"].append(
                        {"office": off, "status": st_a, "rows": len(got),
                         "mode": "address"})
                    if st_a == "ok":
                        addr_rows.extend(got)
                    elif st_a in ("office_switch_failed", "office_mismatch"):
                        result["notes"].append(
                            f"CRITICAL: the address search could not be run on "
                            f"{off!r} ({st_a}) — that index was NOT covered by "
                            "the fallback either.")
                addr_deeds = [r for r in addr_rows
                              if not _is_non_conveyance_instrument(r["deed_type"])]
                addr_cands, addr_ok = _filter_by_street(addr_deeds)
                if addr_ok:
                    result["found_via_address_search"] = True
                    result["notes"].append(
                        f"Address search returned {len(addr_rows)} row(s), "
                        f"{len(addr_deeds)} conveyance(s), {len(addr_cands)} on "
                        "the subject street. Selecting from these instead of the "
                        "name-search rows. VERIFY the grantee on the deed image "
                        "matches the seller — an address search is not "
                        "name-verified.")
                    deed_rows, candidates, street_ok = addr_deeds, addr_cands, True
                else:
                    result["notes"].append(
                        "Address search found no conveyance on the subject street "
                        "either" + (" (it returned rows, but none were deeds on "
                                    "that street)." if addr_rows else " (no rows)."))

            if not deed_rows:
                result["status"] = "deed_not_found"
                result["notes"].append(
                    "No conveyance found by name or by address in "
                    f"{', '.join(offices)}. Registered Land also offers a "
                    "Certificate Search this workflow does not yet use; for an "
                    "older parcel the vesting deed may predate the electronic "
                    "index entirely.")
                await browser.close()
                return result

            if street_token and street_ok:
                result["street_match"] = "matched"
            elif street_token:
                # No row mentions the subject street, and the address search
                # did not rescue it. Selecting "the most recent anyway" is how
                # a run for 15 Larkspur Road came back with a 52 Bayard St deed
                # at exit 0 (live 2026-08-18). The deed images are still
                # fetched — they are evidence — but the run is marked as
                # carrying wrong-parcel risk and must not be read as an answer.
                result["street_match"] = "no_match"
                result["wrong_parcel_risk"] = True
                result["needs_review"].append(
                    f"No deed row's Street # matched {street_token!r}")
                result["notes"].append(
                    f"CRITICAL: NO deed row's street matched {street_token!r}, "
                    "by name search OR by address search. The rows found were: "
                    + " | ".join(
                        f"{_suffolk_row_id(r)} {r['deed_type']} "
                        f"{r['recorded_date']} {r['street']!r}"
                        for r in deed_rows[:15])
                    + ". The most recent row was selected so its images could "
                    "be captured, but there is NO evidence it is the subject "
                    "parcel — treat this as wrong-parcel risk, not as the "
                    "vesting deed. Common causes: the seller is indexed under "
                    "a different name spelling, the street is spelled "
                    "differently in the index, or the deed predates the "
                    "indexed street data.")

            # A parcel lives in ONE system. Street-matching candidates in both
            # offices means the street filter is not discriminating (a common
            # street name, or two parcels) — say so rather than pick silently.
            hit_offices = {r["office"] for r in candidates}
            if len(hit_offices) > 1:
                result["notes"].append(
                    "NEEDS REVIEW: candidate deeds matched in BOTH Recorded Land "
                    "and Registered Land. A parcel is registered in one system or "
                    "the other, so at most one of these is the subject parcel's "
                    "vesting deed. Candidates: "
                    + " | ".join(f"{_suffolk_row_id(r)} [{r['office']}] "
                                 f"{r['deed_type']} {r['recorded_date']} "
                                 f"{r['street']!r}" for r in candidates))

            candidates = sorted(
                candidates,
                key=lambda r: _parse_deed_date(r["recorded_date"]),
                reverse=True)
            row = candidates[0]
            sel_office = row["office"]
            sel_cols, sel_anchor = _suffolk_office_cols(sel_office)
            is_lc = row["land_court"]

            result["office_of_record"] = sel_office
            result["land_court"] = is_lc
            result["book"] = (row["book"] or None) if not is_lc else None
            result["page"] = (row["page"] or None) if not is_lc else None
            result["document_number"] = row["doc_number"] or None
            result["recorded_date"] = row["recorded_date"]
            result["deed_type"] = row["deed_type"]
            result["deed_property_address"] = row["street"]
            result["notes"].append(
                f"Selected row: {row['deed_type']} {_suffolk_row_id(row)} "
                f"[{sel_office}] {row['recorded_date']} | Name: {row['name']} | "
                f"Street: {row['street']} | Descr: {row['descr']}")

            if row.get("via_address"):
                result["needs_review"].append(
                    "Selected by ADDRESS search — grantee not verified against "
                    f"the seller name {seller_last} {seller_first}".strip())
                result["notes"].append(
                    "NOTE: this instrument was selected by ADDRESS, because the "
                    "name search found no deed on this street. The address "
                    "index does not carry a party name, so nothing here "
                    "confirms the grantee is the named seller — check the "
                    "grantees below (read off the detail panel) and the deed "
                    "image before relying on it.")

            pfx = _suffolk_prefix_name_warning(row["name"], seller_first)
            if pfx:
                result["wrong_parcel_risk"] = True
                result["needs_review"].append(
                    f"Indexed name {row['name']!r} is a prefix match only")
                result["notes"].append(pfx)

            if result["results_truncated_at_cap"]:
                result["notes"].append(
                    "CRITICAL: a result set hit the 1000-row server-side cap, "
                    "which is applied BEFORE the date sort — the selected deed "
                    "may not be the most recent. Narrow the search before "
                    "relying on this result.")

            _tm.mark("STEP 4 - detail panel")
            # -----------------------------------------------------------
            # STEP 4 — DETAIL PANEL
            #
            # The grid on screen belongs to the LAST office searched and is
            # parked on the last pager page, so the row is relocated by
            # instrument identity before its link is clicked. Clicking the
            # stale ctl would open a different deed.
            # -----------------------------------------------------------
            async def _research():
                await _suffolk_search(page, seller_last, seller_first, "I",
                                      sel_office)
                await _has_results(page, timeout_ms=40000)

            # The relocation target must have the SAME KEY SHAPE as the raw
            # rows the reader produces for this office. _same_instrument
            # compares with .get(), and a normalised row carries book='' while
            # a raw Land Court row has no 'book' key at all — None != '', so
            # every Land Court relocation failed and the run reported the
            # right deed with no panel and no images.
            if row.get("via_address"):
                # Found by address: replay the ADDRESS search and match on the
                # property key. Replaying the name search here would look for
                # a row that search never returned — which is the whole reason
                # the address fallback ran.
                panel_anchor = "Type Desc"
                live_ctl = await _suffolk_relocate_prop_row(
                    page, sel_office, result, row, street_number, street_token)
            else:
                # The relocation target must have the SAME KEY SHAPE as the raw
                # rows the reader produces for this office. _same_instrument
                # compares with .get(), and a normalised row carries book=''
                # while a raw Land Court row has no 'book' key at all —
                # None != '', so every Land Court relocation failed and the run
                # reported the right deed with no panel and no images.
                panel_anchor = sel_anchor
                reloc_target = {k: row.get(k, "") for k in sel_cols}
                reloc_target["name"] = row["name"]
                await _research()
                live_ctl = await _plymouth_ensure_row_visible(
                    page, reloc_target, _research, cols=sel_cols,
                    anchor=sel_anchor)
            detail_pages = ""
            if not live_ctl:
                result["notes"].append(
                    "WARNING: the selected row could not be relocated in the "
                    "replayed grid — detail panel and images were NOT opened for "
                    "a confirmed row. Verify by hand.")
            else:
                panel_opened = await _open_detail_panel(
                    page, ctl=live_ctl,
                    expected_book="" if is_lc else (row["book"] or ""),
                    anchor_col=panel_anchor)
                if panel_opened:
                    parties = await _read_detail_panel(page)   # parties + references
                    det = await _suffolk_read_detail(page)     # header + blocks
                    result["grantors"] = parties["grantors"]
                    result["grantees"] = parties["grantees"]
                    result["document_number"] = (det["doc_number"]
                                                 or result["document_number"])
                    result["consideration"] = det["consideration"] or None
                    detail_pages = det["num_pages"]
                    # v3.50 — the complete References list, every pager page.
                    result["detail_references"] = parties.get("references") or []
                    result["detail_references_expected"] = parties.get("references_expected")
                    result["detail_references_complete"] = parties.get("references_complete")
                    if parties.get("references_note"):
                        result["notes"].append(parties["references_note"])
                    result["notes"].append(
                        f"Detail panel: Doc#{det['doc_number']} "
                        f"pages={det['num_pages']} "
                        f"consideration={det['consideration']} "
                        f"status={det['doc_status']} | "
                        f"Grantors: {parties['grantors']} | "
                        f"Grantees: {parties['grantees']}")
                    if det["property_lines"]:
                        result["notes"].append(
                            "Detail panel property block: "
                            + " | ".join(det["property_lines"][:6]))

                    if is_lc:
                        # Land Court citation. The panel's Book/Page is the
                        # LAND COURT REGISTRATION book/page — kept in its own
                        # field so nothing can emit it as a Recorded Land
                        # Book/Page citation.
                        result["land_court_registration_book_page"] = (
                            det["book_page"] or None)
                        certs = _suffolk_parse_certificates(
                            row["descr"], " ".join(det["property_lines"]))
                        result["certificate_references"] = det["certificate_refs"]
                        result["certificate_in_index_description"] = (
                            certs[0] if certs else None)
                        # The certificate the deed is NOTED ON — the one a
                        # derivation clause must cite. Verified against the
                        # cover sheet's "Noted on Certificate" line.
                        result["certificate_of_title"] = (
                            det["certificate_refs"][0]
                            if det["certificate_refs"] else None)
                        result["notes"].append(
                            "REGISTERED LAND (Land Court): cite this deed as "
                            f"Document No. {result['document_number'] or '___'}, "
                            "noted on Certificate of Title No. "
                            f"{result['certificate_of_title'] or '___'} "
                            "(from the detail panel's Certificate/Encumbrance "
                            "reference, which matches the cover sheet's 'Noted "
                            "on Certificate' line). The index description also "
                            f"names certificate {certs[0] if certs else 'NONE'} "
                            "— that is the certificate the land is DESCRIBED "
                            "on (the one conveyed out of), not this deed's "
                            "certificate; do not cite it as the seller's. The "
                            f"panel's Book/Page ({det['book_page'] or 'n/a'}) "
                            "is the Land Court registration book/page, NOT a "
                            "Recorded Land citation. Confirm both against the "
                            "deed image before use.")
                    if result["detail_references"]:
                        result["cross_references"] = _normalize_cross_references(
                            result["detail_references"], "Suffolk detail panel")
                        xnote = _cross_reference_note(result["cross_references"])
                        if xnote:
                            result["notes"].append(xnote)
                else:
                    result["grantees"] = [row["name"]] if row["name"] else []
                    result["notes"].append(
                        "Detail panel did not open — party/doc#/consideration "
                        "data limited to the results row.")

            _tm.mark("STEP 5 - page images")
            # -----------------------------------------------------------
            # STEP 5 — VIEW IMAGES → hi-res download of every page
            # -----------------------------------------------------------
            if live_ctl:
                try:
                    vi_tab = await page.query_selector(
                        'a[href*="TabController1$ImageViewertabitem"]')
                    if vi_tab:
                        await vi_tab.click()
                        await page.wait_for_timeout(1500)
                except Exception as e:
                    result["notes"].append(
                        f"View Images tab click error (non-fatal): {e}")

                await page.goto(SUFFOLK_VIEWER, wait_until="domcontentloaded",
                                timeout=30000)
                try:
                    await page.wait_for_function(_MSOUTH_IMG_READY_JS, timeout=45000)
                except Exception:
                    result["errors"].append(
                        "Image viewer did not load a document image.")
                    await browser.close()
                    return result

                total_pages = await _parse_page_count(page)
                result["total_pages_in_viewer"] = total_pages
                if detail_pages and str(total_pages) != str(detail_pages).strip():
                    result["notes"].append(
                        f"NOTE: viewer page count ({total_pages}) differs from "
                        f"detail panel # of Pgs. ({detail_pages}) — verify all "
                        "pages captured.")

                for page_num in range(1, total_pages + 1):
                    if page_num > 1:
                        prev_src = await page.evaluate(
                            "() => document.querySelector('#ImageViewer1_docImage').src")
                        try:
                            await page.click("#ImageViewer1_BtnNext")
                            await page.wait_for_function(
                                "(prev) => { const i = document.querySelector("
                                "'#ImageViewer1_docImage');"
                                " return !!(i && i.src && i.src !== prev &&"
                                " !i.src.includes('loading') && i.naturalWidth > 100); }",
                                arg=prev_src, timeout=45000)
                        except Exception as e:
                            result["notes"].append(
                                f"Page {page_num} navigation error (stopping): {e}")
                            break
                    p_path = output_folder / f"{base_name} - deed_p{page_num}.jpg"
                    method = await _msouth_download_viewer_image(page, p_path)
                    if method != "failed":
                        result["files"].append(str(p_path))
                        result["notes"].append(
                            f"Page {page_num} saved ({method}): {p_path.name}")
                    else:
                        result["errors"].append(
                            f"Page {page_num} download failed.")

            # v3.54 (item 57) — the page images are final here and the grantor
            # check below reads only index data, so hand the images to the caller
            # now: main() starts the extraction API call on a worker thread and
            # joins it after this runner returns.
            if on_images_ready is not None and result["files"]:
                try:
                    on_images_ready(result)
                except Exception as e:
                    result["notes"].append(
                        f"Early extraction not started (non-fatal): {e}")

            _tm.mark("STEP 6 - grantor check")
            # -----------------------------------------------------------
            # STEP 6 — GRANTOR CHECK (seller + all deed grantees, both offices)
            #
            # Windowed from the acquisition date less a small lookback, the
            # same narrowing the ALIS/Plymouth paths use. An unknown
            # acquisition date yields NO window (search all years) rather than
            # a window starting at zero.
            # -----------------------------------------------------------
            result["notes"].append(
                "Grantor check is NOT date-windowed on Suffolk: the basic "
                "form's Recorded Date boxes are not honoured (see module note), "
                "so every year is searched. Every hit below is therefore "
                "reported regardless of date — including instruments that "
                "predate the seller's acquisition.")

            selected_key = _suffolk_row_key(row)
            names_to_check: dict = {}
            seller_key = (seller_last.upper().strip(), seller_first.upper().strip())
            names_to_check[seller_key] = (
                f"named seller ({seller_last} {seller_first})".strip())
            for grantee_display in result.get("grantees", []):
                key = _msouth_split_name(grantee_display)
                # The first-name box is a PREFIX match, so a co-owner queried
                # with a full multi-token first name ('ANNA MARIE') can never
                # reach an instrument indexed under the bare 'ANNA'. Truncate
                # to the first token — a strict superset under prefix matching.
                first_tok = key[1].split()[0] if key[1] else ""
                bkey = (key[0], first_tok)
                if key[0] and bkey != seller_key and bkey not in names_to_check:
                    names_to_check[bkey] = (
                        f"{grantee_display} (co-owner from detail panel)")

            search_log: list = []
            all_grantor_rows: list = []
            seen: set = set()
            g_page = None
            try:
                g_page = await context.new_page()
            except Exception as e:
                for label in names_to_check.values():
                    search_log.append({
                        "name": "", "label": label, "rows_returned": None,
                        "rows_new": 0,
                        "status": f"ERROR — could not open search page: {e}"})
                    result["grantor_check"].setdefault(
                        "incomplete_searches", []).append(label)
            if g_page is not None:
                for (g_last, g_first), label in names_to_check.items():
                    disp = f"{g_last} {g_first}".strip()
                    entry = {"name": disp, "label": label, "rows_returned": None,
                             "rows_new": 0, "status": "ok"}
                    try:
                        rows_g, off_status = await _suffolk_grantor_check(
                            g_page, g_last, g_first, selected_key, label,
                            offices, result,
                            prefetched=(seller_grantor_rows
                                        if (g_last, g_first) == seller_key
                                        else None))
                        entry["offices"] = off_status
                        bad = [o for o, s in off_status.items()
                               if not (str(s).startswith("ok")
                                       or s == "no_results")]
                        entry["rows_returned"] = len(rows_g)
                        if bad:
                            entry["status"] = (
                                "ERROR — office(s) not searched: "
                                + "; ".join(f"{o}: {off_status[o]}" for o in bad))
                            result["grantor_check"].setdefault(
                                "incomplete_searches", []).append(
                                    f"{label} [{', '.join(bad)}]")
                        for r in rows_g:
                            rkey = _suffolk_row_key(r)
                            if rkey in seen:
                                continue
                            seen.add(rkey)
                            entry["rows_new"] += 1
                            all_grantor_rows.append(r)
                            note = _significance_note(
                                _suffolk_row_id(r), r["deed_type"],
                                r["recorded_date"], r["office"], r["descr"])
                            result["notes"].append(
                                f"Grantor check hit [{label}]: "
                                f"{_suffolk_row_id(r)} [{r['office']}] "
                                f"{r['deed_type']} {r['recorded_date']} | "
                                f"{r['street']} {r['descr']}".rstrip())
                            if note:
                                result["notes"].append(note)
                                result["grantor_check"]["needs_review"].append(
                                    f"{_suffolk_row_id(r)} [{r['office']}] "
                                    f"{r['deed_type']} {r['recorded_date']}")
                    except Exception as e:
                        entry["status"] = f"ERROR — {type(e).__name__}: {e}"
                        result["grantor_check"].setdefault(
                            "incomplete_searches", []).append(label)
                    search_log.append(entry)
                try:
                    await g_page.close()
                except Exception:
                    pass

            _plymouth_record_searches(result, search_log)
            result["grantor_check"]["has_subsequent_deed"] = bool(all_grantor_rows)
            result["grantor_check"]["deeds"] = [
                f"{_suffolk_row_id(r)} [{r['office']}] {r['deed_type']} "
                f"{r['recorded_date']} | {r['street']} {r['descr']} "
                f"| [found via: {r['searched_name']}]".replace("  ", " ")
                for r in all_grantor_rows]
            errored = [s for s in search_log
                       if str(s.get("status", "")).startswith("ERROR")]
            if errored:
                result["grantor_check"]["summary"] = "incomplete"
                result["notes"].append(
                    f"CRITICAL: grantor check is INCOMPLETE — {len(errored)} of "
                    f"{len(search_log)} search(es) did not fully run "
                    f"({', '.join(s['label'] for s in errored)}). The hits above "
                    "are from the searches that completed. NEVER report clean "
                    "title from this run; re-run the failed name(s) before "
                    "concluding anything.")
            elif all_grantor_rows:
                result["grantor_check"]["summary"] = "hits_found"
                result["notes"].append(
                    f"Grantor check: {len(all_grantor_rows)} instrument(s) found "
                    "— Claude must assess title flags. (Neither Suffolk grid has "
                    "a Reverse Party column: open the detail panel or the image "
                    "for the counterparty of any DEED-type hit.)")
            else:
                result["grantor_check"]["summary"] = "no_hits"
                result["notes"].append(
                    f"Grantor check: no subsequent instruments found (all "
                    f"{len(search_log)} search(es) completed across "
                    f"{', '.join(offices)}).")

        except Exception as e:
            result["errors"].append(f"Main workflow failed: {e}")
            await browser.close()
            return result
        finally:
            _tm.finish(result)
            try:
                await page.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

    result["status"] = "success" if result["files"] else "error"
    if not result["files"] and not result["errors"]:
        result["errors"].append("No deed images downloaded.")

    # A run can download three perfectly good images OF THE WRONG PARCEL and
    # still be status=success at exit 0 — the recurring failure in this
    # project's history. The status is left alone (files really were fetched,
    # and the caller's exit-code contract is shared with every other
    # registry), but the warning is lifted to notes[0] so it cannot be read
    # past. Verified live: a search for last='X' first='Y' prefix-matched
    # 'XIANG YANQIAO' and returned a Broadway unit deed at exit 0.
    if result.get("wrong_parcel_risk"):
        result["notes"].insert(0, (
            "*** DO NOT REPORT THIS AS THE VESTING DEED WITHOUT CHECKING IT. "
            "wrong_parcel_risk is set: "
            + "; ".join(result.get("needs_review") or ["unspecified"])
            + f". The instrument selected was {result.get('deed_type')} "
            f"at {result.get('deed_property_address') or 'an unstated address'}"
            ", chosen so its images could be captured — not because it was "
            "matched to the subject property. ***"))
    return result


async def run_stub(registry: str) -> dict:
    return {
        "status": "error",
        "error_message": (
            f"{registry.title()} County not yet implemented in Playwright script. "
            "Use the standard fetch-download + Read tool workflow."
        )
    }


# ---------------------------------------------------------------------------
# Browntech ALIS (shared: Barnstable, Norfolk)
# ---------------------------------------------------------------------------
# The two registries run identical ALIS software with the same form fields,
# result table structure, image-list page format, and PDF URL pattern. The
# only differences are the base URL (domain) and town code conventions.
# All helpers below take `base_url` as a parameter so they serve both.

# ---------------------------------------------------------------------------
# v3.43 (item 24) — ALIS NAME-FIELD LENGTH CAP
#
# The registry's own form hard-caps the name inputs. Read off the live form
# HTML on norfolkresearch.org, 2026-08-24:
#
#     Recorded Land   W9SNM / W9GNM   maxlength=30
#     Land Court      W9SN8 / W9GN8   maxlength=28
#
# An OVER-LENGTH name is NOT rejected. It degenerates SILENTLY, and in two
# different ways depending on the town scope — both measured live with the
# 45-character entity name (a nonprofit corporation). Entity names of that
# length are routine; personal names rarely reach the cap, which is exactly
# why this stayed latent for so long:
#
#   town=<a town>  -> ZERO rows. The v3.20 cap-retry consumed that as
#                     "nothing indexed" and reported "0 row(s), COMPLETE ...
#                     the subject-parcel check is complete" — a FALSE CLEAN
#                     from a search that structurally could not return a row.
#   town=*ALL      -> ~149 rows whose NAME CELL IS BLANK. They passed the
#                     conveyance filter and became phantom grantor hits
#                     attributed to the seller (deeds belonging to unrelated
#                     parties in Quincy, Wrentham, Stoughton, Brookline).
#
# On one live run it did both at once: 12 strangers' instruments reported as
# the seller's, and all 3 genuine subject-parcel instruments missed, at exit 0.
#
# Clipping is safe AND correct: both indexes are PREFIX-matched, so a shorter
# name returns a strict SUPERSET of what the full name would have matched.
# Entity names routinely exceed these caps; personal names rarely do, which
# is why this stayed latent.
_ALIS_NAME_MAXLEN_RECORDED   = 30
_ALIS_NAME_MAXLEN_LAND_COURT = 28


def _alis_name_limit(land_court: bool) -> int:
    """Characters the ALIS name inputs accept for this section."""
    return (_ALIS_NAME_MAXLEN_LAND_COURT if land_court
            else _ALIS_NAME_MAXLEN_RECORDED)


def _alis_truncate_name(name: str, land_court: bool):
    """
    Clip `name` to the registry's field limit.

    Returns (clipped, was_clipped). Trailing whitespace is stripped after
    clipping so a query never ends mid-space (the index is matched on the
    literal string, and a trailing space can suppress otherwise-valid hits).
    """
    limit = _alis_name_limit(land_court)
    s = name or ""
    if len(s) <= limit:
        return s, False
    return s[:limit].rstrip(), True


class AlisDegenerateResultError(RuntimeError):
    """
    The registry returned a result set that is not an answer to the query
    we asked — the signature of an over-length or malformed name field.

    Raised rather than returned so callers record the search as ERROR and it
    lands in `incomplete_searches`. Returning [] would be actively dangerous:
    "no rows" is exactly what the false-clean bug looked like.
    """


def _alis_result_set_is_degenerate(rows: list, queried_last: str) -> str:
    """
    Detect the degenerate result set described above. Returns a reason string
    when the rows cannot be an answer to `queried_last`, else "".

    Signature: a NON-empty surname was queried, rows came back, and most of
    them carry NO name at all. A legitimate ALIS row always names its party.
    Deliberately conservative — it needs a majority, so an odd unparsed row
    never invalidates a good search.
    """
    if not queried_last or not rows:
        return ""
    blank = sum(1 for r in rows if not (r.get("name") or "").strip())
    if blank > len(rows) / 2:
        return (f"{blank} of {len(rows)} returned rows have a BLANK name cell "
                f"after querying '{queried_last}' — the registry did not "
                f"filter on the name (over-length or malformed name field)")
    return ""


def _alis_url(
    base_url: str,
    last: str,
    first: str,
    party: str,
    town: str,
    land_court: bool = False,
    doc_type: str = "*ALL",
    date_from: str = "",
    per_page: int | None = None,
) -> str:
    """
    Build a direct ALIS search results URL.

    Parameters:
      base_url    : registry domain (BARNSTABLE_BASE or NORFOLK_BASE)
      last, first : seller name components — URL-encoded with quote(x, safe='')
      party       : "E" = Grantee, "R" = Grantor
      town        : ALIS town code (e.g. BARN, FALM, BRAI, QUIN, WEYM, *ALL).
                    No default — caller supplies the correct value for the
                    registry (Barnstable: BARN covers all villages; Norfolk:
                    each municipality has its own code).
      land_court  : if True, build a Land Court search (WSIQTP=LC01LP,
                    name fields W9SN8/W9GN8, results handler WW401L00);
                    else a Recorded Land search (WSIQTP=LR01LP, name fields
                    W9SNM/W9GNM, results handler WW401R00).
      doc_type    : "*DD" for deed-group pre-filter, "*LN" for the lien
                    document group, "*ALL" for everything
      date_from   : v3.29 — server-side start date, MMDDYYYY, "" for none.
                    The form labels these "Date Range (optional) -mmddyyyy"
                    and they are INDEPENDENT of the W9INQ year-index radio,
                    which stays AY (all years). Verified live 2026-08-13 on
                    Barnstable: a surname-only grantor search returned page-1
                    rows spanning 1884–2022 unfiltered and 2020-10-07 onward
                    with W9FDTA=01012020, so the server really filters.
      per_page    : results per page (WSSRPP — site offers 10/20/30).
                    None omits the param (site default 10). The HTTP engine
                    passes 30 to cut pagination round-trips.

    URL pattern confirmed from live DOM runs on both registries.

    NOTE: Recorded Land and Land Court use DIFFERENT name-index field names.
    A Land Court search built with the Recorded Land names (W9SNM/W9GNM)
    silently returns zero results — the LC form ignores the unknown params
    rather than erroring. Always switch field names on land_court.
    """
    wsiqtp      = "LC01LP"  if land_court else "LR01LP"
    last_field  = "W9SN8"   if land_court else "W9SNM"
    first_field = "W9GN8"   if land_court else "W9GNM"
    wshtnm      = "WW401L00" if land_court else "WW401R00"
    # v3.43 (item 24) — clip to the registry's field limit HERE, in the one
    # place every ALIS query is built, so no caller can bypass it. An
    # over-length name returns garbage or nothing, never an error.
    last, _last_clipped   = _alis_truncate_name(last,  land_court)
    first, _first_clipped = _alis_truncate_name(first, land_court)
    last_enc  = quote(last,  safe="")
    first_enc = quote(first, safe="")
    doc_enc   = quote(doc_type, safe="*")   # preserve * so *DD and *ALL are not percent-encoded
    url = (
        f"{base_url}/ALIS/WW400R.HTM?"
        f"{last_field}={last_enc}&{first_field}={first_enc}&W9IXTP={party}"
        f"&W9ABR={doc_enc}&W9TOWN={town}&W9INQ=AY"
        f"&W9FDTA={quote(date_from, safe='')}&W9TDTA=&AYVAL=%2B1742&CYVAL=2015"
        f"&WSHTNM={wshtnm}&WSIQTP={wsiqtp}&WSKYCD=N&WSWVER=2"
    )
    if per_page:
        url += f"&WSSRPP={per_page}"
    return url


async def _alis_parse_results(page: Page) -> list:
    """
    Parse the ALIS search results table using page.evaluate().
    Returns a list of row dicts. Each result row is identified by a
    "View Document Image" link whose href contains WSIQTP=LR01I (recorded land)
    or WSIQTP=LC01I (land court).

    Recorded Land and Land Court use the same column layout EXCEPT:
      column 1 — Recorded Land: Reverse Party | Land Court: Certificate #
      column 6 — Recorded Land: "Book-Page"   | Land Court: "Doc#-Sequence"
    Each row dict carries a `land_court` bool and BOTH sets of fields, with
    the inapplicable ones left as empty strings:
      Recorded Land row → book, page populated;  certificate, document_number ''
      Land Court row    → certificate, document_number populated; book, page ''
    `reverse_party` is populated for Recorded Land only — the Land Court index
    has no opposite-party column, so the grantor must be read from the deed PDF.

    Returns [] if page.evaluate() returns None or raises.
    """
    js = r"""
() => {
    const rows = [];
    const imgLinks = Array.from(
        document.querySelectorAll('a[href*="WSIQTP=LR01I"], a[href*="WSIQTP=LC01I"]')
    );
    for (const link of imgLinks) {
        const href = link.getAttribute('href');
        const mCtln = href.match(/W9CTLN=(\d+)/);
        const mYear = href.match(/W9RCCY=(\d+)/);
        const mMon  = href.match(/W9RCMM=(\d+)/);
        const mDay  = href.match(/W9RCDD=(\d+)/);

        // Land Court vs Recorded Land: the image-link WSIQTP identifies which
        // result table this row belongs to. The two tables share a column
        // layout except columns 1 and 6 (see below).
        const isLC = /WSIQTP=LC01I/.test(href);

        const tr = link.closest('tr');
        if (!tr) continue;
        const tds = Array.from(tr.querySelectorAll('td'));
        const texts = tds.map(td => td.innerText.replace(/\s+/g, ' ').trim());
        const nameLink = tr.querySelector('a[href*="WSIQTP=LR01L"], a[href*="WSIQTP=LC01L"]');

        // Column 1 — Recorded Land: Reverse Party | Land Court: Certificate #.
        const col1 = texts[1] || '';
        // Column 6 — Recorded Land: "BOOK-PAGE" | Land Court: "DOCNUM-SEQUENCE".
        const col6 = texts[6] || '';
        const col6Match = col6.match(/(\d+)[-\/](\d+)/);

        let reverse_party = '', certificate = '';
        let book = '', page = '', document_number = '';
        if (isLC) {
            certificate = col1;
            // Doc# is the part before the dash; the trailing "-1" is a
            // sequence suffix, not a page. Fall back to a digits-only col6.
            document_number = col6Match ? col6Match[1]
                              : (/^\d+$/.test(col6) ? col6 : '');
        } else {
            reverse_party = col1;
            book = col6Match ? col6Match[1] : '';
            page = col6Match ? col6Match[2] : '';
        }

        rows.push({
            name:            nameLink ? nameLink.innerText.trim() : (texts[0] || ''),
            reverse_party:   reverse_party,
            certificate:     certificate,
            town:            texts[2] || '',
            date_received:   (mYear && mMon && mDay)
                             ? (mMon[1] + '-' + mDay[1] + '-' + mYear[1])
                             : (texts[3] || ''),
            doc_type:        texts[4] || '',
            doc_desc:        texts[5] || '',
            book_page:       col6,
            book:            book,
            page:            page,
            document_number: document_number,
            land_court:      isLC,
            img_href:        href,
            ctl_num:         mCtln ? mCtln[1] : '',
        });
    }
    return rows;
}
"""
    try:
        result = await page.evaluate(js)
        if result is None:
            return []
        return result
    except Exception:
        return []


def _alis_row_id(row: dict) -> str:
    """
    Human-readable identifier for an ALIS result row, used in notes.
    Land Court → "Doc#NNNN Ctf#NNNN"; Recorded Land → "BkNNNN/PgNNNN".
    """
    if row.get("land_court"):
        return f"Doc#{row.get('document_number') or '?'} Ctf#{row.get('certificate') or '?'}"
    return f"Bk{row.get('book') or '?'}/Pg{row.get('page') or '?'}"


def _alis_select_deed_row(rows: list) -> dict | None:
    """
    Select the best (most recently recorded) deed row from ALIS results.

    Filters out non-deed types using the shared _is_non_conveyance_instrument()
    classifier (v3.4) — covers mortgages, discharges, assignments, releases,
    liens, attachments, plans AND tax-title redemptions, tax takings, municipal
    lien certificates, and easements that the prior bare substring list missed.

    From the filtered pool (falls back to full rows if all excluded), returns
    the row with the highest numeric identifier — book number for Recorded
    Land rows, document number for Land Court rows (Land Court rows have no
    book). Falls back to pool[0] if no identifier parses. Returns None if
    rows is empty.
    """
    if not rows:
        return None

    def is_excluded(row: dict) -> bool:
        return _is_non_conveyance_instrument(row.get("doc_type") or "")

    def sort_key(row: dict) -> int:
        # Recorded Land rows carry `book`; Land Court rows carry
        # `document_number` instead. Use whichever is present.
        val = row.get("book") or row.get("document_number") or ""
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    filtered = [r for r in rows if not is_excluded(r)]
    pool = filtered if filtered else rows

    return max(pool, key=sort_key)


async def _alis_get_pdf_hrefs(page: Page, base_url: str, img_href: str) -> dict:
    """
    Navigate to the Document Image List page and return PDF hrefs.

    Returns a dict:
      {
        "pdf_hrefs":      list[str],  # hrefs to download (primary or fallback)
        "is_fallback":    bool,        # True if primary pattern empty, using
                                       # permissive fallback (any .PDF link)
        "all_pdfs":       list[str],  # every .PDF href found on the page
        "image_list_url": str,         # URL of the Document Image List page
      }

    Strategy:
    1. Navigate to the Document Image List page.
    2. Collect all a[href*="/WwwImg/"] hrefs ending in .PDF (any naming).
    3. Primary path: filter for the individual-page numbered pattern
       /\\d{3,4}\\.PDF$/i (e.g. DUIP0001.PDF, DB3R0001.PDF — multi-page deeds).
       Correctly excludes the combined "All Pg" PDF (e.g. DVT6.PDF).
    4. If primary is non-empty → pdf_hrefs=primary, is_fallback=False.
    5. If primary is empty but all_pdfs is non-empty → pdf_hrefs=all_pdfs,
       is_fallback=True. Handles non-standard short single-file naming
       (e.g. /WwwImg/D1UJ.PDF observed on a 1988 Foxborough deed,
       Bk7906/Pg271) where the entire deed is in one PDF with no
       page-number suffix.
    6. If no PDFs at all → pdf_hrefs=[], is_fallback=False, all_pdfs=[].

    PDF filename prefixes vary by recording batch and registry (Barnstable:
    DX26, DN6D; Norfolk: DUIP, DB3R), so prefix is never hardcoded. The
    fallback handles batches that use entirely non-standard short names.

    On navigation/eval error, returns the empty shape but still includes
    the attempted image_list_url so the caller can surface it to Claude
    for manual recovery.
    """
    if img_href.startswith("/"):
        full_url = base_url + img_href
    else:
        full_url = img_href

    empty = {
        "pdf_hrefs": [],
        "is_fallback": False,
        "all_pdfs": [],
        "image_list_url": full_url,
    }

    try:
        await page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return empty

    js = r"""
() => {
    const links = Array.from(document.querySelectorAll('a[href*="/WwwImg/"]'));
    const pdfs = links
        .map(a => a.getAttribute('href'))
        .filter(h => h && /\.PDF$/i.test(h));
    const numbered = pdfs.filter(h => /\d{3,4}\.PDF$/i.test(h));
    return {numbered: numbered, all: pdfs};
}
"""
    try:
        result = await page.evaluate(js)
        if not result:
            return empty
        numbered = result.get("numbered") or []
        all_pdfs = result.get("all") or []
        if numbered:
            return {
                "pdf_hrefs": numbered,
                "is_fallback": False,
                "all_pdfs": all_pdfs,
                "image_list_url": full_url,
            }
        if all_pdfs:
            return {
                "pdf_hrefs": all_pdfs,
                "is_fallback": True,
                "all_pdfs": all_pdfs,
                "image_list_url": full_url,
            }
        return empty
    except Exception:
        return empty


async def _alis_download_pdfs(
    page: Page,
    base_url: str,
    pdf_hrefs: list,
    base_name: str,
    output_folder: Path,
) -> tuple:
    """
    Download each PDF via Playwright's authenticated request context
    (page.request.get()).

    For each href (index i starting at 1):
      - Build url = base_url + href (if href starts with '/').
      - Fetch via page.request.get(url).
      - If response.ok and content-type contains 'pdf' (or url ends with .pdf):
          write bytes to output_folder / f"{base_name} - deed_p{i}.pdf"
          append str(path) to saved.
      - Else append to errors.

    Returns (saved, errors).
    """
    saved = []
    errors = []

    for i, href in enumerate(pdf_hrefs, start=1):
        url = (base_url + href) if href.startswith("/") else href
        try:
            response = await page.request.get(url)
            ct = response.headers.get("content-type", "").lower()
            if response.ok and ("pdf" in ct or url.lower().endswith(".pdf")):
                out_path = output_folder / f"{base_name} - deed_p{i}.pdf"
                out_path.write_bytes(await response.body())
                saved.append(str(out_path))
            else:
                errors.append(
                    f"Page {i}: HTTP {response.status} or non-PDF content-type ({ct!r}) — {url}"
                )
        except Exception as e:
            errors.append(f"Page {i}: download error — {e} — {url}")

    return saved, errors


async def _alis_grantor_check(
    page: Page,
    base_url: str,
    last: str,
    town: str,
    original_id: str,
    land_court: bool = False,
) -> list:
    """
    Run a Grantor search for the seller's last name with blank first name
    (catches all joint owners and name variants). Navigate to the search URL,
    parse results, and return every row except the acquisition document itself.

    The acquisition document is excluded by document_number on Land Court and
    by book number on Recorded Land — `original_id` must be the matching
    identifier for the section being searched.
    """
    url = _alis_url(base_url, last, "", "R", town=town, land_court=land_court, doc_type="*ALL")
    id_field = "document_number" if land_court else "book"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        rows = await _alis_parse_results(page)
        return [
            r for r in rows
            if r.get(id_field) and r.get(id_field) != original_id
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# ALIS pure-HTTP engine (v3.9) — Norfolk & Barnstable without a browser.
#
# The Browntech ALIS sites are plain server-rendered GETs end to end:
#   search:     WW400R.HTM?...WSIQTP=LR01LP|LC01LP (query-string form)
#   next page:  WW400R.HTM with the results form's hidden fields
#               + WSIQTP=LR01N|LC01N  (what doVarButton2() does in JS)
#   per page:   WSSRPP=10|20|30
#   image list: the row's "View Document Image" href (WSIQTP=LR01I|LC01I)
#   PDFs:       /WwwImg/*.PDF
# All verified live on norfolkresearch.org and search.barnstabledeeds.org
# (2026-07-11). These sync helpers mirror the _alis_* Playwright versions
# row-dict-for-row-dict so downstream consumers are shared.
# ---------------------------------------------------------------------------

_ALIS_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}

# v3.38 — ALIS document-group codes used to restrict a search SERVER-SIDE.
# "*DD" is the deed group (the deed-out question) and "*LN" the lien group
# (the opt-in person-level sweep). Filtering at the registry instead of in
# Python is what makes the deed-out net cheap.
_ALIS_DEED_GROUP = "*DD"
_ALIS_LIEN_GROUP = "*LN"

_ALIS_MAX_PAGES = 5  # pagination cap per search (30 rows/page → 150 rows)

# ---------------------------------------------------------------------------
# v3.29 — SERVER-SIDE DATE WINDOW FOR THE GRANTOR CHECK
#
# Until v3.28 every grantor search pulled the party's COMPLETE index history
# and the pre-acquisition rows were discarded in Python afterwards. On a
# common name that is most of the work: GRANT PETER / 23 Harrowgate Dr returned
# 218 rows back to 1704 to answer a question that concerns 41 of them, and
# on ALIS those wasted pages are what pushed Keegan and Salgado into the
# _ALIS_MAX_PAGES cap and the "grantor check INCOMPLETE" outcome. Both
# platforms filter by recorded date server-side (ALIS W9FDTA; Plymouth
# ACSTextBox_DateFrom on the Advanced panel), so the rows are now never
# fetched. This is a speed fix AND a cap fix.
#
# THE WINDOW DOES NOT START ON THE DEED DATE. Two classes of instrument
# recorded before the vesting deed still matter:
#
#   (a) The acquisition batch itself. The purchase-money mortgage and the
#       homestead normally record the same day, but ordering within a batch
#       is not guaranteed and a batch can straddle a day boundary. Hence
#       _GRANTOR_WINDOW_LOOKBACK_DAYS rather than an exact date.
#   (b) Liens against the PERSON that can reach after-acquired property —
#       tax liens, executions, attachments, bankruptcy. These predate
#       acquisition and can still cloud title, and a date window hides them
#       by construction. They are recovered by a separate LIEN SWEEP that is
#       restricted by document TYPE and left unrestricted in time (ALIS doc
#       group "*LN"; Plymouth _PLYMOUTH_LIEN_DOC_TYPES). Those types are
#       rare, so the sweep is cheap — far cheaper than the full history it
#       replaces.
#
# Net effect: same answer, a fraction of the rows. Anything the window
# excludes is either irrelevant to this parcel or caught by the sweep.
# ---------------------------------------------------------------------------
_GRANTOR_WINDOW_LOOKBACK_DAYS = 7


def _grantor_window_start(acq_date: tuple, lookback_days: int = None) -> tuple:
    """
    v3.29 — the start of the grantor-check date window: the acquisition date
    less a small lookback, as a (Y, M, D) tuple. Returns (0, 0, 0) when the
    acquisition date is unknown, which every caller must treat as "no window"
    (search all years) rather than as a window starting at zero — an unknown
    acquisition date is missing information, not a licence to narrow.
    """
    if not acq_date or acq_date <= (0, 0, 0):
        return (0, 0, 0)
    if lookback_days is None:
        lookback_days = _GRANTOR_WINDOW_LOOKBACK_DAYS
    try:
        d = _dt_date(acq_date[0], acq_date[1], acq_date[2])
    except (ValueError, TypeError, IndexError):
        return (0, 0, 0)
    d -= _dt_timedelta(days=lookback_days)
    return (d.year, d.month, d.day)


def _alis_date_param(window: tuple) -> str:
    """v3.29 — (Y, M, D) → ALIS MMDDYYYY, or '' for no window."""
    if not window or window <= (0, 0, 0):
        return ""
    return f"{window[1]:02d}{window[2]:02d}{window[0]:04d}"

# v3.20 — cap for the town-scoped grantor-check retry. When the county-wide
# pass caps at _ALIS_MAX_PAGES on a common name (Keegan: 150/132/149 rows,
# all truncated), the scoped pass must be allowed to run to completion —
# town-scoping shrank Keegan to 69 and 31 rows, well inside this cap.
_ALIS_RETRY_MAX_PAGES = 20  # 30 rows/page → 600 rows


class AlisRegistryUnavailableError(RuntimeError):
    """
    The registry served its maintenance/outage page instead of real content.
    Distinct from RuntimeError so the engine dispatch can report
    `registry_unavailable` (exit 1) instead of falling back to Playwright —
    the browser would hit the same maintenance page and, worse, parse it as
    zero rows → a false `deed_not_found` (exit 2). Observed live 2026-07-16:
    Barnstable nightly backup window returned a 264-byte HTTP 200 page and
    both engines reported "no deed" for a seller with a recorded deed.
    """


def _alis_registry_unavailable_html(html: str) -> bool:
    """
    True if `html` is an ALIS registry maintenance page rather than a search
    page. Both Barnstable and Norfolk serve the Browntech outage page:
    "The <county> Public Search program is currently unavailable due to
    nightly backup or periodic maintenance" — a tiny HTTP 200 response with
    no results table, indistinguishable from zero results to the row parsers.
    """
    if not html or len(html) > 4096:
        return False
    lowered = html.lower()
    return ("currently unavailable" in lowered
            and ("maintenance" in lowered or "backup" in lowered))


def _alis_http_get(session, url: str, params=None, timeout: int = 30,
                   retries: int = 3):
    """
    GET with retries. Returns the requests Response. Raises RuntimeError
    after the final attempt so callers can trip the Playwright fallback,
    or AlisRegistryUnavailableError if the registry is serving its
    maintenance page (retried like a failure in case the window is closing,
    but never returned to callers as if it were real content).

    v3.23 — a connection-level failure on the FINAL attempt (refused/reset/
    unreachable — requests.ConnectionError, e.g. WinError 10061) also raises
    AlisRegistryUnavailableError. A hard-down registry (observed Norfolk
    2026-08-11/12: TCP refused outright across three runs) means exactly
    what the maintenance page means — retry later, conclude nothing — and a
    Playwright fallback would only hit ERR_CONNECTION_REFUSED on the same
    host. Only the final attempt counts so a transient blip mid-retry that
    resolves into a real HTTP error still reports that error.
    """
    last_err = None
    saw_maintenance = False
    last_was_conn_err = False
    for attempt in range(retries):
        last_was_conn_err = False
        try:
            resp = session.get(url, params=params, headers=_ALIS_HTTP_HEADERS,
                               timeout=timeout)
            if resp.status_code == 200:
                ctype = resp.headers.get("Content-Type", "")
                if ("html" in ctype
                        and _alis_registry_unavailable_html(resp.text)):
                    saw_maintenance = True
                    last_err = "registry maintenance page"
                else:
                    return resp
            else:
                last_err = f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError as e:
            last_was_conn_err = True
            last_err = str(e)
        except Exception as e:
            last_err = str(e)
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    if saw_maintenance:
        raise AlisRegistryUnavailableError(
            f"Registry is offline for maintenance (nightly backup / periodic "
            f"maintenance page served on {retries} attempts). Retry later — "
            f"this is NOT a deed-not-found result. URL: {url}")
    if last_was_conn_err:
        raise AlisRegistryUnavailableError(
            f"Registry is unreachable (connection refused/failed after "
            f"{retries} attempts — hard-down outage, same handling as the "
            f"maintenance window). Retry later — this is NOT a "
            f"deed-not-found result. Last error: {last_err}. URL: {url}")
    raise RuntimeError(f"GET failed after {retries} attempts ({last_err}): {url}")


def _alis_parse_results_html(html: str) -> list:
    """
    BeautifulSoup equivalent of _alis_parse_results() — identical row dicts
    (name, reverse_party, certificate, town, date_received, doc_type,
    doc_desc, book_page, book, page, document_number, land_court, img_href,
    ctl_num), so _alis_select_deed_row/_alis_row_id/_is_non_conveyance_
    instrument work unchanged on either engine's output.
    """
    rows = []
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=re.compile(r"WSIQTP=L[RC]01I")):
        href = link.get("href") or ""
        is_lc = "WSIQTP=LC01I" in href
        m_ctln = re.search(r"W9CTLN=(\d+)", href)
        m_year = re.search(r"W9RCCY=(\d+)", href)
        m_mon  = re.search(r"W9RCMM=(\d+)", href)
        m_day  = re.search(r"W9RCDD=(\d+)", href)

        tr = link.find_parent("tr")
        if tr is None:
            continue
        tds = tr.find_all("td")
        texts = [" ".join(td.get_text(" ", strip=True).split()) for td in tds]
        name_link = tr.find("a", href=re.compile(r"WSIQTP=L[RC]01L"))

        col1 = texts[1] if len(texts) > 1 else ""
        col6 = texts[6] if len(texts) > 6 else ""
        col6_match = re.search(r"(\d+)[-/](\d+)", col6)

        reverse_party = certificate = ""
        book = page = document_number = ""
        if is_lc:
            certificate = col1
            if col6_match:
                document_number = col6_match.group(1)
            elif col6.isdigit():
                document_number = col6
        else:
            reverse_party = col1
            if col6_match:
                book = col6_match.group(1)
                page = col6_match.group(2)

        rows.append({
            "name":            " ".join(name_link.get_text(" ", strip=True).split())
                               if name_link else (texts[0] if texts else ""),
            "reverse_party":   reverse_party,
            "certificate":     certificate,
            "town":            texts[2] if len(texts) > 2 else "",
            "date_received":   (f"{m_mon.group(1)}-{m_day.group(1)}-{m_year.group(1)}"
                                if (m_year and m_mon and m_day)
                                else (texts[3] if len(texts) > 3 else "")),
            "doc_type":        texts[4] if len(texts) > 4 else "",
            "doc_desc":        texts[5] if len(texts) > 5 else "",
            "book_page":       col6,
            "book":            book,
            "page":            page,
            "document_number": document_number,
            "land_court":      is_lc,
            "img_href":        href,
            "ctl_num":         m_ctln.group(1) if m_ctln else "",
        })
    return rows


def _alis_hidden_fields_html(html: str) -> list:
    """
    Hidden inputs of the results page's <form id="search"> as (name, value)
    tuples, order and duplicates preserved (the form legitimately repeats
    W9PG). These carry the pagination cursor (W9NMX = last indexed name on
    the page, W9BK/W9PG/W9CTLN/W9RC*/W9INO/X3XBRRN = last row position).
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="search")
    if form is None:
        return []
    return [
        (inp.get("name"), inp.get("value") or "")
        for inp in form.find_all("input", type="hidden")
        if inp.get("name")
    ]


def _alis_row_identity(row: dict) -> tuple:
    """Full row identity (index name included) for pagination dedupe."""
    return (row.get("land_court"), row.get("name"), row.get("ctl_num"),
            row.get("book"), row.get("page"), row.get("document_number"),
            row.get("date_received"))


def _alis_instrument_id(row: dict) -> tuple:
    """
    Instrument identity — the same deed indexed under two grantee names
    (e.g. husband + wife rows) collapses to one instrument.
    """
    if row.get("land_court"):
        return ("LC", row.get("document_number") or row.get("ctl_num"))
    return ("RL", _norm_num(row.get("book")), _norm_num(row.get("page")))


def _norm_num(val) -> str:
    """Normalize a book/page number for comparison ('037820' == '37820')."""
    s = str(val or "").strip()
    return str(int(s)) if s.isdigit() else s


def _alis_search_http(
    session,
    base_url: str,
    last: str,
    first: str,
    party: str,
    town: str,
    land_court: bool = False,
    doc_type: str = "*ALL",
    date_from: str = "",
    max_pages: int = _ALIS_MAX_PAGES,
    notes: list = None,
    meta: dict = None,
) -> list:
    """
    Run an ALIS name search over HTTP and return ALL result rows across
    pagination (up to max_pages of 30). The results page renders a "Next"
    link unconditionally, so termination is: a short page (< 10 rows —
    ALIS's smallest page size), a page with no new rows, or the cap.
    Appends a truncation warning to `notes` if the cap is hit while rows
    are still coming. v3.20: when `meta` is passed, meta["truncated"] is
    set so callers can ACT on a capped search (the note alone let the
    Keegan grantor check report a truncated set as its final answer).
    """
    # v3.43 (item 24) — clip before searching and SAY SO. _alis_url() clips
    # too (belt and braces), but only here do we have `notes`/`meta` to
    # record that the query was widened, so a larger-than-expected result
    # set is explained rather than surprising.
    last, _last_clipped   = _alis_truncate_name(last,  land_court)
    first, _first_clipped = _alis_truncate_name(first, land_court)
    if (_last_clipped or _first_clipped) and notes is not None:
        notes.append(
            f"NOTE: name clipped to the ALIS field limit "
            f"({_alis_name_limit(land_court)} chars, "
            f"{'Land Court' if land_court else 'Recorded Land'}) — searched "
            f"'{last}', '{first}'. The index is PREFIX-matched, so this is a "
            f"SUPERSET of the full name: no hit is lost, but same-prefix "
            f"strangers may appear. Verify the party name on any hit."
        )
    if meta is not None and (_last_clipped or _first_clipped):
        meta["name_clipped"] = True
        meta["name_searched"] = (last, first)

    url = _alis_url(base_url, last, first, party, town=town,
                    land_court=land_court, doc_type=doc_type,
                    date_from=date_from, per_page=30)
    resp = _alis_http_get(session, url)
    html = resp.text
    new_rows = _alis_parse_results_html(html)

    # v3.43 (item 24) — refuse a result set that is not an answer to our
    # query. Raising (not returning []) is the point: callers log an ERROR
    # and the name lands in `incomplete_searches`, whereas an empty return
    # is indistinguishable from "nothing indexed" — the false clean itself.
    _degen = _alis_result_set_is_degenerate(new_rows, last)
    if _degen:
        raise AlisDegenerateResultError(
            f"ALIS returned a result set that does not answer the query: "
            f"{_degen}. Treat this name as NOT searched."
        )

    all_rows = list(new_rows)
    seen = {_alis_row_identity(r) for r in new_rows}
    next_control = "LC01N" if land_court else "LR01N"

    pages = 1
    while len(new_rows) >= 10 and pages < max_pages:
        fields = _alis_hidden_fields_html(html)
        if not fields:
            break
        # WSSRPP is not among the form's hidden fields — without re-sending
        # it, continuation pages revert to the 10-row default.
        params = [(n, v) for n, v in fields if n not in ("WSIQTP", "WSSRPP")]
        params.append(("WSIQTP", next_control))
        params.append(("WSSRPP", "30"))
        resp = _alis_http_get(session, f"{base_url}/ALIS/WW400R.HTM", params=params)
        html = resp.text
        page_rows = _alis_parse_results_html(html)
        new_rows = [r for r in page_rows if _alis_row_identity(r) not in seen]
        if not new_rows:
            break
        seen.update(_alis_row_identity(r) for r in new_rows)
        all_rows.extend(new_rows)
        pages += 1

    truncated = pages >= max_pages and len(new_rows) >= 10
    if meta is not None:
        meta["truncated"] = truncated
        meta["pages_walked"] = pages
    if truncated and notes is not None:
        notes.append(
            f"WARNING: pagination cap hit ({max_pages} pages / {len(all_rows)} rows) "
            f"on {'Land Court' if land_court else 'Recorded Land'} "
            f"{'grantor' if party == 'R' else 'grantee'} search for "
            f"'{last}, {first or '(surname only)'}' — results may be truncated."
        )
    return all_rows


# ---------------------------------------------------------------------------
# v3.46 (backlog item 28) — COMBINED address search: Recorded + Land Court
# ---------------------------------------------------------------------------
# Norfolk's page is titled "Search by Address (Recorded and Registered Land
# Combined)" and it queries BOTH sections in ONE request. That makes it the
# only index in this tool that is NAME-INDEPENDENT, which is precisely the
# gap every name-side fix leaves open:
#
#   - the v3.43 name-field clip widens a query but cannot reach a name the
#     registry SPELLED differently (the v3.45 standing limitation);
#   - the v3.44 both-sections search still needs the name to be findable in
#     at least one section;
#   - a misindexed grantee defeats the name index outright.
#
# The address index answers "what is recorded against this PARCEL", so it
# survives all three. It is a SUPPLEMENT and never a selector — see the 2003
# coverage boundary below.
#
# Endpoint (verified live against norfolkresearch.org):
#   form:   /ALIS/WW400R.HTM?WSIQTP=SY14D&WSKYCD=T
#   search: /ALIS/WW400R.HTM?W9PADR=<addr>&W9ABR=<doctype>&W9TOWN=<code>
#           &W9FDTA=<MMDDYYYY>&W9TDTA=&WSHTNM=WW414R00&WSIQTP=SY14AP
#           &WSKYCD=T&WSWVER=2&WSSRPP=30
#   field:  W9PADR, maxlength 30
#
# THREE MECHANICS, each of which produces a WRONG ANSWER if not coded:
#
#  1. IT PAGINATES, AND PAGE 1 IS TINY (~3 documents). Reading page 1 and
#     stopping makes this index look sparse and useless — that conclusion was
#     actually drawn once, and it was wrong. Walked to completion, one
#     residential street number returned 14 documents = the entire parcel
#     chain, including a municipal lien certificate on which the owner is not
#     a party and which NO name search for the owner could ever return.
#     Pagination is the same hidden-field re-GET as _alis_search_http(), with
#     control SY14N in place of LR01N/LC01N.
#
#  2. THE SUFFIX SPELLING DECIDES WHETHER LAND COURT ROWS COME BACK — the
#     house number does NOT. This corrects an earlier reading of the same
#     index. Measured across five parcels on three streets:
#         "<n> BIRCHWOOD ST"     -> Land Court rows, subject deed present
#         "<n> BIRCHWOOD STREET" -> the SAME query minus every Land Court row
#     because the two sections store the suffix differently (Land Court
#     writes "BIRCHWOOD ST.", Recorded writes "BIRCHWOOD STREET"). An earlier
#     recorded this as "a house NUMBER suppresses Land Court rows"; that was
#     a PAGE-1-ONLY read of a paginated result (mechanic 1, one layer
#     deeper) — the suppressed row was on page 2 all along.
#
#     W9PADR is PREFIX-matched, exactly like the ALIS name fields, so the
#     fix is to drop the suffix entirely and query "<number> <STEM>":
#         "12 BIRCHWOOD" is a strict SUPERSET of both "12 BIRCHWOOD ST"
#         and "12 BIRCHWOOD STREET" — verified on 5/5 parcels, none missing.
#     That is one query instead of two, it is far cheaper than the
#     street-only sweep (a busy street runs past 75 documents; the
#     number-qualified query is single digits), and it is the same
#     "a shorter prefix returns a superset" argument as the v3.43 name clip.
#
#  3. ONE DOCUMENT LISTS EVERY ADDRESS IT TOUCHES. A single town-wide
#     assessment carried 315 Addr: entries. Parse by DOCUMENT HEADER
#     ("Doc#:" for Land Court, "Bk-Pg:" for Recorded), never by counting
#     Addr: lines, and expect one document to match many streets. Each row
#     therefore carries `addresses` as a LIST.
#
# THE 2003 BOUNDARY — where this index does not help. The Registry states it
# has included the property address "for all applicable documents since 2003"
# and that earlier listings are "very limited". So:
#   * NEVER select a vesting deed from this index on a pre-2003 chain, and
#   * NEVER read an empty address result as evidence of absence.
# That is the v3.20 rule again: missing information is not a non-match.

_ALIS_ADDRESS_FIELD_LIMIT = 30      # W9PADR maxlength, read off the form
_ALIS_ADDRESS_MAX_PAGES   = 25      # ~3 docs/page, so 25 pages ~= 75 documents

# Street-suffix aliases. Both spellings are queried because the two sections
# store the suffix differently; this is mechanic 2 above, not cosmetics.
_STREET_SUFFIX_ALIASES: dict[str, str] = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR",
    "LANE": "LN", "COURT": "CT", "PLACE": "PL", "TERRACE": "TER",
    "CIRCLE": "CIR", "BOULEVARD": "BLVD", "HIGHWAY": "HWY",
    "PARKWAY": "PKWY", "SQUARE": "SQ", "EXTENSION": "EXT",
    "TURNPIKE": "TPKE", "HEIGHTS": "HTS", "LANDING": "LNDG",
}
_STREET_SUFFIX_EXPAND = {v: k for k, v in _STREET_SUFFIX_ALIASES.items()}

_ALIS_ADDR_HEADER_RE = re.compile(r'(Doc#:|Bk-Pg:)\s*([0-9]+)\s*-\s*([0-9]+)', re.I)
# Cut a captured value at the next "Label:" on the same line — the results page
# packs several labelled fields per line ("Type: DEED  Doc$: 1.00",
# "Town: X  Addr: Y", "<address> Map Book-Page:").
_ALIS_ADDR_TRAILING_LABEL_RE = re.compile(r'\s{1,}[A-Z][A-Za-z$#/ -]{0,22}:.*$')


def _alis_address_normalize_nbsp(html: str) -> str:
    """
    &#160;/&nbsp; are whitespace AND they appear inside the document headers
    themselves ("Doc#:&#160;123456-1"), so they must be normalised before any
    header split — otherwise the Land Court blocks silently do not match and
    the page parses as Recorded-only. (Found exactly that way.)
    """
    return re.sub(r"&#160;|&nbsp;|&#xa0;", " ", html, flags=re.I)


def _alis_address_field(text: str, *labels: str) -> str:
    """First value for any of `labels`, trimmed at the next labelled field."""
    for lab in labels:
        mo = re.search(re.escape(lab) + r"\s*:\s*([^\n]*)", text)
        if mo:
            val = _ALIS_ADDR_TRAILING_LABEL_RE.sub("", mo.group(1).strip()).strip()
            if val:
                return val
    return ""


def _alis_parse_address_results_html(html: str) -> list:
    """
    Parse a combined-address results page into one dict per DOCUMENT.

    Two block layouts share the page and their labels differ — this is not
    cosmetic, and keying on the wrong one drops half the results:
      Land Court : "Doc#: <n>-<seq>"  Address:  Descr:  Grantor:  Grantee:  Ctf#:
      Recorded   : "Bk-Pg: <bk>-<pg>" Addr:     Desc:   Gtor:     Gtee:

    Each row carries the abstract href's recording-date + control-number key
    (rc_year/rc_month/rc_day/ctl_num), which is the same key the existing
    Document Abstract fetchers use — so a row from here can be handed
    straight to the abstract machinery with no extra lookup.
    """
    html = _alis_address_normalize_nbsp(html)
    heads = list(_ALIS_ADDR_HEADER_RE.finditer(html))
    rows = []
    for idx, mo in enumerate(heads):
        seg = html[mo.start(): heads[idx + 1].start() if idx + 1 < len(heads) else len(html)]
        text = BeautifulSoup(seg, "html.parser").get_text("\n")
        text = re.sub(r"[ \t]+", " ", text.replace("\xa0", " "))
        text = re.sub(r"\n{2,}", "\n", text)
        is_lc = mo.group(1).lower().startswith("doc#")

        # EVERY address in THIS document (mechanic 3) — a list, never a scalar.
        addresses = []
        for raw in re.findall(r"(?:Address|Addr)\s*:\s*([^\n]+)", text):
            val = _ALIS_ADDR_TRAILING_LABEL_RE.sub("", raw.strip()).strip()
            if val and val not in addresses:
                addresses.append(val)

        def _href(pattern, _seg=seg):
            hm = re.search(r'href="([^"]*WSIQTP=(?:%s)[^"]*)"' % pattern, _seg)
            return hm.group(1).replace("&amp;", "&") if hm else ""

        abstract_href = _href("LR09A|LC09A")
        key = {}
        for k in ("W9RCCY", "W9RCMM", "W9RCDD", "W9CTLN"):
            km = re.search(k + r"=([^&\"]*)", abstract_href)
            key[k] = km.group(1) if km else ""

        ctf_mo = re.search(r"Ctf#\s*:?\s*\n?\s*([0-9]+)", text)
        parties = re.findall(r"\b(Grantor|Grantee|Gtor|Gtee)\s*:\s*\n?\s*([^\n]+)", text)

        rows.append({
            "land_court":      is_lc,
            "document_number": mo.group(2) if is_lc else "",
            "sequence":        mo.group(3) if is_lc else "",
            "book":            "" if is_lc else mo.group(2),
            "page":            "" if is_lc else mo.group(3),
            "book_page":       "" if is_lc else "%s-%s" % (mo.group(2), mo.group(3)),
            "date_received":   _alis_address_field(text, "Recorded").split("@")[0].strip(),
            "doc_type":        _alis_address_field(text, "Type"),
            "doc_desc":        _alis_address_field(text, "Descr", "Desc"),
            "town":            _alis_address_field(text, "Town"),
            "addresses":       addresses,
            "certificate":     ctf_mo.group(1) if ctf_mo else "",
            "consideration":   _alis_address_field(text, "Consideration"),
            "doc_date":        _alis_address_field(text, "Doc date"),
            "grantors":        [p[1].strip() for p in parties if p[0].lower() in ("grantor", "gtor")],
            "grantees":        [p[1].strip() for p in parties if p[0].lower() in ("grantee", "gtee")],
            "ctl_num":         key["W9CTLN"],
            "rc_year":         key["W9RCCY"],
            "rc_month":        key["W9RCMM"],
            "rc_day":          key["W9RCDD"],
            "abstract_href":   abstract_href,
            "img_href":        _href("LR15I|LC15I"),
        })
    return rows


def _alis_address_row_identity(row: dict) -> tuple:
    return (row.get("land_court"), row.get("document_number"), row.get("book"),
            row.get("page"), row.get("ctl_num"), row.get("date_received"))


def _alis_address_url(base_url: str, address: str, town: str,
                      doc_type: str = "*ALL", date_from: str = "",
                      per_page: int | None = 30) -> str:
    """
    Build a combined address-search URL. `date_from` is MMDDYYYY or "".

    The date format is asserted rather than normalised, for the reason
    recorded as backlog item 31: ALIS answers a MALFORMED date filter with
    ZERO ROWS instead of an error, and a zero-row result is indistinguishable
    from "nothing indexed" — the false-clean shape this codebase keeps having
    to design against. A caller passing "08/10/2018" has a bug and should
    hear about it immediately.
    """
    if date_from and not re.fullmatch(r"\d{8}", date_from):
        raise ValueError(
            "ALIS date_from must be MMDDYYYY (8 digits) or empty, got %r. "
            "A malformed date is NOT rejected by the registry — it silently "
            "returns zero rows, which reads as 'nothing indexed'." % (date_from,)
        )
    address = (address or "").strip().upper()[:_ALIS_ADDRESS_FIELD_LIMIT]
    url = (
        "%s/ALIS/WW400R.HTM?W9PADR=%s&W9ABR=%s&W9TOWN=%s"
        "&W9FDTA=%s&W9TDTA=&WSHTNM=WW414R00&WSIQTP=SY14AP&WSKYCD=T&WSWVER=2"
        % (base_url, quote(address, safe=""), quote(doc_type, safe="*"),
           town, quote(date_from, safe=""))
    )
    if per_page:
        url += "&WSSRPP=%s" % per_page
    return url


def _alis_address_search_http(session, base_url: str, address: str, town: str,
                              doc_type: str = "*ALL", date_from: str = "",
                              max_pages: int = _ALIS_ADDRESS_MAX_PAGES,
                              notes: list = None, meta: dict = None) -> list:
    """
    Run one combined address search and walk its pagination (mechanic 1).

    Sets meta["truncated"] when the page cap is hit with rows still coming.
    A truncated address search must NEVER be reported as an absence of
    anything — the same rule as every other capped search in this file.
    """
    url = _alis_address_url(base_url, address, town, doc_type, date_from)
    resp = _alis_http_get(session, url)
    html = resp.text
    page_rows = _alis_parse_address_results_html(html)

    all_rows = list(page_rows)
    seen = {_alis_address_row_identity(r) for r in page_rows}
    pages = 1
    while page_rows and pages < max_pages:
        fields = _alis_hidden_fields_html(html)
        if not fields:
            break
        params = [(n, v) for n, v in fields if n not in ("WSIQTP", "WSSRPP")]
        params.append(("WSIQTP", "SY14N"))
        params.append(("WSSRPP", "30"))
        resp = _alis_http_get(session, "%s/ALIS/WW400R.HTM" % base_url, params=params)
        html = resp.text
        fresh = _alis_parse_address_results_html(html)
        page_rows = [r for r in fresh if _alis_address_row_identity(r) not in seen]
        if not page_rows:
            break
        seen.update(_alis_address_row_identity(r) for r in page_rows)
        all_rows.extend(page_rows)
        pages += 1

    truncated = pages >= max_pages and bool(page_rows)
    if meta is not None:
        meta["truncated"] = truncated
        meta["pages_walked"] = pages
    if truncated and notes is not None:
        notes.append(
            "WARNING: address search '%s' (town %s) hit the %d-page cap at %d "
            "document(s) — the result is TRUNCATED. Do not read it as a complete "
            "picture of the street." % (address, town, max_pages, len(all_rows))
        )
    return all_rows


def _alis_address_queries(street_number: str, street: str) -> list:
    """
    Build the address queries for a parcel, cheapest-and-widest first.

    Preferred form is "<number> <STEM>" with the suffix DROPPED: W9PADR is
    prefix-matched, so the stem is a strict superset of both the abbreviated
    and the spelled-out suffix (verified on 5/5 parcels), and it is the only
    form that reliably returns Land Court rows — see mechanic 2 above.

      ("12", "BIRCHWOOD DRIVE") -> ["12 BIRCHWOOD"]
      ("12", "BIRCHWOOD ST")   -> ["12 BIRCHWOOD"]
      ("",   "BIRCHWOOD ST")   -> ["BIRCHWOOD"]  (street-only fallback)

    Returns [] when there is nothing to query, which callers must treat as
    "not asked", never as "nothing found".
    """
    stem_words = re.sub(r"\s+", " ", (street or "").strip().upper()).split()
    while stem_words and (stem_words[-1] in _STREET_SUFFIX_ALIASES
                          or stem_words[-1] in _STREET_SUFFIX_EXPAND):
        stem_words.pop()
    stem = " ".join(stem_words).strip()
    if not stem:
        return []
    num = str(street_number or "").strip().upper()
    q = ("%s %s" % (num, stem)).strip()
    return [q[:_ALIS_ADDRESS_FIELD_LIMIT]]


def _alis_address_matches_number(row: dict, street_number: str, street: str) -> bool:
    """
    Does any address on this document name the subject street number?

    Both sides are normalised loosely because the index is dirty — observed
    values include a misspelled street name and inconsistent suffix and
    punctuation between the two sections. A row with NO address at all
    returns False here, but callers must treat that as UNVERIFIED rather than
    as a different parcel (the v3.20 rule).
    """
    if not street_number:
        return False
    head = re.sub(r"\s+", " ", (street or "").strip().upper()).split()
    stem = head[0] if head else ""
    num = str(street_number).strip().upper()
    for addr in row.get("addresses") or []:
        a = re.sub(r"[.,]", " ", addr.upper())
        a = re.sub(r"\s+", " ", a).strip()
        toks = a.split()
        if not toks:
            continue
        # the leading number must match exactly ("48" must not match "148"),
        # and a range ("66-70") counts as a match on either endpoint
        lead = toks[0]
        nums = lead.split("-") if "-" in lead else [lead]
        if num in nums and (not stem or stem in a):
            return True
    return False


def _alis_land_court_tripwire(session, base_url: str, street_number: str,
                              street: str, town: str, notes: list) -> dict:
    """
    ITEM 28, use 1 — the cheap fix for the item-25 blind spot.

    After a Recorded-Land selection, ask the NAME-INDEPENDENT combined
    address index whether the SUBJECT PARCEL has any Registered Land. The
    v3.44 both-sections search already covers the case where the name index
    can see the parcel; this covers the case it cannot — a misindexed,
    variant, or successor owner name, which is how a Land Court parcel gets
    reported as the seller's adjoining Recorded parcel at exit 0.

    Restricted to the DEED GROUP (*DD) deliberately. Measured on one parcel:
    50 documents / 17 pages / ~30 s unrestricted versus 1 document / 1 page /
    ~2 s for the deed group, with the Land Court deed still returned. A
    registered parcel's defining instrument is a deed noted on a certificate,
    so the deed group is the right net for THIS question.

    The cost of that restriction, stated plainly because it bounds the
    negative answer: a registered parcel whose only address-indexed document
    at this number is a NON-deed would not be seen here. That is why a clean
    result is reported as support, never as proof.

    Returns {"checked", "queries", "land_court_rows", "rows", "truncated"}.
    `checked` False means the question was NOT asked (no street parsed, or
    every query errored) — which is never the same as "no registered land".
    """
    out = {"checked": False, "queries": [], "land_court_rows": [],
           "rows": 0, "truncated": False}
    queries = _alis_address_queries(street_number, street)
    if not queries or not town:
        notes.append(
            "Land Court tripwire (v3.46): SKIPPED — no street or town available, so "
            "the address index was not queried. This is NOT a finding that the parcel "
            "has no registered land."
        )
        return out

    seen, ok = set(), False
    for q in queries:
        meta = {}
        try:
            rows = _alis_address_search_http(session, base_url, q, town,
                                             doc_type="*DD", notes=notes, meta=meta)
            ok = True
        except Exception as exc:                      # noqa: BLE001
            notes.append(
                "Land Court tripwire: address query '%s' FAILED (%s) — treat the "
                "tripwire as not run for that variant." % (q, exc)
            )
            continue
        out["queries"].append({"query": q, "rows": len(rows),
                               "truncated": bool(meta.get("truncated"))})
        out["truncated"] = out["truncated"] or bool(meta.get("truncated"))
        for r in rows:
            ident = _alis_address_row_identity(r)
            if ident in seen:
                continue
            seen.add(ident)
            out["rows"] += 1
            if r["land_court"]:
                out["land_court_rows"].append(r)

    out["checked"] = ok
    if not ok:
        return out

    # The query is already number-scoped, so a returned Land Court row is at
    # (or prefix-matches) the subject number. Confirm against the row's own
    # address where it has one; a row with NO address stays in — absent
    # information is not a non-match (the v3.20 rule).
    lc = out["land_court_rows"]
    lc_here = [r for r in lc
               if not r.get("addresses")
               or _alis_address_matches_number(r, street_number, street)]
    if lc_here:
        cites = ", ".join(
            "Doc %s%s" % (r["document_number"],
                          (" / Ctf %s" % r["certificate"]) if r["certificate"] else "")
            for r in lc_here[:5]
        )
        notes.append(
            "CRITICAL (v3.46 Land Court tripwire): the combined address index shows "
            "REGISTERED LAND at the subject address — %s. The selected deed is "
            "Recorded Land. Confirm which section the subject parcel is in before "
            "reporting; re-run with --office registered if it is Land Court." % cites
        )
    elif lc:
        notes.append(
            "NOTE (v3.46 Land Court tripwire): %d Registered Land deed(s) matched the "
            "street prefix but not the subject number — likely a neighbouring parcel." % len(lc)
        )
    else:
        notes.append(
            "NOTE (v3.46 Land Court tripwire): no Registered Land deed found at this "
            "address via the NAME-INDEPENDENT combined address index"
            + (" — but the result was TRUNCATED, so this is not a complete answer."
               if out["truncated"] else
               ". Two limits bound this: address coverage is reliable only from 2003, "
               "and the query is restricted to the deed group. It SUPPORTS the "
               "Recorded Land selection without proving it.")
        )
    return out


def _alis_get_pdf_hrefs_http(session, base_url: str, img_href: str) -> dict:
    """
    HTTP version of _alis_get_pdf_hrefs() — fetch the Document Image List
    page and return the same dict shape (pdf_hrefs / is_fallback / all_pdfs /
    image_list_url).
    """
    full_url = (base_url + img_href) if img_href.startswith("/") else img_href
    empty = {"pdf_hrefs": [], "is_fallback": False, "all_pdfs": [],
             "image_list_url": full_url}
    try:
        resp = _alis_http_get(session, full_url)
    except Exception:
        return empty

    soup = BeautifulSoup(resp.text, "html.parser")
    all_pdfs = [
        a.get("href") for a in soup.find_all("a", href=re.compile(r"/WwwImg/", re.I))
        if a.get("href") and re.search(r"\.PDF$", a.get("href"), re.I)
    ]
    numbered = [h for h in all_pdfs if re.search(r"\d{3,4}\.PDF$", h, re.I)]
    if numbered:
        return {"pdf_hrefs": numbered, "is_fallback": False,
                "all_pdfs": all_pdfs, "image_list_url": full_url}
    if all_pdfs:
        return {"pdf_hrefs": all_pdfs, "is_fallback": True,
                "all_pdfs": all_pdfs, "image_list_url": full_url}
    return empty


def _alis_download_pdfs_http(
    session,
    base_url: str,
    pdf_hrefs: list,
    base_name: str,
    output_folder: Path,
    label: str = "deed",
) -> tuple:
    """
    HTTP version of _alis_download_pdfs(). `label` distinguishes the main
    deed ("deed") from candidate page-1 samples ("candidate_Bk..._Pg...").
    Returns (saved, errors).
    """
    saved, errors = [], []
    for i, href in enumerate(pdf_hrefs, start=1):
        url = (base_url + href) if href.startswith("/") else href
        try:
            resp = _alis_http_get(session, url)
            ct = resp.headers.get("content-type", "").lower()
            if "pdf" in ct or url.lower().endswith(".pdf"):
                out_path = output_folder / f"{base_name} - {label}_p{i}.pdf"
                out_path.write_bytes(resp.content)
                saved.append(str(out_path))
            else:
                errors.append(f"Page {i}: non-PDF content-type ({ct!r}) — {url}")
        except Exception as e:
            errors.append(f"Page {i}: download error — {e} — {url}")
    return saved, errors


# ---------------------------------------------------------------------------
# Document Abstract page (v3.22) — the registry's own structured index record
# for one instrument, including the PROPERTY ADDRESS.
#
# Until v3.22 the workflow explicitly skipped this page ("all required
# metadata is on the results and image list pages"), an enumeration that
# missed the `Addr:` field — and the address is precisely what the v3.14/3.15
# wrong-parcel guards spend a PDF download plus a vision-model call per
# candidate to re-derive. Worse, that derivation has a null-address failure
# mode this page does not: Keegan Bk15978/412's page 1 reads only "SEE ATTACHED
# FULL LEGAL", so its sampled address came back null and the candidate was
# silently dropped (the whole v3.20 defect) — while its abstract carries
# "Town: WEYMOUTH  Addr: 402 SEDGEFIELD STREET" as plain text.
#
# Cheap (one GET), needs no ANTHROPIC_API_KEY, and also yields Doc$
# consideration, page count, and the Ref By:/Refers to Book: cross-references.
# NOT a replacement for PDF sampling: `Addr:` is frequently absent (Keegan
# Bk11873/154 has none), and an absent address means UNVERIFIED, never "a
# different parcel" — the caller must fall through to sampling.
#
# RECORDED LAND ONLY. The Land Court abstract is keyed differently and
# returns HTTP 500 for these parameters (probed live 2026-08-12); Land Court
# rows fall through to the existing sampling path untouched.
# ---------------------------------------------------------------------------

# Every label the abstract record uses. Parsing is positional: a field's value
# runs from the end of its label to the start of the next label, which handles
# repeated Town:/Addr: pairs (multi-parcel deeds) and missing fields alike.
_ALIS_ABSTRACT_LABELS = (
    "Bk-Pg:", "Recorded:", "Inst #:", "Chg:", "Vfy:", "Sec:",
    "Pages in document:", "Grp:", "Type:", "Doc$:", "Desc:",
    "Refers to Book:", "Town:", "Addr:", "Map Book-Page:",
    "Gtor:", "Gtee:", "Ref By:", "In book:", "Notes:", "Chgs Jrnl",
    "Prev Doc", "Next Doc", "Print Search Results",
    # v3.28 — the recording-footer labels. The LC vocabulary below has had
    # these since v3.25; Recorded Land did not, and the scan takes each
    # value up to the NEXT label — so on a page whose last label is "Gtee:"
    # the whole footer was swallowed into the final party name:
    #   "SALGADO, MARIA TERESA (Gtee) Return addr: SIMPLIFILE E-RECORDING
    #    Recording Fee: 100.00 State excise: .00 Surcharge: 55.00"
    # Harmless while `grantees` was only displayed; not harmless once
    # v3.28 derives grantor-check SEARCH NAMES from it — a search for that
    # first name returns nothing, and a co-owner search that finds nothing
    # is indistinguishable from a co-owner with no subsequent instruments.
    "Return addr:", "Recording Fee:", "State excise:", "Surcharge:",
)

# v3.25 — the Land Court abstract page uses its own label vocabulary
# (spelled-out where the Recorded Land page abbreviates): Address:/Descr:/
# Grantor:/Grantee: vs Addr:/Desc:/Gtor:/Gtee:, Consideration: vs Doc$:,
# and LC-only fields — Ctf#:, Doc date:, Parent doc:/Related doc: (the
# cross-references), Return addr:. Note Address: precedes Town: (Recorded
# Land pairs Town:→Addr: in the opposite order).
_ALIS_LC_ABSTRACT_LABELS = (
    "Doc#:", "Recorded:", "Address:", "Pages in document:", "Group:",
    "Type:", "Descr:", "Town:", "Doc date:", "Consideration:", "Ctf#:",
    "Parent doc:", "Related doc:", "Grantor:", "Grantee:", "Return addr:",
    "Recording Fee:", "State excise:", "Surcharge:", "Notes:",
    "Prev Doc", "Next Doc", "Print Search Results",
)


def _alis_abstract_url(base_url: str, row: dict) -> str:
    """
    v3.22 — build the Document Abstract URL for a result row. Keyed by
    recording date + control number, both already parsed off the results
    grid, so no extra navigation is needed. Returns "" when the row lacks
    either.

    v3.25 — Land Court supported. The earlier "keyed by document number"
    hypothesis was wrong: the LC abstract uses the SAME date+ctl keying,
    just `WSIQTP=LC09A` + `WSKYCD=D` (not LR09A/B) — read off the ABS
    icon's href on a live LC results page (Norfolk Kilbride row,
    2026-08-12; the `W9IMID`/`W9ABR` params the icon carries are optional).
    Confirmed identical on Barnstable.
    """
    parts = (row.get("date_received") or "").split("-")
    ctl = (row.get("ctl_num") or "").strip()
    if len(parts) != 3 or not ctl:
        return ""
    mm, dd, yyyy = parts
    inq, key = ("LC09A", "D") if row.get("land_court") else ("LR09A", "B")
    return (f"{base_url}/ALIS/WW400R.HTM?WSIQTP={inq}&WSKYCD={key}"
            f"&W9RCCY={yyyy}&W9RCMM={mm}&W9RCDD={dd}&W9CTLN={ctl}")


def _alis_parse_abstract_html(html_text: str) -> dict:
    """
    v3.22 — parse a Recorded Land abstract page into structured fields.
    v3.25 — also parses the Land Court abstract page (own label
    vocabulary; routed by which start label the page carries).

    Returns {book, page, recorded, inst, pages, doc_type, consideration,
    desc, addresses, grantors, grantees, refs, certificate}. `addresses`
    is a list of {"town", "addr"} in document order; `addr` is None when
    the record carries a Town with no Addr (common on Recorded Land), and
    the list is empty when the record carries neither. On Land Court:
    book/page are None, `inst` is the document number (group suffix
    stripped), `certificate` is the Ctf# when numeric, and `refs` carries
    the Parent doc:/Related doc: cross-references.
    """
    txt = _html.unescape(re.sub(r"<[^>]+>", " ", html_text or ""))
    txt = re.sub(r"\s+", " ", txt).strip()
    start = txt.find("Bk-Pg:")
    if start < 0:
        return _alis_parse_lc_abstract_text(txt)
    txt = txt[start:]

    # Positional scan: (index, label) for every label occurrence.
    hits = []
    for lab in _ALIS_ABSTRACT_LABELS:
        i = txt.find(lab)
        while i >= 0:
            hits.append((i, lab))
            i = txt.find(lab, i + 1)
    hits.sort()

    fields = []   # (label, value) in document order
    for n, (pos, lab) in enumerate(hits):
        end = hits[n + 1][0] if n + 1 < len(hits) else len(txt)
        fields.append((lab, txt[pos + len(lab):end].strip()))

    def first(label):
        return next((v for l, v in fields if l == label and v), None)

    out = {
        "book": None, "page": None,
        "recorded": first("Recorded:"),
        "inst": first("Inst #:"),
        "pages": None,
        "doc_type": first("Type:"),
        "consideration": first("Doc$:"),
        "desc": first("Desc:"),
        "addresses": [],
        "grantors": [v for l, v in fields if l == "Gtor:" and v],
        "grantees": [v for l, v in fields if l == "Gtee:" and v],
        "refs": [],
        "certificate": None,   # v3.25 — Land Court only
    }
    bp = first("Bk-Pg:")
    if bp:
        mo = re.match(r"([0-9A-Za-z]+)-([0-9A-Za-z]+)", bp)
        if mo:
            out["book"], out["page"] = mo.group(1), mo.group(2)
    pg = first("Pages in document:")
    if pg and pg.split()[0].isdigit():
        out["pages"] = int(pg.split()[0])
    if out["consideration"]:
        out["consideration"] = out["consideration"].split()[0].rstrip(",")

    # Town:/Addr: pairs — Addr belongs to the Town it immediately follows.
    for n, (lab, val) in enumerate(fields):
        if lab != "Town:":
            continue
        addr = None
        if n + 1 < len(fields) and fields[n + 1][0] == "Addr:":
            addr = fields[n + 1][1] or None
        out["addresses"].append({"town": val or None, "addr": addr})

    # Cross-references: "Ref By: <date> <TYPE> In book: <bk>-<pg>"
    for n, (lab, val) in enumerate(fields):
        if lab not in ("Ref By:", "Refers to Book:"):
            continue
        book = None
        if lab == "Refers to Book:":
            book = val.split()[0] if val else None
        elif n + 1 < len(fields) and fields[n + 1][0] == "In book:":
            book = (fields[n + 1][1] or "").split()[0] or None
        out["refs"].append({"kind": lab.rstrip(":"), "detail": val or None,
                            "book_page": book})
    return out


def _alis_parse_lc_abstract_text(txt: str) -> dict:
    """
    v3.25 — parse the Land Court abstract page (already tag-stripped and
    whitespace-collapsed by _alis_parse_abstract_html, which routes here
    when the page has no "Bk-Pg:"). Same positional label scan, LC
    vocabulary. Live samples: Norfolk Doc 1183426 (Kilbride — Address:
    29 FOX MEADOW ROAD, Ctf#: 174905, Parent doc: 438,116), Barnstable
    Doc 982447 (COC — Ctf#: "See parent list", Related doc: + Parent doc:,
    no Consideration:). Returns the same dict shape as the Recorded Land
    parser; {} when the page carries no "Doc#:" either (maintenance page,
    genuinely unkeyed row, error page).
    """
    start = txt.find("Doc#:")
    if start < 0:
        return {}
    txt = txt[start:]

    hits = []
    for lab in _ALIS_LC_ABSTRACT_LABELS:
        i = txt.find(lab)
        while i >= 0:
            hits.append((i, lab))
            i = txt.find(lab, i + 1)
    hits.sort()

    fields = []   # (label, value) in document order
    for n, (pos, lab) in enumerate(hits):
        end = hits[n + 1][0] if n + 1 < len(hits) else len(txt)
        fields.append((lab, txt[pos + len(lab):end].strip()))

    def first(label):
        return next((v for l, v in fields if l == label and v), None)

    def party(label):
        # values carry a trailing role token: "COYNE, DENNIS H. (JR.&AL) (Gtor)"
        out = []
        for l, v in fields:
            if l == label and v:
                out.append(re.sub(r"\s*\((?:Gtor|Gtee)\)\s*$", "", v))
        return out

    out = {
        "book": None, "page": None,
        "recorded": first("Recorded:"),
        "inst": None,
        "pages": None,
        "doc_type": first("Type:"),
        "consideration": first("Consideration:"),
        "desc": first("Descr:"),
        "addresses": [],
        "grantors": party("Grantor:"),
        "grantees": party("Grantee:"),
        "refs": [],
        "certificate": None,
    }
    doc = first("Doc#:")
    if doc:
        # "1183426-1" — strip the group suffix.
        out["inst"] = doc.split()[0].split("-")[0]
    pg = first("Pages in document:")
    if pg and pg.split()[0].isdigit():
        out["pages"] = int(pg.split()[0])
    if out["consideration"]:
        out["consideration"] = out["consideration"].split()[0].rstrip(",")
    ctf = first("Ctf#:")
    if ctf:
        tok = ctf.split()[0].replace(",", "")
        # "See parent list" and similar non-numeric values stay out — a
        # certificate number is only useful when it IS one.
        out["certificate"] = tok if tok.isdigit() else None

    # Address:/Town: pairing — Address PRECEDES its Town on this page
    # (Recorded Land is the opposite), with other fields between; a
    # multi-group document repeats the block per group.
    pending_addr = None
    for lab, val in fields:
        if lab == "Address:":
            if pending_addr is not None:
                out["addresses"].append({"town": None, "addr": pending_addr})
            pending_addr = val or None
        elif lab == "Town:":
            out["addresses"].append({"town": val or None, "addr": pending_addr})
            pending_addr = None
    if pending_addr is not None:
        out["addresses"].append({"town": None, "addr": pending_addr})

    # Cross-references: the prior instrument(s) in this parcel's chain.
    for lab, val in fields:
        if lab in ("Parent doc:", "Related doc:") and val:
            out["refs"].append({"kind": lab.rstrip(":"), "detail": val,
                                "book_page": None})
    return out


# ---------------------------------------------------------------------------
# v3.26 — cross-reference normalisation (the registries' own "what else
# touches this instrument" lists). Four sources collect this data and none
# of them consumed it: ALIS Recorded `Ref By:`/`Refers to Book:` (v3.22),
# ALIS Land Court `Parent doc:`/`Related doc:` (v3.25), the Plymouth detail
# panel's References table (v3.24) and the Middlesex South detail panel's
# References list (v3.8). Each renders differently; this normalises all
# four into one `cross_references` list so the report can show them and
# /title-rundown + the discharge workflow can consume them.
#
# SCOPE (unchanged): this workflow does NOT verify discharges. A DISCHARGE
# appearing here is a LEAD — the registry index saying an instrument of
# that type references this one. It is not proof the mortgage was
# discharged, and it must never be reported as one.
# ---------------------------------------------------------------------------

# Longest-first within each bucket; first hit wins, so "DISCHARGE" is tested
# before "DIS" and "DECLARATION OF HOMESTEAD" before "DECLARATION".
_CROSSREF_KINDS = (
    ("partial_release", ("PARTIAL RELEASE",)),   # v3.52 — before RELEASE
    ("discharge",  ("DISCHARGE", "RELEASE", "SATISFACTION", "DIS REL",
                    "DIS", "REL")),
    ("homestead",  ("DECLARATION OF HOMESTEAD", "HOMESTEAD", "DCLN HMS", "HMS")),
    ("deed",       ("DEED", "DD")),
    ("mortgage",   ("MORTGAGE", "MTG")),
    ("death_cert", ("DEATH CERTIFICATE", "DEATH CERT", "DEATH")),
    ("probate",    ("PROBATE", "ESTATE", "AFFIDAVIT", "AFFT")),
    ("assignment", ("ASSIGNMENT", "ASSIGN", "ASST")),
    ("lien",       ("MUNICIPAL LIEN", "TAX LIEN", "LIEN", "ATTACHMENT",
                    "ATTACH", "MLC")),
    ("plan",       ("PLAN",)),
    ("taking",     ("TAKING", "TKG")),
    ("easement",   ("EASEMENT", "ESMT")),
    ("notice",     ("NOTICE", "NOTC")),
)

# v3.52 — the terse Avenu/20-20 codes (Plymouth's published "INSTRUMENT CODES
# WITH CORRESPONDING DESCRIPTIONS, effective November 3, 2003" — all 59, plus
# the 8-character forms the grid truncates them to), matched as WHOLE TOKEN
# SEQUENCES before the substring needles above. The needles alone misfiled
# most of the table: every "DIS xxx"/"REL xxx" code landed in 'discharge'
# (a released UCC, tax lien or lis pendens then fired the MORTGAGE-discharge
# note), AFFT TAX (a FEDERAL TAX LIEN affidavit) landed in 'probate' via
# "AFFT", and ATT/EXON/JGMT/LISPN/TT/CR fell through to 'other'. Short codes
# like "TT" or "CR" cannot simply join the substring needles — they would
# fire inside unrelated words — hence exact token matching here.
#
# 'discharge' is kept for MORTGAGE discharges only (DIS, DIS REL, REL), because
# the note and the report treat that kind as a mortgage-payoff lead. Releases
# of anything else are 'release'; a Partial Release (PR — usually a lender
# releasing part of the land from a mortgage) is its own kind because it is a
# lead on the mortgage but never a full discharge.
_CROSSREF_CODES = {
    # mortgage discharge (the only codes that feed the discharge note)
    "DIS": "discharge", "DIS REL": "discharge", "REL": "discharge",
    "PR": "partial_release",
    # releases / discharges of something OTHER than a mortgage
    "AFFT DIS": "release", "DIS ATT": "release", "DIS EXON": "release",
    "DIS LISPN": "release", "DIS LISP": "release",
    "REL TAX": "release", "REL UCC": "release",
    # mortgage and its satellites
    "MTG": "mortgage", "AMDT MTG": "mortgage", "SUBD MTG": "mortgage",
    "SUBD": "mortgage", "MDFN AGRT": "mortgage", "MDFN AGR": "mortgage",
    "CRTF ENTRY": "foreclosure", "CRTF ENT": "foreclosure",
    "ASST": "assignment",
    # liens, judgments, litigation, UCC fixture filings
    "AFFT TAX": "lien", "ATT": "lien", "CRTF ATT": "lien",
    "EXON": "lien", "EXTN EXON": "lien", "EXTN EXO": "lien",
    "JGMT": "lien", "LISPN": "lien", "MLC": "lien",
    "UCC": "lien", "CONTN UCC": "lien", "CONTN UC": "lien",
    "AMDT UCC": "lien", "AMDT UC": "lien",
    # takings and tax-title redemption
    "TKG": "taking", "TT": "taking", "CR": "redemption",
    "ESMT": "easement",
    # conveyances
    "DEED": "deed", "MDEED": "deed",
    # ownership / signer changes
    "DEATH CRTF": "death_cert", "DEATH CR": "death_cert",
    "DCRE": "court_order", "ORDR": "court_order",
    "TR CRTF": "trust", "ACPT TR": "trust", "APPT ACPT TR": "trust",
    "APPT ACP": "trust", "RSGN TR": "trust", "DCLN TRUST": "trust",
    "DCLN TRU": "trust", "AMDT TRUST": "trust", "AMDT TRU": "trust",
    "DCLN HMSTD": "homestead", "DCLN HMS": "homestead",
    "AFFT": "probate",
    "NOTC": "notice", "NOTC CONTR": "notice", "NOTC CON": "notice",
    "NOTC LSE": "notice", "NOTC OPTN": "notice", "NOTC OPT": "notice",
    # deliberately 'other': 6D CRTF, AGRT, AMDT, CRTF, LSE, OPTN, OPTN AGRT,
    # POA, VOTE, WAVR — surfaced as-is, never guessed into a bucket.
}
_CROSSREF_CODE_TOKENS = {tuple(c.split()): k for c, k in _CROSSREF_CODES.items()}
_CROSSREF_CODE_MAXLEN = max(len(t) for t in _CROSSREF_CODE_TOKENS)


def _crossref_code_kind(t: str) -> str | None:
    """v3.52 — the kind of the LONGEST terse code appearing as whole tokens
    in `t` (so "DIS LISPN" beats "DIS", "AFFT TAX" beats "AFFT"), or None."""
    toks = re.findall(r"[A-Z0-9]+", t)
    for n in range(min(_CROSSREF_CODE_MAXLEN, len(toks)), 0, -1):
        for i in range(len(toks) - n + 1):
            kind = _CROSSREF_CODE_TOKENS.get(tuple(toks[i:i + n]))
            if kind:
                return kind
    return None


def _classify_cross_reference(text: str) -> str:
    """v3.26 — bucket a cross-reference's instrument text. 'other' when
    nothing matches: an unrecognised type is surfaced, never dropped.

    v3.52 — terse Avenu codes are resolved first, as whole tokens, from
    `_CROSSREF_CODES`; spelled-out labels (ALIS, and the spelled Avenu
    forms such as "DISCHARGE OF MORTGAGE") fall through to the needles."""
    t = (text or "").upper()
    kind = _crossref_code_kind(t)
    if kind:
        return kind
    for kind, needles in _CROSSREF_KINDS:
        if any(n in t for n in needles):
            return kind
    return "other"


def _normalize_cross_references(entries, source: str) -> list:
    """
    v3.26 — normalise one registry's cross-reference list into
    [{kind, instrument, book, page, doc_number, certificate, date,
      direction, source, raw}].

    `entries` is either the ALIS abstract's `refs` (list of dicts) or a
    list of raw text lines (the Plymouth / Middlesex South detail-panel
    slices, which arrive as innerText rows with tab-separated cells).

    `direction` is the part a title reader actually acts on:
      later    — a subsequent instrument references this one (ALIS
                 `Ref By:`; panel rows dated after the deed). These are
                 the homesteads/discharges/deeds recorded against the
                 parcel afterwards.
      earlier  — this instrument references a prior one (ALIS `Refers to
                 Book:`, Land Court `Parent doc:` — the prior deed or
                 certificate in the chain).
      related  — lateral (Land Court `Related doc:`) or undetermined.

    Never raises: a line it cannot parse is still returned with `raw` set
    and everything else null, because dropping an unparsed cross-reference
    is exactly the "missing information treated as absence" failure this
    codebase keeps relearning.
    """
    out = []
    for e in entries or []:
        if isinstance(e, dict):
            kind_label = (e.get("kind") or "").strip()
            detail = (e.get("detail") or "").strip()
            bp = (e.get("book_page") or "").strip()
            raw = f"{kind_label}: {detail}" if kind_label else detail
            direction = ("later" if kind_label == "Ref By"
                         else "earlier" if kind_label in ("Refers to Book",
                                                          "Parent doc")
                         else "related")
        else:
            raw = " ".join(str(e).split())
            if not raw or raw.lower().startswith("references"):
                continue   # the "References - 2" table caption
            kind_label, detail, bp, direction = "", raw, "", "later"

        book = page = doc_number = certificate = date = None
        # Book/page: "35430-156" (ALIS) or "29868/325" (panel tables).
        mo = re.search(r"(?<![0-9])(\d{3,6})[-/](\d{1,4})(?![0-9])", bp or detail)
        if mo:
            book, page = mo.group(1), mo.group(2)
        # Land Court: "438,116 1 DEED Ctf: 117912"
        if not book:
            mo = re.match(r"([\d,]{4,})", detail)
            if mo:
                doc_number = mo.group(1).replace(",", "")
        mo = re.search(r"Ctf:?\s*([\d,]+)", detail, re.IGNORECASE)
        if mo:
            certificate = mo.group(1).replace(",", "")
        mo = re.search(r"(\d{1,2}-\d{1,2}-\d{4})", detail)
        if mo:
            date = mo.group(1)
        else:
            mo = re.search(r"(?<![0-9])((?:19|20)\d{2})(?![0-9])", detail)
            if mo:
                date = mo.group(1)

        # Instrument text = the words, minus the numeric/date noise.
        instrument = re.sub(r"Ctf:?\s*[\d,]+", " ", detail, flags=re.IGNORECASE)
        instrument = re.sub(r"\d{1,2}-\d{1,2}-\d{4}", " ", instrument)
        instrument = re.sub(r"(?<![A-Za-z])[\d,]+(?:[-/]\d+)?(?![A-Za-z])", " ", instrument)
        instrument = " ".join(instrument.split()) or None

        out.append({
            "kind": _classify_cross_reference(instrument or detail),
            "instrument": instrument,
            "book": book,
            "page": page,
            "doc_number": doc_number,
            "certificate": certificate,
            "date": date,
            "direction": direction,
            "source": source,
            "raw": raw,
        })
    return out


def _cross_reference_note(refs: list) -> str:
    """v3.26 — one-line summary of the normalised cross-references for the
    notes array. Names the discharge-type hits explicitly because those are
    the ones a reader will want to chase — while saying plainly that this
    workflow has not verified them."""
    if not refs:
        return ""
    by_kind = {}
    for r in refs:
        by_kind.setdefault(r["kind"], 0)
        by_kind[r["kind"]] += 1
    parts = ", ".join(f"{n} {k}" for k, n in sorted(by_kind.items()))
    msg = (f"Cross-references (v3.26): {len(refs)} instrument(s) reference "
           f"this deed or are referenced by it — {parts}. These are the "
           "registry's own index cross-refs, useful as leads for the "
           "discharge / title-rundown workflows.")
    disc = [r for r in refs if r["kind"] == "discharge"]
    if disc:
        cites = ", ".join(
            (f"Bk{r['book']}/{r['page']}" if r["book"]
             else f"Doc#{r['doc_number']}" if r["doc_number"] else r["raw"])
            for r in disc)
        msg += (f" NOTE the {len(disc)} discharge-type reference(s) "
                f"({cites}): this workflow does NOT verify discharges — "
                "treat them as leads to confirm, never as proof a mortgage "
                "was discharged.")
    return msg


def _address_sources_disagree(addr_pdf, addr_abstract, base_name: str) -> bool:
    """
    v3.26 — do the deed PDF and the registry abstract disagree about the
    property address? Both have been reported since v3.22 and on every run
    so far have agreed; a disagreement means either a misindexed abstract
    or a wrong-parcel PDF, and must not pass silently because one of the
    two happened to match the subject.

    Compared on the street parsed from --base-name — that is the question
    the run actually turns on ("do these name the same parcel, relative to
    the subject?"), and it tolerates the formatting differences between a
    staff-typed index line and a granting clause ("402 SEDGEFIELD STREET,
    WEYMOUTH" vs "402 Sedgefield Street, Weymouth, MA 02188"). With no street
    to compare against, falls back to loose containment of the leading
    address component. False whenever either source is missing: absence is
    not disagreement.
    """
    if not addr_pdf or not addr_abstract:
        return False
    st_num, st_word = _parse_street_from_base_name(base_name)
    if st_num and st_word:
        return (_alis_address_matches(st_num, st_word, addr_pdf)
                != _alis_address_matches(st_num, st_word, addr_abstract))
    a, b = addr_pdf.upper(), addr_abstract.upper()
    return not (a.split(",")[0].strip() in b or b.split(",")[0].strip() in a)


def _alis_fetch_abstract_http(session, base_url: str, row: dict,
                              notes: list = None) -> dict:
    """
    v3.22 — fetch + parse one row's Document Abstract. Fails soft: returns
    {} on any error (unsupported row, HTTP failure, unparseable page) so
    every caller falls back to the existing PDF-sampling path.
    """
    url = _alis_abstract_url(base_url, row)
    if not url:
        return {}
    try:
        parsed = _alis_parse_abstract_html(_alis_http_get(session, url).text)
    except Exception as e:
        if notes is not None:
            notes.append(f"Abstract fetch failed for {_alis_row_id(row)} "
                         f"(non-fatal, falling back to page-1 sampling): {e}")
        return {}
    if parsed:
        parsed["url"] = url
    return parsed


# v3.39 (item 22b) — the registry does not always leave Addr blank when it
# has no address; it writes a PLACEHOLDER. Confirmed live on the Norfolk
# Land Court abstracts for a death certificate and its companion affidavit:
# `Addr: N/A`. Consumed as a real address that string is a NON-MATCH, which
# demoted those rows out of "parcel unknown" (kept for review) and into
# "other street, subject town" (demoted) — the v3.20 lesson exactly, one
# layer out: a placeholder MEANS missing information, and reading it as a
# value is how missing information becomes a negative answer.
_ADDRESS_PLACEHOLDERS = {
    "N/A", "NA", "N.A.", "N.A", "NONE", "NULL", "UNKNOWN", "UNK",
    "-", "--", "---", "?", "SEE RECORD", "SEE DEED", "SEE DOCUMENT",
    "NOT AVAILABLE", "NO ADDRESS", "NOT GIVEN",
}


def _is_placeholder_address(addr: str) -> bool:
    """v3.39 — True when the registry wrote 'no address' rather than one."""
    t = (addr or "").strip().upper().strip(".").strip()
    return not t or t in _ADDRESS_PLACEHOLDERS


def _alis_abstract_address_strings(abstract: dict) -> list:
    """
    v3.22 — the abstract's addresses as match-ready strings ("402 SEDGEFIELD
    STREET, WEYMOUTH"). Entries with no Addr are omitted: a Town alone
    cannot answer the parcel question, and treating it as an answer is the
    exact mistake v3.20 was written to prevent.

    v3.39 (item 22b) — a PLACEHOLDER Addr ("N/A", "NONE", "SEE RECORD") is
    omitted for the same reason and under the same rule; see
    _ADDRESS_PLACEHOLDERS. This is the single choke point every consumer of
    an abstract address goes through — the selected row's own address
    verification, the candidate wrong-parcel guard, and the grantor-hit
    classifier all read it — so the fix reaches all three at once.
    """
    out = []
    for a in (abstract or {}).get("addresses") or []:
        if a.get("addr") and not _is_placeholder_address(a["addr"]):
            out.append(", ".join(x for x in (a["addr"], a.get("town")) if x))
    return out


# ---------------------------------------------------------------------------
# v3.23 — ALIS grantor-hit classification (the common-name pile, ALIS edition)
#
# Port of the Plymouth v3.21 trio. The blocker was always that the ALIS index
# carries no address column; v3.22 removed it — the Document Abstract answers
# "which parcel?" for one GET per hit, no PDF and no model call. Motivating
# run: Keegan / 402 Sedgefield St Weymouth (2026-08-12, log 2026-08-12-003) — the
# v3.20 town-scoped retries made the grantor check COMPLETE but returned 322
# instruments, every one of which had to be read by hand.
#
# NOTHING IS EVER DROPPED. Hits are classified and ORDERED; the same tier
# names, tags, and JSON shape as Plymouth (grantor_check.needs_review +
# .summary) so both registries read identically.
# ---------------------------------------------------------------------------

# Abstract GETs are cheap (one HTTP request, no download, no model call), so
# classification does NOT inherit _GRANTOR_HIT_SAMPLE_CAP = 5 — it fetches
# far more. The cap only bounds a pathological run; rows beyond it classify
# from town/type/date alone, which errs toward needs_review (safe direction).
_ALIS_CLASSIFY_ABSTRACT_CAP = 250
_ALIS_CLASSIFY_WORKERS = 8


def _alis_hit_town_matches(row_town: str, town_code: str, town_name: str) -> bool:
    """
    v3.23 — does an ALIS grantor-hit row's Town cell refer to the subject
    town? The grid usually renders the full proper-case name ("Cohasset"),
    but fixtures and some batches carry the 4-letter ALIS code ("WEYM"), so
    both the resolved code and the town name parsed from --base-name are
    tried. `*ALL` is a search scope, never a town — it matches nothing.
    """
    t = (row_town or "").strip().upper()
    if not t:
        return False
    code = (town_code or "").strip().upper()
    name = (town_name or "").strip().upper()
    if code and code != "*ALL":
        if t == code or _town_matches_filter(code, t):
            return True
    return bool(name) and _town_matches_filter(name, t)


def _alis_hit_address_note(result: dict, r: dict, address, st_num: str,
                           st_word: str, what: str) -> None:
    """
    Compare a grantor hit's known address to the subject street and append
    the appropriate note. v3.23 — hoisted from the STEP 8 closure so the
    classification pass emits the identical wording (single source for the
    CRITICAL / POSSIBLE / UNVERIFIED / different-parcel judgments).
    """
    if not (st_num and st_word):
        return
    rid = _alis_row_id(r)
    if not address:
        # v3.20 — null is MISSING INFORMATION, not a non-match (same class
        # as the Keegan candidate gap): the sampled page may just say "SEE
        # ATTACHED FULL LEGAL".
        ref = (f"--verify-grantor-hit {r['document_number']}"
               if r.get("land_court")
               else f"--verify-grantor-hit {r['book']}/{r['page']}")
        result["notes"].append(
            f"WARNING: grantor hit {rid} ({r['doc_type']} "
            f"{r['date_received']}): no property address could be "
            "extracted from the sampled page(s) — UNVERIFIED; do "
            "NOT dismiss it as a different parcel. Re-run with "
            f"{ref} to fetch and read the full instrument. [{what}]"
        )
        return
    if _alis_address_matches(st_num, st_word, address):
        result["notes"].append(
            f"CRITICAL: grantor hit {rid} ({r['doc_type']} "
            f"{r['date_received']}) conveys the SUBJECT property "
            f"({address}) — the seller has deeded the subject parcel "
            f"out. [{what}]"
        )
    elif _alis_street_word_matches(st_word, address):
        # v3.16 — street name matches but the number couldn't be
        # confirmed. NEVER dismiss this as a different parcel.
        ref = (f"--verify-grantor-hit {r['document_number']}"
               if r.get("land_court")
               else f"--verify-grantor-hit {r['book']}/{r['page']}")
        result["notes"].append(
            f"POSSIBLE SUBJECT PROPERTY: grantor hit {rid} "
            f"({r['doc_type']} {r['date_received']}) conveys "
            f"{address!r} — the street name matches '{st_word}' but "
            f"the street number could not be confirmed. Treat as a "
            f"likely deed-out until verified (re-run with {ref}). "
            f"[{what}]"
        )
    else:
        result["notes"].append(
            f"Grantor hit {rid} conveys {address!r}, which does not "
            f"match the subject street '{st_num} {st_word}' — likely "
            f"a different parcel of the seller's; verify before "
            f"flagging. [{what}]"
        )


def _certificates_match(a: str, b: str) -> bool:
    """
    v3.39 (item 22c) — do two Land Court certificate numbers name the same
    certificate? Compared as digits so "123456", "0123456" and "Ctf 123456"
    agree. Returns False whenever either side is missing or non-numeric
    (an LC abstract can carry "See parent list" instead of a number, and a
    death certificate's abstract carries no Ctf# at all): absence must never
    manufacture a match, in either direction.
    """
    da = "".join(ch for ch in str(a or "") if ch.isdigit()).lstrip("0")
    db = "".join(ch for ch in str(b or "") if ch.isdigit()).lstrip("0")
    return bool(da) and da == db


def _alis_classify_grantor_hit(row: dict, st_num: str, st_word: str,
                               town_code: str, town_name: str,
                               acq_date: tuple,
                               subject_certificate: str = "") -> dict:
    """
    v3.23 — classify ONE ALIS grantor-check hit against the subject parcel.
    Same tiers, tags, and needs_review rule as _plymouth_classify_grantor_hit
    (v3.21); the address comes from the registry abstract (attached to the
    row by _alis_classify_fetch_abstracts) instead of a grid cell.

    A row with NO abstract address is NEVER treated as a different parcel on
    that basis alone — it is only deprioritised when its TOWN also differs
    (the Keegan lesson: missing information is not a non-match). The index
    Desc cell can only ESCALATE a hit to possible_subject (it is staff-typed
    low-signal text like "STANTON ROAD" or "SEE RECORD"); it can never
    dismiss one, and never outranks a real abstract address.

    v3.39 (item 22c) — on REGISTERED LAND the certificate number outranks
    every address. It is the Land Court's own parcel key: exact, carried on
    every index row already, and needing no abstract fetch. Matching it is
    therefore checked FIRST, and it is the only signal here strong enough to
    assert `subject` on its own. It was simply never used — the classifier
    was address-only on both sections — which is how seven hits that all sat
    on the subject certificate got sorted by street address instead.

    Absence is still not an answer: a missing certificate on EITHER side
    falls through to the address/town logic rather than asserting anything.
    """
    addrs = row.get("abstract_addresses") or []
    town_match = _alis_hit_town_matches(row.get("town"), town_code, town_name)
    ctf_match = (row.get("land_court")
                 and _certificates_match(row.get("certificate"),
                                         subject_certificate))

    if ctf_match:
        # The Land Court parcel key matched. Nothing an address says can
        # move this row off the subject parcel.
        parcel = "subject"
    elif any(_alis_address_matches(st_num, st_word, a) for a in addrs):
        parcel = "subject"
    elif any(_alis_street_word_matches(st_word, a) for a in addrs):
        parcel = "possible_subject"
    elif addrs:
        parcel = "other_same_town" if town_match else "other_parcel"
    elif _alis_street_word_matches(st_word, row.get("doc_desc") or ""):
        parcel = "possible_subject"
    else:
        parcel = "unknown_same_town" if town_match else "other_town"

    row_date = _parse_deed_date(row.get("date_received") or "")
    # A row whose date will not parse is treated as post-acquisition — the
    # safe direction for a deed-out check.
    pre_acq = bool(acq_date > (0, 0, 0) and (0, 0, 0) < row_date < acq_date)
    dt = (row.get("doc_type") or "").strip()
    # v3.36 (item 0a): three-way. A blank type is 'unknown' — kept in
    # needs_review with the unknown-tier WARNING, no longer promoted all the
    # way to a CRITICAL deed-out. Same for unrecognised types (item 13).
    instrument_class = _classify_instrument(dt)
    conveyance = instrument_class == "conveyance"
    # v3.39 (item 22a) — the Desc cell goes to significance but NOT to
    # _classify_instrument. Escalating on free text is safe (it can only add
    # rows to needs_review); classifying a CONVEYANCE from it is not, and
    # the v3.23 rule that Desc may escalate but never dismiss still holds.
    significance = _instrument_significance(dt, row.get("doc_desc") or "")

    # v3.37 (item 18) — see _plymouth_classify_grantor_hit for the full
    # reasoning. Demote a post-acquisition conveyance out of needs_review
    # ONLY on positive evidence it sits elsewhere: an abstract address that
    # did not match, or a town cell that did not match. A row with neither
    # is NOT ruled out and stays — `other_town` is also where a row with a
    # BLANK town lands, and demoting that would be the v3.20 null-address
    # mistake in a new place.
    # Same rule as Plymouth: demote only on a TOWN mismatch with a town
    # actually indexed. `other_same_town` stays (same-town wrong-parcel
    # traps), and a blank town is not evidence — on ALIS a blank town
    # cannot match, so it lands in `other_town` alongside genuine
    # different-town rows; keying on the tier alone would drop it.
    located_elsewhere = (
        parcel in ("other_parcel", "other_town")
        and bool((row.get("town") or "").strip())
    )
    needs_review = (
        parcel in ("subject", "possible_subject", "unknown_same_town")
        # unknown counts like a conveyance here: membership must not shrink
        # for want of a recognised type.
        or (instrument_class != "non_conveyance" and not pre_acq
            and not located_elsewhere)
        # v3.38 — an instrument that can change WHO OWNS or WHO SIGNS is
        # never demoted for being a non-conveyance: a death certificate is
        # how a survivor takes title with no deed recorded.
        or (significance == "ownership_change" and not pre_acq
            and not located_elsewhere)
    )
    tag = _PLYMOUTH_HIT_TAGS[parcel] + (" | pre-acquisition" if pre_acq else "")
    return {
        "parcel": parcel,
        "pre_acquisition": pre_acq,
        "conveyance": conveyance,
        "instrument_class": instrument_class,
        "significance": significance,             # v3.38 ownership_change|burden|''
        "located_elsewhere": located_elsewhere,   # v3.37 (item 18) evidence
        "needs_review": needs_review,
        "tag": tag,
    }


def _alis_grantor_sort_key(row: dict) -> tuple:
    """
    v3.23 — order grantor hits most-relevant first (same rule as
    _plymouth_grantor_sort_key): subject parcel before unknown before other;
    post-acquisition before pre-acquisition; conveyances before
    non-conveyances; then newest first. On the Keegan set the rows that
    matter sit wherever the merged county-wide + town-scoped searches left
    them, 322 rows deep.
    """
    c = row.get("classification") or {}
    try:
        tier = _PLYMOUTH_HIT_TIERS.index(c.get("parcel", "other_town"))
    except ValueError:
        tier = len(_PLYMOUTH_HIT_TIERS)
    y, m, d = _parse_deed_date(row.get("date_received") or "")
    return (tier, c.get("pre_acquisition", False), not c.get("conveyance", False),
            -y, -m, -d)


def _alis_grantor_hit_str(r: dict) -> str:
    """
    v3.23 — one ALIS grantor-check hit as its report/JSON line. Same base
    format as v3.9; the abstract address and the classification tag are
    appended when known, so the parcel question reads straight off the line.
    """
    if r.get("land_court"):
        s = (f"Doc#{r['document_number']} Ctf#{r['certificate']} {r['doc_type']} "
             f"{r['date_received']} | Desc: {r['doc_desc']} | Ctl#: {r['ctl_num']}"
             f" | via: {r.get('via_search', '?')}")
    else:
        s = (f"Bk{r['book']}/{r['page']} {r['doc_type']} {r['date_received']} "
             f"| Grantee: {r['reverse_party']} | Desc: {r['doc_desc']} | Ctl#: {r['ctl_num']}"
             f" | via: {r.get('via_search', '?')}")
    addrs = r.get("abstract_addresses") or []
    if addrs:
        s += f" | Addr: {addrs[0]}"
        if len(addrs) > 1:
            s += f" (+{len(addrs) - 1} more)"
    c = r.get("classification")
    if c:
        s += f" | {c['tag']}"
    return s


def _alis_classify_fetch_abstracts(base_url: str, rows: list, acq_date: tuple,
                                   town_code: str, town_name: str,
                                   notes: list) -> None:
    """
    v3.23 — fetch registry abstracts, in parallel, for the grantor-check
    rows whose classification an address can actually change:

      (a) post-acquisition (or unparseable-date) conveyance hits — the
          deed-out candidates; the address decides subject vs elsewhere;
      (b) rows whose Town matches the subject town — the address moves them
          out of unknown_same_town (the tier that forces needs_review).

    Other-town non-conveyance and pre-acquisition rows classify to excluded
    tiers with no address, so no GET is spent on them. Land Court rows are
    included since v3.25 (LC09A/WSKYCD=D keying — same date+ctl fields).
    Each fetched row gains `_abstract` (cached for STEP 8),
    `abstract_addresses`, and `abstract_url`. Failures are aggregated into
    ONE note — a per-row note per failure would flood a 300-hit run when
    the registry hiccups.
    """
    need = []
    for r in rows:
        if "_abstract" in r:
            continue
        dt = (r.get("doc_type") or "").strip()
        # v3.36 (item 0a): grantor role — an UNKNOWN type must still get an
        # abstract fetched (it is the row most in need of an address, and
        # the wrapper's selection-role default would skip it).
        conv = _classify_instrument(dt) != "non_conveyance"
        rd = _parse_deed_date(r.get("date_received") or "")
        post = not (acq_date > (0, 0, 0) and (0, 0, 0) < rd < acq_date)
        if (conv and post) or _alis_hit_town_matches(r.get("town"), town_code,
                                                     town_name):
            prio = 0 if (conv and post) else 1
            need.append((prio, (-rd[0], -rd[1], -rd[2]), r))
    need.sort(key=lambda t: (t[0], t[1]))
    over_cap = len(need) - _ALIS_CLASSIFY_ABSTRACT_CAP
    todo = [t[2] for t in need[:_ALIS_CLASSIFY_ABSTRACT_CAP]]
    if not todo:
        return

    def _worker(chunk):
        s = requests.Session()
        for r in chunk:
            a = _alis_fetch_abstract_http(s, base_url, r)
            r["_abstract"] = a
            r["abstract_addresses"] = _alis_abstract_address_strings(a)
            r["abstract_url"] = a.get("url") if a else None

    workers = min(_ALIS_CLASSIFY_WORKERS, len(todo))
    chunks = [todo[i::workers] for i in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # list() so worker exceptions propagate to the caller's try/except.
        list(pool.map(_worker, chunks))

    with_addr = sum(1 for r in todo if r.get("abstract_addresses"))
    failed = sum(1 for r in todo if not r.get("_abstract"))
    notes.append(
        f"Grantor-hit classification (v3.23): fetched {len(todo)} registry "
        f"abstract(s) ({with_addr} carried an address"
        + (f", {failed} failed/empty" if failed else "")
        + ")"
        + (f"; {over_cap} lower-priority row(s) beyond the "
           f"{_ALIS_CLASSIFY_ABSTRACT_CAP}-abstract cap classified from "
           "town/type/date alone" if over_cap > 0 else "")
        + ". Other-town non-conveyance and pre-acquisition rows need no "
        "address to classify."
    )


def _alis_finalize_grantor_check(result: dict, rows: list, base_name: str,
                                 town_code: str, base_url: str) -> None:
    """
    v3.23 — classify, order and summarise the ALIS grantor-check hits,
    mutating `result` in place (Plymouth v3.21 parity — same JSON shape:
    grantor_check.deeds ordered most-relevant first with parcel tags,
    .needs_review, .summary).

    NOTHING IS DROPPED. ALIS full-name hits include the seller's own
    mortgages, homesteads and liens (they are not type-filtered), so hits
    are classified and ordered, never filtered out.

    Classification needs a street parsed from --base-name; without one
    (entity sellers, unparseable base names) every hit is left unclassified
    and reported for manual assessment exactly as before v3.23.

    Per-hit notes are emitted here ONLY for subject / possible-subject hits,
    via the same _alis_hit_address_note wording the sampler uses; rows this
    pass has assessed are marked `_class_noted` so STEP 8 does not repeat
    the note for its sampled subset.
    """
    st_num, st_word = _parse_street_from_base_name(base_name)
    town_name = _parse_town_from_base_name(base_name)
    acq_date = _parse_deed_date(result.get("recorded_date") or "")
    gc = result["grantor_check"]
    classified = bool(st_num and st_word)
    if classified:
        try:
            _alis_classify_fetch_abstracts(base_url, rows, acq_date,
                                           town_code, town_name,
                                           result["notes"])
        except Exception as e:
            result["notes"].append(
                f"Grantor-hit abstract fetch failed (non-fatal — hits with "
                f"no fetched address classify as parcel-unknown, which stays "
                f"in needs_review): {e}"
            )
        for r in rows:
            r["classification"] = _alis_classify_grantor_hit(
                r, st_num, st_word, town_code, town_name, acq_date,
                result.get("certificate_of_title") or "")
        rows.sort(key=_alis_grantor_sort_key)
    else:
        result["notes"].append(
            "Grantor-hit classification skipped: no street number/name parsed "
            "from the base name — every hit below must be assessed manually "
            "by parcel."
        )

    gc["deeds"] = [_alis_grantor_hit_str(r) for r in rows]
    review = [r for r in rows
              if not classified or r["classification"]["needs_review"]]
    gc["needs_review"] = [_alis_grantor_hit_str(r) for r in review]

    if classified:
        counts = {t: 0 for t in _PLYMOUTH_HIT_TIERS}
        for r in rows:
            counts[r["classification"]["parcel"]] += 1
        gc["summary"] = {
            "total": len(rows),
            "needs_review": len(review),
            "pre_acquisition": sum(
                1 for r in rows if r["classification"]["pre_acquisition"]),
            # v3.37 (item 18) — how many post-acquisition conveyance-type
            # hits were kept OUT of needs_review because an address or town
            # positively located them at another parcel. This is the
            # evidence behind a short review set: without it, "needs_review
            # is small" and "the classifier lost rows" look identical.
            "demoted_located_elsewhere": sum(
                1 for r in rows
                if r["classification"].get("located_elsewhere")
                and not r["classification"]["needs_review"]
                and r["classification"]["instrument_class"] != "non_conveyance"
                and not r["classification"]["pre_acquisition"]),
            **counts,
        }
        # Subject / possible-subject notes — same wording as the sampler.
        # A conveyance at the subject parcel recorded on/after the
        # acquisition date is the deed-out this whole check exists to find.
        for r in rows:
            c = r["classification"]
            if c["pre_acquisition"]:
                continue
            addrs = r.get("abstract_addresses") or []
            if c["parcel"] == "subject" and c["conveyance"]:
                matched = next(
                    (a for a in addrs
                     if _alis_address_matches(st_num, st_word, a)), None)
                _alis_hit_address_note(result, r, matched, st_num, st_word,
                                       "registry abstract")
                r["_class_noted"] = True
            elif c["parcel"] == "subject" and c.get("instrument_class") == "unknown":
                # v3.36 (item 0a): the middle tier. Before this, an
                # unrecognised type here fired the CRITICAL deed-out note —
                # a false alarm costing a browser verification trip
                # (item 13). One line to read instead of a browser session.
                result["notes"].append(
                    f"WARNING: grantor hit {_alis_row_id(r)} has UNRECOGNISED "
                    f"type {r['doc_type']!r} ({r['date_received']}) at the "
                    "SUBJECT property — not classified. Read the instrument "
                    "(or its abstract) to determine whether it conveys or "
                    "encumbers, and add the type to the script vocabulary so "
                    "future runs classify it."
                )
                r["_class_noted"] = True
            elif c["parcel"] == "subject":
                # v3.38 — same elevation as the Plymouth dispatcher.
                sig_note = _significance_note(
                    _alis_row_id(r), r.get("doc_type"), r.get("date_received"),
                    "", r.get("doc_desc") or "")
                result["notes"].append(sig_note or (
                    f"Grantor hit {_alis_row_id(r)} ({r['doc_type']} "
                    f"{r['date_received']}) affects the SUBJECT property but "
                    "is not a conveyance — assess as an encumbrance "
                    "(homestead/lien/mortgage), not as a deed-out."
                ))
                r["_class_noted"] = True
            elif c["parcel"] == "possible_subject" and c["conveyance"]:
                addr = next(
                    (a for a in addrs
                     if _alis_street_word_matches(st_word, a)), None)
                # Escalated from the index Desc cell when no abstract
                # address exists — the note cites what triggered it.
                what = "registry abstract" if addr else "index Desc"
                _alis_hit_address_note(
                    result, r, addr or (r.get("doc_desc") or "").strip(),
                    st_num, st_word, what)
                r["_class_noted"] = True
        s = gc["summary"]
        result["notes"].append(
            f"Grantor check: {s['total']} instrument(s) found; "
            f"{s['needs_review']} need review (subject parcel: {s['subject']}, "
            f"possible subject: {s['possible_subject']}, unknown parcel in "
            f"the subject town: {s['unknown_same_town']}, plus any "
            f"post-acquisition conveyance that could NOT be located "
            f"elsewhere). The other "
            f"{s['total'] - s['needs_review']} are other parcels/towns or "
            "pre-acquisition and are still listed in full in "
            "grantor_check.deeds, ordered most-relevant first. READ "
            "grantor_check.needs_review FIRST. A 'parcel unknown' tag means "
            "no address was available from the registry abstract — that row "
            "was NOT ruled out. Rows 'via: ... (surname only)' may still be "
            "same-surname strangers — verify the grantor's first name before "
            "flagging one as the seller's."
            + (f" {s['demoted_located_elsewhere']} post-acquisition "
               "conveyance-type hit(s) were kept OUT of the review set because "
               "the registry abstract or town cell positively located them at "
               "a DIFFERENT parcel — they are still in grantor_check.deeds; a "
               "row with no locating information at all is never demoted."
               if s.get("demoted_located_elsewhere") else "")
        )
    else:
        gc["summary"] = None
        result["notes"].append(
            f"Grantor check: {len(rows)} instrument(s) found — "
            "Claude must assess title flags. Rows 'via: <last>, <first>' are "
            "the seller. Rows 'via: ... (co-owner from deed)' are a "
            "co-owner named on the deed — their subsequent instruments "
            "affect this parcel's title. Rows 'via: ... (surname only)' "
            "are conveyance-type ONLY (v3.11) and may still be "
            "same-surname strangers — verify the grantor's first name "
            "and the property before flagging one; do NOT report a "
            "surname-only row as the seller's encumbrance."
        )


# ---------------------------------------------------------------------------
# Inline PDF extraction (v3.10) — Claude API reads the scanned deed so the
# conversation doesn't have to. ALIS PDFs are image-based scans (no text
# layer), so this requires a multimodal model; local parsers return nothing.
# ---------------------------------------------------------------------------

# v3.16 — two extraction tiers. The MAIN deed (and --verify-grantor-hit
# full extractions) carry the verbatim legal description and stay on the
# strongest reader; page-1 samples only need an address + party names and
# run on the fast model (with a one-shot main-model fallback on failure).
#
# These are defaults, not pins. Override per run with --model-main /
# --model-light, or set MA_REGISTRY_MODEL_MAIN / MA_REGISTRY_MODEL_LIGHT in
# the environment, so a newer model can be adopted without editing the script.
_EXTRACT_MODEL_MAIN_DEFAULT  = "claude-opus-4-8"
_EXTRACT_MODEL_LIGHT_DEFAULT = "claude-haiku-4-5-20251001"

_EXTRACT_MODEL_MAIN = os.environ.get(
    "MA_REGISTRY_MODEL_MAIN", _EXTRACT_MODEL_MAIN_DEFAULT)
_EXTRACT_MODEL_LIGHT = os.environ.get(
    "MA_REGISTRY_MODEL_LIGHT", _EXTRACT_MODEL_LIGHT_DEFAULT)

_DEED_SCHEMA = {
    "type": "object",
    "properties": {
        "legal_description": {
            "type": ["string", "null"],
            "description": (
                "The full legal description of the premises, transcribed "
                "verbatim from the body of the deed: metes and bounds, lot "
                "and plan references, condominium unit recitals including "
                "the master deed reference, appurtenant rights, and any "
                "'subject to' clauses that are part of the description. "
                "Preserve the original wording and punctuation EXACTLY — "
                "do not correct apparent typos or unusual punctuation. "
                "Preserve the instrument's line breaks as newline "
                "characters and its paragraph breaks as blank lines, so "
                "the text can be checked line-for-line against the page "
                "images. "
                "STOP AT THE END OF THE DESCRIPTION. Do NOT include: the "
                "homestead release or declaration; the execution, signature, "
                "witness, notary or acknowledgment blocks; the recording or "
                "excise stamp; or the derivation clause ('Meaning and "
                "intending to convey the same premises conveyed to the "
                "grantor by deed recorded at ...'), which is captured "
                "separately in prior_deed_reference. Those follow the "
                "description rather than forming part of it, and including "
                "them makes the output vary between runs of the same deed. "
                "Null only if no legal description appears."
            ),
        },
        "property_address": {
            "type": ["string", "null"],
            "description": (
                "The property street address as stated on the deed — from "
                "the granting clause, the left-margin/property notation, or "
                "the cover sheet. Include town. Null if no address appears "
                "anywhere on the instrument."
            ),
        },
        "document_number": {
            "type": ["string", "null"],
            "description": (
                "The registry document/instrument number, e.g. the '#NNNNN' "
                "on a Norfolk recording-stamp header, 'Ctrl#' on a "
                "Barnstable cover, or 'Doc#' on a Land Court instrument."
            ),
        },
        "certificate_of_title": {
            "type": ["string", "null"],
            "description": (
                "Land Court (Registered Land) only: the certificate this "
                "instrument is NOTED ON — the number on the cover sheet's "
                "'Noted on Certificate' line (or a registrar's notation to "
                "the same effect). This is NOT the same as a certificate "
                "recited in the body or in the property description: that "
                "one is the certificate the land is DESCRIBED on, i.e. the "
                "one being conveyed OUT of, and reporting it here would "
                "cite the wrong certificate. If the instrument recites a "
                "certificate but has no 'Noted on Certificate' line, return "
                "null rather than the recited number. Null for Recorded "
                "Land instruments."
            ),
        },
        "consideration": {
            "type": ["string", "null"],
            "description": (
                "The consideration as stated in the granting clause ('for "
                "consideration paid and in full consideration of $X'). "
                "Cross-check against a cover-sheet 'Cons:' figure if "
                "present; report the granting-clause amount and note any "
                "discrepancy in title_flags."
            ),
        },
        "signing_date": {
            "type": ["string", "null"],
            "description": (
                "The date the deed was executed/signed (e.g. 'Executed "
                "under seal this Xth day of MONTH, YYYY' on the signature "
                "page), in MM-DD-YYYY form."
            ),
        },
        "recording_stamp": {
            "type": ["string", "null"],
            "description": (
                "The recording identifiers stamped on the instrument, used "
                "to sanity-check that the right document was downloaded. "
                "RECORDED LAND: the book and page from the margin stamp, "
                "header, or cover sheet (e.g. 'Bk 34918 Pg 103'). "
                "REGISTERED LAND (Land Court) HAS NO BOOK AND PAGE — report "
                "the Document Number and the 'Noted on Certificate' number "
                "instead (e.g. 'Doc 812445, Noted on Certificate 198332'), "
                "plus the 'Land Court Book and Page' registration reference "
                "if one is printed. Never report a Land Court registration "
                "book/page as though it were a Recorded Land book and page. "
                "Null if none visible."
            ),
        },
        "grantors_full": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Every grantor's full name exactly as written, including "
                "middle names/initials and capacity language ('John A. "
                "Smith, individually and as Trustee of the Smith Family "
                "Trust')."
            ),
        },
        "grantees_full": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Every grantee's full name exactly as written, including "
                "middle names/initials and capacity language."
            ),
        },
        "tenancy": {
            "type": ["string", "null"],
            "description": (
                "The tenancy in which the grantees take title, verbatim: "
                "'as joint tenants with rights of survivorship', 'as "
                "tenants by the entirety', 'as tenants in common', etc. "
                "Null if the deed is silent (single grantee or unstated)."
            ),
        },
        "prior_deed_reference": {
            "type": ["string", "null"],
            "description": (
                "The derivation clause: 'Being the same premises conveyed "
                "to the grantor by deed ... recorded at Book NNNN, Page "
                "NNN' (or a Land Court document/certificate reference)."
            ),
        },
        "title_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Anything a closing attorney should notice: trust vesting "
                "or trustee-authority recitals, divorce-action recitals, "
                "tenancy-in-common-only conveyances, homestead releases or "
                "declarations, estate/probate references, life estates, "
                "mortgage payoff references, consideration discrepancies, "
                "handwritten alterations. Empty array if clean."
            ),
        },
    },
    "required": [
        "legal_description", "property_address", "document_number",
        "certificate_of_title", "consideration", "signing_date",
        "recording_stamp", "grantors_full", "grantees_full", "tenancy",
        "prior_deed_reference", "title_flags",
    ],
    "additionalProperties": False,
}

# Lighter schema for multiple_deed_candidates page-1 samples — just enough
# to verify which candidate is the subject property.
_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "property_address": {
            "type": ["string", "null"],
            "description": (
                "The property street address (with town) as stated on this "
                "deed page — granting clause, margin notation, or cover "
                "sheet. Null if page 1 shows no address."
            ),
        },
        "lot_or_unit": {
            "type": ["string", "null"],
            "description": "Lot number, unit number, or plan reference if stated.",
        },
        "grantees": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Grantee names as written on this page.",
        },
    },
    "required": ["property_address", "lot_or_unit", "grantees"],
    "additionalProperties": False,
}

# Light schema for grantor-check hit page-1 samples (v3.15) — enough to
# tell whether a suspected deed-out conveys the subject parcel, and by whom.
_GRANTOR_HIT_SCHEMA = {
    "type": "object",
    "properties": {
        "property_address": {
            "type": ["string", "null"],
            "description": (
                "The property street address (with town) as stated on this "
                "instrument page — granting clause, margin notation, or "
                "cover sheet. Null if page 1 shows no address."
            ),
        },
        "lot_or_unit": {
            "type": ["string", "null"],
            "description": "Lot number, unit number, or plan reference if stated.",
        },
        "grantors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Grantor names as written on this page.",
        },
        "grantees": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Grantee names as written on this page.",
        },
    },
    "required": ["property_address", "lot_or_unit", "grantors", "grantees"],
    "additionalProperties": False,
}

# v3.15 — page-1 samples are fetched for at most this many conveyance-type
# grantor-check hits per run (each costs a download + an API extraction).
_GRANTOR_HIT_SAMPLE_CAP = 5

_EXTRACT_SYSTEM = (
    "You extract structured title data from scanned Massachusetts Registry "
    "of Deeds instruments (Browntech ALIS registries such as Norfolk and "
    "Barnstable serve PDFs; Avenu registries such as Plymouth serve page "
    "images). The attached pages together form ONE recorded "
    "instrument, in page order; the first page is usually a registry cover "
    "sheet or bears the recording stamp. Transcribe fields exactly as "
    "written on the instrument — do not paraphrase, normalize names, or "
    "infer facts that are not on the page. Use null for anything not "
    "present. These are scans: read stamps, margins, and handwriting "
    "carefully."
)


def _anthropic_client():
    """
    Construct the Anthropic client, or return (None, reason) if extraction
    cannot run (SDK missing / no credentials).

    v3.27 — credentials are checked HERE rather than left to surface on the
    first request. The docstring used to say a credentials problem "may
    only surface on the first request"; measured against the installed SDK,
    that is what always happens: `Anthropic()` constructs fine with
    ANTHROPIC_API_KEY unset (api_key=None) or empty (api_key=''), and only
    raises "Could not resolve authentication method" when a request is
    sent. So this probe reported a usable client on a keyless machine, and
    the run did a full search before failing — which is precisely the
    experience the claude-code mode exists to avoid. Checking the resolved
    api_key/auth_token makes the probe honest, so `--extraction auto`
    degrades up front and `--extraction api` errors up front.
    """
    if anthropic is None:
        return None, "anthropic SDK not installed (python -m pip install anthropic)"
    try:
        client = anthropic.Anthropic(timeout=180.0, max_retries=2)
    except Exception as e:
        return None, f"Anthropic client init failed: {e}"
    if not (getattr(client, "api_key", None) or getattr(client, "auth_token", None)):
        return None, ("no Anthropic credentials — set ANTHROPIC_API_KEY in "
                      "the environment")
    return client, None


def _extraction_fatal_reason(exc) -> str:
    """
    v3.28 — is this extraction failure one that will recur for every
    remaining call in this run (account/credentials/model), as opposed to a
    per-document or transient one? Returns a short reason, or "" if the
    failure is worth retrying on the next document.

    Salgado / 87 Marchmont St Hyannis (2026-08-12): a valid API key on an account
    with no credit returned HTTP 400 `invalid_request_error: "Your credit
    balance is too low"`. v3.27's pre-flight probe passed — credentials
    resolved fine — so the run made the same doomed call for the main deed
    and for every candidate sample, each failing identically. A present key
    is not a usable key; the honest response to the first such answer is to
    stop asking and hand the PDFs to Claude, which is what claude-code mode
    does by design.

    Deliberately NOT fatal: rate limits, timeouts, connection errors,
    refusals and max_tokens — those are per-request or transient, and
    giving up on the whole run for one of them would lose extractions that
    would have succeeded.
    """
    status = getattr(exc, "status_code", None)
    if status in (401, 402, 403, 404):
        return f"HTTP {status}: {exc}"
    msg = str(exc)
    if status == 400 and re.search(
            r"credit balance|billing|quota|payment|purchase credits",
            msg, re.I):
        return f"HTTP 400: {exc}"
    if anthropic is not None:
        fatal_types = tuple(
            t for t in (
                getattr(anthropic, "AuthenticationError", None),
                getattr(anthropic, "PermissionDeniedError", None),
            ) if t is not None
        )
        if fatal_types and isinstance(exc, fatal_types):
            return str(exc)
    return ""


# v3.27 — what the run still does with no Claude API. Worth stating
# plainly, because it changed a lot: before v3.22 the wrong-parcel guard
# was gated on PDF extraction, so a keyless run lost its main safety
# check. Abstracts (v3.22/v3.25) and index-based classification (v3.23)
# moved that work off the model entirely.
_NO_API_STILL_WORKS = (
    "Unaffected without the API: the grantee search and deed selection, "
    "the registry-abstract address check (the wrong-parcel guard and "
    "auto-retarget, v3.22/v3.25), the grantor check with its needs_review "
    "classification (v3.23), cross-references (v3.26), and the deed PDF "
    "downloads themselves."
)
_NO_API_DEGRADES = (
    "What you must do by hand: (1) Read the downloaded deed PDFs to get "
    "the legal description and the deed's own field values — that is the "
    "one job the API was doing; (2) for any candidate or grantor hit whose "
    "registry abstract carried no address, Read its `sample_file` page-1 "
    "PDF to answer the which-parcel question. To have this done "
    "automatically in one API call instead, set ANTHROPIC_API_KEY and re-run "
    "with the default --extraction auto."
)


def _resolve_extraction_mode(requested: str):
    """
    v3.27 — resolve `--extraction {auto,api,claude-code}` into
    (extract_pdf, mode, note, error).

      auto (default)  Use the Claude API when a client is available,
                      otherwise fall back to claude-code mode with a
                      friendly note. This keeps a key-holder's single-shot
                      run unchanged while making a keyless install work
                      out of the box instead of emitting an
                      `extraction_error`.
      api             Force the API. Missing SDK/credentials is a hard,
                      actionable error rather than a silent degrade — the
                      caller asked for it explicitly.
      claude-code     Force no-API. This is a MODE, NOT A FAILURE: no
                      `extraction_error` is set, and the notes tell Claude
                      to Read the PDFs.

    Returns (extract_pdf: bool, mode: str, note: str|None, error: str|None).
    """
    if requested == "claude-code":
        return False, "claude-code", (
            "Extraction mode: claude-code (no Claude API call). This is a "
            "mode, not a failure. " + _NO_API_DEGRADES + " " +
            _NO_API_STILL_WORKS
        ), None

    client, reason = _anthropic_client()
    if requested == "api":
        if client is None:
            return False, "api", None, (
                f"--extraction api was requested but the Claude API is not "
                f"available: {reason}. Set ANTHROPIC_API_KEY (and "
                f"`python -m pip install anthropic`), or re-run with "
                f"--extraction claude-code to have Claude read the deed "
                f"PDFs instead. No search was performed."
            )
        return True, "api", None, None

    # auto
    if client is None:
        return False, "claude-code", (
            f"Extraction mode: claude-code — the Claude API is unavailable "
            f"({reason}), so the run continues without it. This is expected "
            f"and supported, not an error. " + _NO_API_DEGRADES + " " +
            _NO_API_STILL_WORKS + " (Pass --extraction api to make a missing "
            "key a hard error instead.)"
        ), None
    return True, "api", None, None


# v3.47 (47b) — the browser registries (Plymouth, Middlesex South, Suffolk)
# save deed pages as images, not PDFs. Extension → image media type; a
# file not listed here is sent as a PDF.
_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
}


def _extract_pdf_fields(client, pdf_paths: list, schema: dict,
                        instruction: str,
                        model: str = _EXTRACT_MODEL_MAIN) -> dict:
    """
    Send the given pages of one instrument (PDFs, or page images since
    v3.47) to Claude with a structured-output schema and return the parsed
    field dict. Raises on API/parse failure — callers wrap.
    """
    content = []
    for p in pdf_paths:
        data = base64.standard_b64encode(Path(p).read_bytes()).decode("utf-8")
        media = _IMAGE_MEDIA_TYPES.get(Path(p).suffix.lower())
        if media:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media,
                           "data": data},
            })
        else:
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": data},
            })
    content.append({"type": "text", "text": instruction})

    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=_EXTRACT_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("extraction request was refused")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("extraction output truncated (max_tokens)")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _extract_pdf_fields_light(client, pdf_paths: list, schema: dict,
                              instruction: str) -> dict:
    """
    v3.16 — page-1 sample extraction on the fast model, retried once on
    the main model on any failure so a light-model hiccup can't blind the
    address checks. Raises only if BOTH attempts fail.
    """
    try:
        return _extract_pdf_fields(client, pdf_paths, schema, instruction,
                                   model=_EXTRACT_MODEL_LIGHT)
    except Exception:
        return _extract_pdf_fields(client, pdf_paths, schema, instruction,
                                   model=_EXTRACT_MODEL_MAIN)


def _mark_extraction_unavailable(result: dict, exc) -> None:
    """
    v3.28 — on the first extraction failure that will recur for the rest of
    the run (see _extraction_fatal_reason), latch it on the result so the
    later extraction sites — the auto-retarget's re-extraction, the
    grantor-hit page-1 samples, and --verify-grantor-hit — skip their calls
    and tell Claude to Read the PDFs instead. Behaviourally the run
    finishes in claude-code mode; `extraction_mode` still reports what was
    resolved pre-flight, and `extraction_error` stays set because this one
    IS a failure, not the chosen mode.

    Idempotent: only the first fatal failure is recorded.
    """
    if result.get("extraction_unavailable"):
        return
    reason = _extraction_fatal_reason(exc)
    if not reason:
        return
    result["extraction_unavailable"] = reason
    result["notes"].append(
        "EXTRACTION UNAVAILABLE for the rest of this run — the Claude API "
        f"returned an error that will recur for every remaining call: "
        f"{reason}. Skipping the remaining extraction calls (candidate and "
        "grantor-hit samples, verification) rather than repeating a failing "
        "one. " + _NO_API_DEGRADES + " " + _NO_API_STILL_WORKS
    )
    if result.get("files"):
        result["notes"].append(
            "READ THE DEED PDFs to extract the legal description and deed "
            "fields (extraction degraded to claude-code mode): "
            + ", ".join(Path(f).name for f in result["files"])
        )


def _run_pdf_extraction(result: dict, land_court: bool) -> None:
    """
    v3.10 — extract structured fields from the downloaded deed PDFs and the
    multi-candidate page-1 samples, concurrently. Mutates `result` in place:
    populates result["pdf_extraction"], promotes high-value fields to the
    top level, fills index nulls, and annotates candidate entries with
    "sample_extraction". Fails soft: on any error sets
    result["extraction_error"] and a fallback note; never raises.
    """
    client, reason = _anthropic_client()
    if client is None:
        result["extraction_error"] = reason
        result["notes"].append(
            f"PDF extraction skipped ({reason}) — Claude should Read the "
            "PDFs to extract the legal description and deed details."
        )
        return

    deed_instruction = (
        "Extract the requested fields from this "
        + ("Land Court (Registered Land)" if land_court else "Recorded Land")
        + " instrument."
    )

    jobs = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs["deed"] = pool.submit(
            _extract_pdf_fields, client, result["files"], _DEED_SCHEMA,
            deed_instruction,
        )
        for i, cand in enumerate(result.get("multiple_deed_candidates") or []):
            # v3.14 — skip candidates already extracted (the auto-retarget
            # re-run extracts only the newly selected main deed).
            if (cand.get("sample_file") and not cand.get("selected")
                    and not cand.get("sample_extraction")):
                jobs[f"cand{i}"] = pool.submit(
                    _extract_pdf_fields_light, client, [cand["sample_file"]],
                    _CANDIDATE_SCHEMA,
                    "This is page 1 of a candidate deed. Extract the "
                    "property address, lot/unit, and grantees so the "
                    "subject property can be identified.",
                )

        # Main deed
        try:
            fields = jobs["deed"].result()
            result["pdf_extraction"] = {"model": _EXTRACT_MODEL_MAIN, "fields": fields}
            result["legal_description"]  = fields.get("legal_description")
            result["signing_date"]       = fields.get("signing_date")
            result["grantors_full"]      = fields.get("grantors_full") or []
            result["grantees_full"]      = fields.get("grantees_full") or []
            result["tenancy"]            = fields.get("tenancy")
            result["prior_deed_reference"] = fields.get("prior_deed_reference")
            result["title_flags"]        = fields.get("title_flags") or []
            result["deed_property_address_pdf"] = fields.get("property_address")
            result["recording_stamp"]    = fields.get("recording_stamp")
            if not result.get("consideration"):
                result["consideration"] = fields.get("consideration")
            if not result.get("document_number"):
                result["document_number"] = fields.get("document_number")
            if not result.get("certificate_of_title"):
                result["certificate_of_title"] = fields.get("certificate_of_title")
            result["notes"].append(
                f"PDF extraction ({_EXTRACT_MODEL_MAIN}): OK — legal description "
                f"{'present' if fields.get('legal_description') else 'NOT FOUND'}, "
                f"address: {fields.get('property_address') or 'n/a'}, "
                f"stamp: {fields.get('recording_stamp') or 'n/a'}"
                + (f", title flags: {len(fields.get('title_flags') or [])}"
                   if fields.get("title_flags") else "")
            )
        except Exception as e:
            result["extraction_error"] = f"{type(e).__name__}: {e}"
            result["notes"].append(
                "PDF extraction FAILED for the main deed — Claude should "
                f"Read the PDFs instead. ({result['extraction_error']})"
            )
            _mark_extraction_unavailable(result, e)

        # Candidate samples
        for i, cand in enumerate(result.get("multiple_deed_candidates") or []):
            job = jobs.get(f"cand{i}")
            if job is None:
                continue
            try:
                cand["sample_extraction"] = job.result()
            except Exception as e:
                cand["sample_extraction"] = {"error": f"{type(e).__name__}: {e}"}
                _mark_extraction_unavailable(result, e)


def _stamp_matches_selection(stamp: str, book, page, *,
                             land_court: bool = False,
                             document_number=None,
                             certificate=None,
                             lc_book_page=None) -> str:
    """
    v3.47, extended v3.48 (item 42) — does the recording stamp read off the
    page images name the SELECTED instrument? Returns "match" | "mismatch" |
    "unknown". Token match, so 'Bk: 12345 Pg: 678' and 'Book 12345, Page
    678' both pass; a stamp naming a different instrument means the viewer
    served something other than the row that was clicked.

    REGISTERED LAND HAS NO BOOK AND PAGE. The v3.47 check returned False
    whenever either was falsy, so porting it to Suffolk unchanged would have
    fired "the viewer may have served a different instrument" on every
    CORRECT Land Court run — and Suffolk is the one registry that routinely
    lands in Land Court, which is the whole reason --office exists. A
    warning that cries wolf on every run is worse than no warning. A Land
    Court instrument is keyed instead on its Document Number (the Suffolk
    cover sheet prints it twice: "Document Number : 812445" and "Doc#
    00812445"), corroborated by "Noted on Certificate" and by the "Land
    Court Book and Page" registration reference. Any one of those matching
    is a match; a stamp naming none of them is a mismatch.

    "unknown" is NOT a mismatch — it means the check could not run (no
    stamp, a stamp with no digits, or nothing to check it against, as on an
    older paper filing with no cover sheet). A check that cannot run must
    say so rather than warn.
    """
    toks = {t.lstrip("0") or "0" for t in re.findall(r"\d+", str(stamp or ""))}
    if not toks:
        return "unknown"

    def _n(v):
        digits = re.sub(r"\D", "", str(v or ""))
        return (digits.lstrip("0") or "0") if digits else None

    if land_court:
        checks = []
        for ident in (document_number, certificate):
            n = _n(ident)
            if n:
                checks.append(n in toks)
        # The registration book/page is a PAIR — both halves must appear,
        # or "148" alone would match almost any stamp by accident.
        pair = [t.lstrip("0") or "0"
                for t in re.findall(r"\d+", str(lc_book_page or ""))]
        if len(pair) == 2:
            checks.append(all(p in toks for p in pair))
        if not checks:
            return "unknown"
        return "match" if any(checks) else "mismatch"

    if not (book and page):
        return "unknown"
    return "match" if (_n(book) in toks and _n(page) in toks) else "mismatch"


def _timings_add_stage(result: dict, label: str, seconds: float,
                       wall_seconds: float = None) -> None:
    """
    v3.47 — append a stage measured OUTSIDE the runner (inline extraction
    happens in main(), after the runner has already finished its timings)
    to the finished timings block. Swallows everything: a timing bug must
    never be able to fail a run.

    v3.54 (item 57) — `wall_seconds` is what the stage added to the run's
    wall clock when that differs from its own duration: an extraction that
    ran alongside the grantor check lists its full `seconds` but adds only
    the time main() spent waiting for it to finish. Without this the total
    would count the overlapped seconds twice and hide the saving.
    """
    try:
        t = result.get("timings")
        if not t:
            return
        stage = {"stage": label, "seconds": round(seconds, 2)}
        if wall_seconds is not None:
            stage["wall_seconds"] = round(wall_seconds, 2)
        t["stages"].append(stage)
        add = seconds if wall_seconds is None else wall_seconds
        t["total_seconds"] = round(t["total_seconds"] + add, 2)
        t["slowest"] = max(t["stages"], key=lambda s: s["seconds"])
    except Exception:
        pass


class _ImageExtractionPrefetch:
    """
    v3.54 (item 57) — start a browser registry's deed extraction as soon as
    the page images are on disk, so the Claude API call runs WHILE the
    grantor check does, not after it.

    Why this is safe: on Plymouth, Middlesex South and Suffolk the grantor
    check takes its names from the INDEX (the named seller plus the detail
    panel's grantees) and reads no extracted field, and nothing after the
    image step changes result["files"]. ALIS already overlaps the other way
    round (v3.16 prefetches grantor searches during extraction).

    The worker never touches the live result. It extracts into a SHADOW
    copy with its own notes list, because the runner is appending notes
    and rewriting keys (grantor_check, status) on the other thread the
    whole time. join() then copies back only the keys the extraction
    itself changed, and appends its notes after the runner's. The files
    list is snapshotted at start; if it no longer matches at join, the
    prefetched fields describe different images and are thrown away —
    the caller then extracts synchronously exactly as before.

    Only the API call moves. The stamp, address and Land Court certificate
    checks stay on the main thread after join(), so they still see the
    runner's final book/page/document number.
    """

    def __init__(self) -> None:
        self._pool = None
        self._future = None
        self._files = None
        self._land_court = None

    @property
    def started(self) -> bool:
        return self._future is not None

    def start(self, result: dict) -> None:
        """Called by a runner right after its image step. Never raises."""
        try:
            if self._future is not None or not result.get("files"):
                return
            files = list(result["files"])
            shadow = dict(result)
            shadow["files"] = files
            shadow["notes"] = []
            before = dict(shadow)
            land_court = bool(result.get("land_court"))

            def _work():
                t0 = time.perf_counter()
                _run_pdf_extraction(shadow, land_court=land_court)
                changed = {k: v for k, v in shadow.items()
                           if k != "notes" and (k not in before
                                                or v is not before[k])}
                return changed, shadow["notes"], time.perf_counter() - t0

            self._files = files
            self._land_court = land_court
            self._pool = ThreadPoolExecutor(max_workers=1)
            self._future = self._pool.submit(_work)
        except Exception:
            self._future = None     # join() reports not-started; caller runs it inline

    def join(self, result: dict):
        """
        Wait for the worker and merge its output into `result`. Returns
        (seconds_extracting, seconds_waited), or None when there is nothing
        usable to merge — never started, failed, or stale — in which case
        the caller must extract synchronously. Never raises.
        """
        if self._future is None:
            return None
        try:
            t0 = time.perf_counter()
            changed, notes, secs = self._future.result()
            waited = time.perf_counter() - t0
            if (list(result.get("files") or []) != self._files
                    or bool(result.get("land_court")) != self._land_court):
                result.setdefault("notes", []).append(
                    "NOTE: the early (overlapped) extraction was discarded — "
                    "the page images or the section (Recorded Land / Land "
                    "Court) changed after it started; extracting again on "
                    "the final selection.")
                return None
            result.update(changed)
            result.setdefault("notes", []).extend(notes)
            return secs, waited
        except Exception as e:
            result.setdefault("notes", []).append(
                f"NOTE: the early (overlapped) extraction failed to complete "
                f"({type(e).__name__}: {e}); extracting again inline.")
            return None
        finally:
            try:
                self._pool.shutdown(wait=False)
            except Exception:
                pass


def _run_image_extraction(result: dict, *, extract_pdf: bool,
                          extraction_mode: str, mode_note,
                          street_number: str, street_name: str,
                          land_court: bool = False,
                          stage_label: str = "STEP 6 - inline extraction",
                          prefetch: "_ImageExtractionPrefetch" = None) -> None:
    """
    v3.47 (47b) — inline extraction for a browser registry whose deed pages
    arrive as IMAGES. Same _run_pdf_extraction, same --extraction gating,
    same claude-code note naming the files to Read; plus two post-checks
    aimed at the AUDIT question rather than the which-parcel one (the
    index-level town/street guards ran before the images were fetched):

      * the extracted recording stamp vs the SELECTED Bk/Pg — a mismatch
        means the viewer served a different instrument than the row that
        was clicked, and the legal description is from the wrong deed;
      * the extracted property address vs the street parsed from
        --base-name — a WARNING / ADDRESS MISMATCH note, never an
        auto-retarget.

    Mutates `result`; never raises.
    """
    try:
        result["extraction_mode"] = extraction_mode
        if mode_note:
            result.setdefault("notes", []).insert(0, mode_note)
        if result.get("status") != "success" or not result.get("files"):
            return
        if not extract_pdf:
            result["notes"].append(
                "READ THE DEED PAGE IMAGES to extract the legal description "
                "and deed fields (claude-code extraction mode): "
                + ", ".join(Path(f).name for f in result["files"])
            )
            return

        # v3.48 (item 42) — snapshot the certificate BEFORE extraction can
        # fill it, so a panel-sourced number (authoritative) stays
        # distinguishable from one read off the instrument.
        _panel_cert = result.get("certificate_of_title") if land_court else None

        # v3.54 (item 57) — take the extraction the runner started while
        # the grantor check ran; fall back to extracting here if it never
        # started, failed, or went stale.
        joined = prefetch.join(result) if prefetch is not None else None
        if joined is not None:
            secs, waited = joined
            _timings_add_stage(
                result, stage_label + " (overlapped with grantor check)",
                secs, wall_seconds=waited)
        else:
            t0 = time.perf_counter()
            _run_pdf_extraction(result, land_court=land_court)
            _timings_add_stage(result, stage_label, time.perf_counter() - t0)
        if not result.get("legal_description"):
            return

        stamp = result.get("recording_stamp")
        if land_court:
            _reconcile_lc_certificate(result, stamp, _panel_cert)
        # v3.48 (item 42) — cite the selection the way the section cites it.
        # Registered Land has no Bk/Pg, so a Land Court run names Document
        # No. + Certificate instead (the same citation the report uses).
        if land_court:
            cite = "Document No. " + str(result.get("document_number") or "___")
            if result.get("certificate_of_title"):
                cite += (", noted on Certificate of Title No. "
                         + str(result["certificate_of_title"]))
        else:
            cite = f"Bk {result.get('book')}/Pg {result.get('page')}"
        verdict = _stamp_matches_selection(
            stamp, result.get("book"), result.get("page"),
            land_court=land_court,
            document_number=result.get("document_number"),
            certificate=result.get("certificate_of_title"),
            lc_book_page=result.get("land_court_registration_book_page"),
        )
        if verdict == "match":
            result["notes"].append(
                f"Recording stamp verified: '{stamp}' names the selected "
                f"{cite}."
            )
        elif verdict == "mismatch":
            result["notes"].append(
                f"WARNING: the recording stamp read off the page images "
                f"('{stamp}') does NOT name the selected {cite} — the "
                "viewer may have served a different instrument. Verify "
                "the page images against the index row before using "
                "this legal description."
            )
        elif stamp:
            result["notes"].append(
                f"NOTE: a recording stamp was read off the page images "
                f"('{stamp}') but it could NOT be checked against the "
                f"selected {cite} — no identifier was available on both "
                "sides. This is an unchecked box, not a clean check: "
                "confirm the page images against the index row yourself."
            )
        addr = result.get("deed_property_address_pdf")
        if addr and street_number and street_name:
            if _alis_address_matches(street_number, street_name, addr):
                result["notes"].append(
                    f"Address verified: extracted deed address '{addr}' "
                    f"matches {street_number} {street_name}."
                )
            elif _alis_street_word_matches(street_name, addr):
                result["notes"].append(
                    f"WARNING: extracted deed address '{addr}' names the "
                    f"subject STREET but the number could not be confirmed "
                    f"against {street_number} {street_name} — verify the "
                    "parcel on the page images."
                )
            else:
                result["notes"].append(
                    f"ADDRESS MISMATCH: extracted deed address '{addr}' does "
                    f"not match {street_number} {street_name}. Do NOT use "
                    "this legal description until the parcel is confirmed — "
                    "the seller may own more than one property, or the "
                    "parcel may be Registered Land."
                )
    except Exception as e:
        result.setdefault("notes", []).append(
            f"Inline image extraction failed (non-fatal): {e}")


def _stamp_noted_certificate(stamp: str):
    """
    v3.48 (item 42) — the certificate named on a Land Court cover sheet's
    "Noted on Certificate" line, pulled back out of the extracted stamp
    string. That line is the authority for which certificate a deed is
    noted on; a certificate recited in the body is the one the land is
    DESCRIBED on (conveyed out of) and is a different number.
    """
    mt = re.search(r"noted\s+on\s+(?:certificate|ctf)[^0-9]{0,20}(\d+)",
                   str(stamp or ""), re.I)
    return mt.group(1) if mt else None


def _reconcile_lc_certificate(result: dict, stamp: str, panel_cert) -> None:
    """
    v3.48 (item 42) — keep the Land Court certificate honest now that
    inline extraction can fill it.

    Precedence is the settled rule: the detail panel's Certificate /
    Encumbrance reference, which equals the cover sheet's "Noted on
    Certificate" line. Extraction reads the same cover sheet, so it is a
    fine SECOND source — but it can also return a certificate recited in
    the deed body, which is the certificate the land is described on, not
    this deed's. Before item 42 a failed panel read left the field null and
    the run said "Certificate of Title No. ___"; letting extraction quietly
    put a plausible wrong number there would replace visible missing
    information with invisible bad information, which is the mistake this
    codebase keeps having to unlearn.

    Live origin: Hollister / 15 Larkspur Rd, 2026-09-02 — the panel returned
    no certificate reference, extraction filled 77105 from the instrument,
    and the cover sheet reads "Noted on Certificate : 198332".
    """
    noted = _stamp_noted_certificate(stamp)
    cur = result.get("certificate_of_title")

    def _d(v):
        s = re.sub(r"\D", "", str(v or ""))
        return s.lstrip("0") or None if s else None

    if panel_cert:
        # Panel spoke; it wins. A disagreeing cover sheet is still news.
        if noted and _d(noted) != _d(panel_cert):
            result["notes"].append(
                f"WARNING: certificate disagreement — the detail panel's "
                f"Certificate/Encumbrance reference is {panel_cert}, but the "
                f"cover sheet's 'Noted on Certificate' line reads {noted}. "
                "Both name this deed's certificate and they should match. "
                "Confirm on the page images before citing either."
            )
        return

    if noted:
        if cur and _d(cur) != _d(noted):
            result["notes"].append(
                f"Certificate corrected to {noted}: the extraction returned "
                f"{cur}, but that number is recited in the instrument rather "
                f"than on the cover sheet's 'Noted on Certificate' line — a "
                "recited certificate is the one the land is DESCRIBED on "
                "(conveyed out of), not the one this deed is noted on. "
                f"Citing {noted}; confirm on the page images."
            )
        else:
            result["notes"].append(
                f"Certificate of Title {noted} read off the cover sheet's "
                "'Noted on Certificate' line (the detail panel returned no "
                "Certificate/Encumbrance reference on this run)."
            )
        result["certificate_of_title"] = noted
        return

    if cur:
        result["notes"].append(
            f"WARNING: Certificate of Title {cur} came from the deed text "
            "alone — the detail panel returned no Certificate/Encumbrance "
            "reference and no 'Noted on Certificate' line was read off the "
            "cover sheet. A certificate recited in an instrument is usually "
            "the one the land is DESCRIBED on, NOT the one this deed is "
            "noted on. Do NOT cite it until it is confirmed on the images."
        )


def _plymouth_extract_verified_hit(result: dict, *, extract_pdf: bool,
                                   street_number: str, street_name: str) -> None:
    """
    v3.50 — full extraction of a --verify-grantor-hit instrument on
    Plymouth (page images), the same _DEED_SCHEMA call the ALIS engine
    makes, plus the which-parcel note. In claude-code mode, or when
    extraction has latched unavailable, the files are NAMED instead, so a
    verification that was not read never looks like one that was.
    Mutates `result`; never raises.
    """
    ver = result.get("grantor_hit_verification") or {}
    files = ver.get("files") or []
    if not files:
        return
    try:
        names = ", ".join(Path(f).name for f in files)
        if not extract_pdf or result.get("extraction_unavailable"):
            why = ("claude-code extraction mode" if not extract_pdf
                   else f"extraction unavailable: {result['extraction_unavailable']}")
            result["notes"].append(
                f"READ THE GRANTOR-HIT PAGE IMAGES to verify Bk "
                f"{ver.get('book')}/Pg {ver.get('page')} ({why}): {names}")
            return
        client, reason = _anthropic_client()
        if client is None:
            result["notes"].append(
                f"Grantor-hit verification extraction skipped ({reason}) — "
                f"READ: {names}")
            return
        try:
            fields = _extract_pdf_fields(
                client, files, _DEED_SCHEMA,
                "These are the page images of an instrument the seller (or "
                "a co-owner) executed as GRANTOR after acquiring the subject "
                "property, surfaced by a grantor-index search and pulled up "
                "for verification. Extract the requested fields.")
        except Exception as e:
            fields = {"error": f"{type(e).__name__}: {e}"}
            _mark_extraction_unavailable(result, e)
        ver["extraction"] = fields
        if "error" in fields:
            result["notes"].append(
                f"WARNING: --verify-grantor-hit extraction failed "
                f"({fields['error']}) — READ: {names}")
            return
        cite = f"Bk {ver.get('book')}/Pg {ver.get('page')}"
        # Same audit check as the main deed: do the images name the hit?
        stamp = fields.get("recording_stamp")
        verdict = _stamp_matches_selection(stamp, ver.get("book"), ver.get("page"))
        ver["stamp_check"] = verdict
        if verdict == "mismatch":
            result["notes"].append(
                f"WARNING: the verified grantor hit's recording stamp "
                f"('{stamp}') does NOT name {cite} — the viewer may have "
                "served a different instrument. Do not rely on this "
                f"verification. READ: {names}")
            return
        if verdict != "match":
            result["notes"].append(
                f"NOTE: the verified grantor hit's recording stamp could not "
                f"be checked against {cite} (read: {stamp!r}) — confirm the "
                "images are that instrument.")
        addr = fields.get("property_address")
        if not addr:
            result["notes"].append(
                f"WARNING: verified grantor hit {cite}: no property address "
                "could be extracted — the parcel is UNVERIFIED, not a "
                f"different parcel. READ: {names}")
        elif street_number and street_name and _alis_address_matches(
                street_number, street_name, addr):
            sev = ("CRITICAL" if _classify_instrument(ver.get("doc_type") or "")
                   != "non_conveyance" else "NOTE")
            result["notes"].append(
                f"{sev}: verified grantor hit {cite} "
                f"({ver.get('doc_type')}) is at the SUBJECT property — "
                f"extracted address '{addr}'.")
        elif street_name and _alis_street_word_matches(street_name, addr):
            result["notes"].append(
                f"WARNING: verified grantor hit {cite}: extracted address "
                f"'{addr}' names the subject STREET but the number could not "
                "be confirmed — treat it as the POSSIBLE subject parcel.")
        else:
            result["notes"].append(
                f"Verified grantor hit {cite}: extracted address '{addr}' — "
                "a different parcel from the subject.")
    except Exception as e:
        result["notes"].append(
            f"Grantor-hit verification extraction failed (non-fatal): {e}")


def _finish_image_registry(result: dict, args, output_folder: Path, *,
                           street_number: str, street_name: str,
                           extract_pdf: bool, extraction_mode: str,
                           mode_note,
                           stage_label: str = "STEP 6 - inline extraction",
                           prefetch: "_ImageExtractionPrefetch" = None) -> None:
    """
    v3.48 (item 42) — the common tail for a browser registry whose deed
    pages arrive as IMAGES: inline extraction, then the Step 6 report
    draft. Plymouth got both at v3.47; Suffolk and Middlesex South were the
    last two registries without them, so on both the assistant had to Read
    the page images, retype the legal description into a temp file and
    re-invoke with --deliver-text-file. The argument for closing that is
    TRANSCRIPTION FIDELITY, not speed: a hand transcription silently
    "corrects" the record (the v3.47 case was a semicolon inside a date),
    and the fix is to let the schema-constrained extraction do the typing.
    With this in place no registry in the plugin depends on the assistant
    retyping a legal description.

    land_court is read off the RESULT, not passed in: Suffolk selects
    across BOTH offices, so which section the deed came from is only known
    once the run has finished. Getting it wrong would label a Registered
    Land instrument "Recorded Land" in the extraction instruction and skip
    the certificate_of_title fill.
    """
    _run_image_extraction(
        result, extract_pdf=extract_pdf, extraction_mode=extraction_mode,
        mode_note=mode_note, street_number=street_number,
        street_name=street_name,
        land_court=bool(result.get("land_court")),
        stage_label=stage_label, prefetch=prefetch,
    )
    try:
        _write_markdown_report(
            result, args.base_name, f"{args.first} {args.last}".strip(),
            output_folder, show_timings=args.timings,
        )
    except Exception as e:
        result.setdefault("notes", []).append(
            f"Report draft failed (non-fatal): {e}")


def _alis_indexed_name_pair(indexed: str) -> tuple:
    """
    Parse an ALIS index name string into (last, first) for a name search.
    "RENWICK, MICHELE D (&AL)" → ("RENWICK", "MICHELE D") — the (&AL)/(&H)/(&W)
    co-party suffix is stripped, the middle initial is KEPT (the index
    groups by the exact string, so 'MICHELE D' rows sort apart from
    'MICHELE' rows — searching first="MICHELE" prefix-matches both).
    """
    # v3.28 — strip EVERY parenthetical group, not just "(&...)". ALIS puts
    # only capacity/co-party markers in parentheses — "(&AL)", "(TR &AL)",
    # "(JR.&AL)", "(BY M)", "(AS TR)", "(EST.&AL)" — and the abstract page
    # additionally tags each party "(Gtor)"/"(Gtee)" where the results grid
    # does not. The old "(&" -only pattern left "COYNE, MARTIN H. (JR.&AL)"
    # with first="MARTIN H. (JR.&AL)", which is not a searchable first name.
    s = re.sub(r"\([^)]*\)", "", indexed or "").strip().rstrip(",").strip()
    if "," in s:
        last, _, first = s.partition(",")
        return (last.strip().upper(), " ".join(first.split()).upper())
    return (s.upper(), "")


def _alis_address_matches(street_num: str, street_word: str, address: str) -> bool:
    """
    v3.14 — does an extracted property address match the expected street?
    Match = the street NUMBER and the FIRST street-name word both appear as
    standalone tokens (case-insensitive). Matching only the first street
    token tolerates suffix variance ("Ave"/"Avenue", "Dr"/"Drive"):
    ("72", "CLOVERFIELD") matches "72 Cloverfield Avenue, Weymouth, MA".
    Tokenizing on non-alphanumerics also splits ranged numbers ("72-74").
    """
    if not (street_num and street_word and address):
        return False
    tokens = re.findall(r"[A-Z0-9]+", _addr_norm(address))
    return street_num.upper() in tokens and _addr_norm(street_word) in tokens


def _addr_norm(s: str) -> str:
    """
    v3.47 — uppercase with apostrophes removed, so a possessive street name
    survives tokenisation: "Baker's Lane" used to split into BAKER + S
    and could never match the street word BAKERS parsed from --base-name,
    producing an ADDRESS MISMATCH on the correct parcel. Both sides are
    normalised, so "Baker's" and "Bakers" in the base name behave alike.
    """
    return (s or "").upper().replace("'", "").replace("’", "")


def _alis_street_word_matches(street_word: str, address: str) -> bool:
    """
    v3.16 — street-NAME-only match, the "suspicious partial" tier: an
    extracted address like 'Cloverfield Avenue, Weymouth' (no number read from
    the scan) matches street word CLOVERFIELD. Used to keep a possible
    subject-parcel hit from being dismissed as a different parcel when the
    number couldn't be confirmed (Renwick Bk39044/162, light-model sample).
    """
    if not (street_word and address):
        return False
    return _addr_norm(street_word) in re.findall(r"[A-Z0-9]+", _addr_norm(address))


_ENTITY_NAME_TOKENS = {
    "TRUST", "TRUSTEE", "TRUSTEES", "LLC", "INC", "CORP", "CORPORATION",
    "COMPANY", "CO", "BANK", "ESTATE", "REALTY", "NOMINEE", "PARTNERSHIP",
    "PARTNERS", "LP", "LLP", "ASSOCIATES", "ASSOCIATION",
}

_GENERATIONAL_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}

# v3.34 (item 19) — words that are marital-status / capacity RECITAL, never
# part of a name. A deed's granting clause writes "Argos Castille being
# unmarried" with no comma, and the v3.14 splitter took the LAST token as
# the surname — so the grantor check searched "UNMARRIED, ARGOS", found
# nothing (no such party exists), and reported the search as
# `status: ok, 0 rows`, which the reading guide defines as CLEAN. A
# nonexistent party rendering as a cleared owner is the tenth instance of
# missing-information-read-as-a-negative-answer. Both halves of the fix
# matter: strip the recital so the real name survives, AND treat a surname
# that still lands on one of these words as UNDERIVABLE — never searched,
# never silently skipped.
_NAME_RECITAL_TOKENS = {
    "BEING", "UNMARRIED", "MARRIED", "SINGLE", "WIDOWED", "WIDOW",
    "WIDOWER", "DIVORCED", "INDIVIDUALLY", "DECEASED", "FORMERLY",
    "KNOWN", "NOW",
}

# Recital PHRASES cut before tokenising. Anchored on specific status words
# so "John A Smith" (period-stripped initial 'A') can never be truncated:
# "a"/"an" only cut when followed by a status word.
_NAME_RECITAL_PHRASE_RE = re.compile(
    r"\s+(?:"
    r"being\s.*"                                            # "being unmarried", "being duly ..."
    r"|(?:a|an)\s+(?:single|married|unmarried|widowed)\b.*"  # "a single person", "a married man"
    r"|(?:a|an)\s+widow(?:er)?\b.*"                          # "a widow", "a widower"
    r"|husband\s+and\s+wife\b.*"
    r"|wife\s+and\s+husband\b.*"
    r"|individually\b.*"
    r")$",
    re.IGNORECASE,
)


def _grantee_full_name_pair(name: str, notes: list = None) -> tuple:
    """
    v3.14 — parse a grantees_full entry (a name transcribed verbatim from
    the deed, natural order, possibly with capacity language) into an ALIS
    (LAST, FIRST) search pair for the co-owner grantor check.

      "Marta Lynn Kowalczyk"                   → ("KOWALCZYK", "MARTA")
      "John A. Smith, individually and as
       Trustee of the Smith Family Trust"      → ("SMITH", "JOHN")
      "Alan D. Whitfield-Barrow"               → ("WHITFIELD-BARROW", "ALAN")
      "Robert Fenwick Jr."                     → ("FENWICK", "ROBERT")
      "Anna Marie Coyne being unmarried"       → ("COYNE", "ANNA")   [v3.34]
      "The Smith Family Trust"                 → ("", "")   [entity]

    Everything after the first comma is capacity language and is dropped;
    " as Trustee ..." phrases without a comma are cut too, and v3.34 cuts
    marital-status recitals ("being unmarried", "a single person") the
    same way. Last remaining token = surname (hyphenated surnames survive
    intact), first token = first name — ALIS's begins-with matching
    extends "MARTA" to "MARTA LYNN"/"MARTA L" index variants.

    Returns ("", "") when the entry is an entity/trust or doesn't parse to
    at least two name tokens. v3.34: when the failure is NOT an entity —
    an individual's entry that would not yield a searchable name, or a
    derived surname landing on a recital word — a WARNING is appended to
    `notes` naming the entry, because that party's grantor search DID NOT
    RUN and silence here reads as a clean check (item 19; the abstract's
    party list usually still covers the party, but that cannot be assumed
    at this call site).
    """
    segments = [seg.strip() for seg in (name or "").split(",")]
    s = segments[0]
    # An entity designator directly after the first comma ("BRANDT
    # INVESTMENTS, LLC, a Massachusetts Limited Liability Company") marks
    # an entity even though the pre-comma portion carries no entity token;
    # an individual's capacity clause starts with "individually"/"as
    # Trustee ..." instead (Brandt live run, 2026-07-16).
    if len(segments) > 1 and segments[1]:
        if segments[1].split()[0].upper().rstrip(".") in _ENTITY_NAME_TOKENS:
            return ("", "")
    s = re.split(r"\s+(?:as|aka|a/k/a|f/k/a)\s+", s, maxsplit=1, flags=re.I)[0]
    s = _NAME_RECITAL_PHRASE_RE.sub("", s)          # v3.34 (item 19)
    s = s.replace(".", " ").strip()
    tokens = s.split()
    if any(t.upper() in _ENTITY_NAME_TOKENS for t in tokens):
        return ("", "")
    while tokens and (tokens[-1].upper() in _GENERATIONAL_SUFFIXES
                      or tokens[-1].upper() in _NAME_RECITAL_TOKENS):
        tokens.pop()
    if len(tokens) < 2 or tokens[-1].upper() in _NAME_RECITAL_TOKENS:
        # Not an entity (that returned above) — this is an individual's
        # entry that did NOT yield a search name. Say so: silence here is
        # how "UNMARRIED, <first name>: 0 rows, ok" read as a cleared
        # co-owner.
        if notes is not None and (name or "").strip():
            notes.append(
                f"WARNING: grantees_full entry '{name}' did not yield a "
                f"co-owner search name — that party's grantor search DID "
                f"NOT RUN from the deed's party list. Check the abstract "
                f"co-owner searches in grantor_check.searches cover this "
                f"party, or search the name by hand before reporting the "
                f"co-owner clean."
            )
        return ("", "")
    return (tokens[-1].upper(), tokens[0].upper())


def _alis_abstract_party_pairs(abstract: dict, notes: list = None) -> list:
    """
    v3.28 — derive grantor-check name pairs from the selected deed's
    Document Abstract, which lists EVERY party on both sides
    ("Gtor:"/"Gtee:", one label per party) in ALIS index format. Returns
    [(LAST, FIRST, via_label), ...].

    Two gaps this closes, both found on Salgado / 87 Marchmont St Hyannis
    (2026-08-12):

      1. The v3.14 co-owner check reads `grantees_full`, i.e. the PDF
         extraction — so when extraction fails (there: an API billing
         error) the co-owner search silently never runs. The abstract is
         index data: no API, no PDF, and it is already fetched for the
         selected row.

      2. A co-owner REMOVED by the vesting deed appears only on the
         GRANTOR side, so `grantees_full` could never have named them even
         with extraction working. Salgado: grantee "SALGADO, MARIA TERESA";
         grantors "DESALGADO, MARIA ISABEL" + "SALGADO, MARIA TERESA". The
         departing party is indexed under a different surname, so neither
         the full-name nor the broad surname-only SALGADO search could reach
         a deed-out by her — and her mortgages on this parcel were
         invisible too.

    Grantees are always returned: they are the continuing owners, and any
    one of them can convey or encumber their interest alone.

    Grantors are returned ONLY when the deed is a partial self-conveyance
    — some party appears on BOTH sides. That is the co-owner-removal /
    re-vesting pattern, and it is what makes the other grantors continuing
    parties in interest rather than the arm's-length seller. On an ordinary
    purchase (Bk 5311/226: TRELAWNEY -> KEEGAN, no overlap) the grantors are
    strangers whose other conveyances are pure noise, and none is returned.
    """
    if not abstract:
        return []

    def _pairs(strings):
        out = []
        for s in strings or []:
            # Defence in depth against the v3.28 footer bug: the parser now
            # terminates the last party value at the recording-footer
            # labels, but any trailer that gets through would become part
            # of a search name, and a search on a malformed name returns
            # zero rows — which reads exactly like a co-owner with nothing
            # recorded against them. Three cuts, cheapest first. Case
            # INSENSITIVE throughout: the Braintree run (2026-08-12) showed
            # the same footer arriving upper-cased, where a rule keyed on
            # the labels' title case would have sailed straight past it.
            s = s or ""
            s = re.split(r"(?i)\s+(?:return\s+addr|recording\s+fee"
                         r"|state\s+excise|surcharge|notes)\s*:",
                         s, maxsplit=1)[0]
            if ":" in s:
                # An unknown TITLE-CASE label ("Some Trailer: …"): ALIS
                # index names are upper case, so the first token carrying a
                # lower-case letter starts the trailer. Gated on the colon,
                # so a genuinely mixed-case name is never truncated.
                keep = []
                for tok in s.split():
                    if any(c.islower() for c in tok):
                        break
                    keep.append(tok)
                s = " ".join(keep) or s
            if ":" in s:
                # An unknown UPPER-CASE label: cut at the colon and drop
                # the label's own last word.
                s = s[:s.index(":")].rsplit(" ", 1)[0]
            last, first = _alis_indexed_name_pair(s)
            # A party name with a digit in it, or one this long, is a
            # parse artefact rather than a person — spending a paginated
            # grantor search on it buys nothing and (Braintree) injected
            # 146 junk hits into the pile the classifier has to sort.
            if any(c.isdigit() for c in last + first) or len(last) + len(first) > 60:
                if notes is not None:
                    notes.append(
                        "NOTE: ignored an unparseable party name from the "
                        f"registry abstract: {s[:80]!r} — not searched as a "
                        "co-owner. If that looks like a real name, the "
                        "abstract parser needs a new terminating label."
                    )
                continue
            # The abstract punctuates initials where the results grid does
            # not — "KEEGAN, RICHARD H." vs "KEEGAN, RICHARD H". Searching
            # the punctuated form finds nothing, so drop the trailing dots
            # (and only those: an interior "." never appears in an ALIS
            # index name).
            last = re.sub(r"\.(?=\s|$)", "", last).strip()
            first = re.sub(r"\.(?=\s|$)", "", first).strip()
            if last and (last, first) not in out:
                out.append((last, first))
        return out

    gtee = _pairs(abstract.get("grantees"))
    gtor = _pairs(abstract.get("grantors"))

    def _ident(pair):
        # Same identity test as _alis_same_party_reconveyance: surname plus
        # the first given-name token, so "KEEGAN, RICHARD H" == "KEEGAN,
        # RICHARD H." == "KEEGAN, RICHARD".
        first_tok = (pair[1].split() or [""])[0]
        return (pair[0], re.sub(r"[^A-Z0-9]", "", first_tok))

    out = [(last, first, f"{last}, {first} (co-owner from abstract)")
           for last, first in gtee]
    gtee_ids = {_ident(p) for p in gtee}
    if any(_ident(p) in gtee_ids for p in gtor):
        for last, first in gtor:
            if _ident((last, first)) in gtee_ids:
                continue      # a continuing owner, already covered above
            out.append((last, first,
                        f"{last}, {first} (prior co-owner from abstract)"))
    return out


def _alis_grantor_check_http(
    session,
    base_url: str,
    name_pairs: list,
    town: str,
    acq_row: dict,
    land_court: bool,
    notes: list,
    prefetched: dict = None,
    retry_town: str = None,
    check_meta: dict = None,
    lien_sweep: bool = False,
) -> list:
    """
    v3.9 grantor check. Runs a PAGINATED grantor search for each
    (last, first) pair in name_pairs, dedupes hits across searches, and
    excludes the acquisition instrument itself (book+page match on Recorded
    Land — the old book-only exclusion could hide a genuine later deed
    recorded in the same book — or document number on Land Court).

    v3.20 — town-scoped retry on the pagination cap (Keegan/402 Sedgefield St,
    2026-08-10): on a common name the county-wide (`town="*ALL"`, Norfolk's
    default by design — it catches a seller who moved within the county)
    search caps at _ALIS_MAX_PAGES and a truncated check cannot support a
    clean-title statement. When a search caps and `retry_town` (the subject
    town code) is a real town, the same pair is re-searched scoped to that
    town with the larger _ALIS_RETRY_MAX_PAGES cap and the results MERGED —
    the county-wide pass is kept, not replaced. A deed-out of the subject
    parcel is indexed under the subject town, so a complete scoped pass
    closes the subject-parcel question even when the county-wide set stays
    truncated. `check_meta` (the result's grantor_check dict) records
    capped_searches / incomplete_searches so callers and the report can
    tell a genuinely clean check from a truncated one.

    v3.28 — DEED-GROUP fallback when town scoping runs out (Salgado / 87
    Linden St Hyannis, 2026-08-12). Barnstable's grantor search is already
    town-scoped, so a capped broad surname-only search had no narrower town
    to retry with and the check reported INCOMPLETE with nothing left to
    try. Document type is the other axis: a `*DD` (deed-group) pass asks
    precisely the question a capped deed-out check still needs answered,
    and took `SALGADO` from capped/150 rows to a complete 36. Results are
    merged, never substituted. A complete deed-group pass RESOLVES the cap
    for a broad surname-only search (which keeps conveyances only anyway,
    so nothing it would have kept is missing) but only PARTLY resolves it
    for a full-name search, whose non-conveyance rows may still be
    truncated — that pair stays in incomplete_searches and says why.

    v3.23 — the fetches are parallel, the semantics unchanged: live
    county-wide searches run concurrently (Phase A), then every capped
    search's town-scoped retry runs concurrently (Phase B), each worker on
    its own Session with its own notes list; merging, filtering, and every
    note/check_meta append happen serially in pair order (Phase C), so the
    output is deterministic. The Keegan validation spent ~4m39s running
    three 20-page scoped retries back to back — the retries are independent
    GETs and there was never a reason to wait between them.

    Callers build name_pairs as:
      Recorded Land — user-supplied full name, exact indexed grantee
        name(s) from the selected deed row, AND the broad surname-only
        search (joint-owner safety net; its namesake noise is tolerable
        on town-filtered Recorded Land).
      Land Court — full-name pairs ONLY (Kowalczyk spec): the broad search
        is what buried the seller's real instruments under pages of
        alphabetically-earlier namesakes.

    Each returned row gains `via_search` naming the search that found it.

    Broad (surname-only) hits are filtered twice, because the broad search
    is a joint-owner safety net and NOTHING else:

      (a) Non-conveyance types are dropped (v3.11). The only question a
          surname-only search can answer is "did someone sharing the
          seller's surname convey this property out?" — a co-owner or name
          variant the full-name searches would miss (Fenwick: the estate
          deed out was indexed under the co-owner's name). A MORTGAGE,
          LIEN, HOMESTEAD, etc. returned by that search is by construction
          a same-surname stranger's business: it cannot be a deed out and
          it cannot change who the grantee is. Reporting them put a false
          CRITICAL flag on a closing file — Louis Sarno's Citizens
          Bank MORTGAGE (Bk 43196/88) was surfaced as a possible
          encumbrance on seller Rosa Sarno (11 Halverson Dr, Braintree,
          2026-07-12). The seller's OWN encumbrances still come through the
          full-name searches, which are not type-filtered.

      (b) Hits recorded BEFORE the acquisition date are dropped — the check
          looks for subsequent dealings, and on a common surname the
          pre-acquisition rows are overwhelmingly unrelated namesakes
          (Renwick broad search: 148 hits, mostly 1910–2016 strangers).

    Full-name hits are kept regardless of type or date, and rows whose date
    fails to parse are kept as a safe default.
    """
    acq_id = _alis_instrument_id(acq_row) if acq_row else None
    acq_date = _parse_deed_date(acq_row.get("date_received") or "") if acq_row else (0, 0, 0)

    def _pair_key(pair):
        # v3.38 — the document group is PART OF THE IDENTITY of a search.
        # Without it a prefetched deed-group set could be served to an
        # all-types pair (or vice versa), silently narrowing a search that
        # was supposed to see every instrument.
        return (pair[0], pair[1], _pair_doc_type(pair))

    def _pair_doc_type(pair):
        """v3.38 — optional 4th element: the server-side document group for
        THIS pair. The deed-out net runs restricted to the deed group so the
        registry filters instead of Python (the broad pass fetched 150-190
        rows to keep ~25, and was ~all of the grantor check's runtime)."""
        return pair[3] if len(pair) > 3 and pair[3] else "*ALL"

    def _pair_is_net(pair):
        """v3.38 — is this pair a broad deed-out NET (strangers likely,
        conveyances only) rather than a search for a known party? Defaults
        to the pre-v3.38 rule: an empty first name marked the net."""
        if len(pair) > 4:
            return bool(pair[4])
        return not pair[1]

    def _pair_label(pair):
        # v3.14 — a pair may carry an explicit via-label as a third element
        # (used to tag co-owner names sourced from the deed extraction).
        last, first = pair[0], pair[1]
        if len(pair) > 2 and pair[2]:
            return pair[2]
        return f"{last}, {first}" if first else f"{last} (surname only)"

    # -----------------------------------------------------------
    # v3.23 — the searches are fetched in PARALLEL, then merged and
    # filtered serially in pair order (so notes, dedupe order, and the
    # via-label a duplicated instrument gets stay deterministic). The
    # Keegan validation ran 4m39s against the 25–65s benchmark because
    # three county-wide searches capped and each re-ran town-scoped at up
    # to _ALIS_RETRY_MAX_PAGES=20 pages, one after another. The retries
    # (and any non-prefetched county-wide searches) are independent HTTP
    # GETs — v3.16 prefetch pattern: own Session and own notes list per
    # worker. NOTE: the retry is never skipped based on the truncated
    # county-wide set's contents — a capped set's absence of subject-town
    # rows proves nothing.
    # -----------------------------------------------------------
    # Phase A — county-wide searches. v3.16 — rows for the row-independent
    # searches may have been prefetched on a worker thread while extraction
    # ran; filtering still happens below, against the final acquisition row.
    # v3.29 — the server-side date window for every search below. Computed
    # from the FINAL acquisition row, so a v3.14 auto-retarget that moved to
    # an earlier deed widens the window rather than leaving it where the
    # pre-retarget row put it.
    window = _grantor_window_start(acq_date)
    window_param = _alis_date_param(window)
    if check_meta is not None:
        check_meta["search_window"] = {
            "from": f"{window[1]:02d}/{window[2]:02d}/{window[0]:04d}" if window_param else None,
            "lookback_days": _GRANTOR_WINDOW_LOOKBACK_DAYS if window_param else None,
            "basis": "acquisition date less lookback" if window_param
                     else "no window — acquisition date unknown, all years searched",
            "lien_sweep": "document-type restricted, ALL YEARS (see *LN pass)",
        }

    searched = {}
    for pair in name_pairs:
        pf_entry = (prefetched or {}).get(_pair_key(pair))
        if pf_entry is None:
            continue
        # v3.29 — the prefetch ran before extraction and therefore before any
        # auto-retarget, so its window was derived from the THEN-selected
        # row. If the final acquisition date is earlier, the prefetched set
        # is missing rows between the two dates — discard it and search live
        # rather than merge a set that was narrowed against the wrong deed.
        # v3.45 (item 29b) — SECTION check, and it comes first: a set from
        # the other index is not merely narrow, it is about a different
        # parcel's index entirely. Live 2026-08-24: the grantee search
        # selected the Land Court deed, the v3.14 address check retargeted to
        # the Recorded Land parcel, and the grantor check then consumed the
        # LAND COURT prefetch — 1 row instead of 3 — and reported
        # "no subsequent instruments found - clean title".
        pf_lc = pf_entry.get("land_court")
        if pf_lc is not None and bool(pf_lc) != bool(land_court):
            notes.append(
                f"Grantor check: discarded the prefetched search for "
                f"{_pair_label(pair)} — it ran against "
                f"{'Land Court' if pf_lc else 'Recorded Land'} before the "
                f"auto-retarget moved the selected deed to "
                f"{'Land Court' if land_court else 'Recorded Land'}. "
                f"Re-searching live in the correct section."
            )
            continue
        pf_window = pf_entry.get("window") or (0, 0, 0)
        if pf_window > window:
            notes.append(
                f"Grantor check: discarded the prefetched search for "
                f"{_pair_label(pair)} — it was date-windowed from "
                f"{pf_window[1]:02d}/{pf_window[2]:02d}/{pf_window[0]} against the "
                f"pre-retarget deed, but the final deed needs "
                f"{window[1]:02d}/{window[2]:02d}/{window[0]}. Re-searching live."
            )
            continue
        searched[_pair_key(pair)] = {
            "rows": pf_entry["rows"], "truncated": pf_entry["truncated"],
            "prefetched": True, "notes": [], "error": None,
        }

    def _county_search(pair):
        s = requests.Session()
        local_notes, meta = [], {}
        try:
            rows = _alis_search_http(
                s, base_url, pair[0], pair[1], "R", town=town,
                land_court=land_court, doc_type=_pair_doc_type(pair),
                date_from=window_param, notes=local_notes,
                meta=meta,
            )
            return _pair_key(pair), {
                "rows": rows, "truncated": meta.get("truncated", False),
                "prefetched": False, "notes": local_notes, "error": None,
            }
        except Exception as e:
            return _pair_key(pair), {
                "rows": [], "truncated": False, "prefetched": False,
                "notes": local_notes, "error": e,
            }

    live_pairs = [p for p in name_pairs if _pair_key(p) not in searched]
    if live_pairs:
        with ThreadPoolExecutor(max_workers=min(4, len(live_pairs))) as pool:
            for key, entry in pool.map(_county_search, live_pairs):
                searched[key] = entry

    # Phase B — town-scoped retries for every capped search (v3.20),
    # including capped prefetched ones, in parallel.
    retry_ok = bool(retry_town and retry_town != town and retry_town != "*ALL")
    retry_pairs = [
        p for p in name_pairs
        if retry_ok and searched.get(_pair_key(p), {}).get("truncated")
        and searched[_pair_key(p)]["error"] is None
    ]

    def _scoped_search(pair):
        s = requests.Session()
        local_notes, meta = [], {}
        try:
            rows = _alis_search_http(
                s, base_url, pair[0], pair[1], "R", town=retry_town,
                land_court=land_court, doc_type="*ALL",
                date_from=window_param,
                max_pages=_ALIS_RETRY_MAX_PAGES, notes=local_notes, meta=meta,
            )
            return _pair_key(pair), {"rows": rows, "meta": meta,
                                     "notes": local_notes, "error": None}
        except Exception as e:
            return _pair_key(pair), {"rows": [], "meta": {},
                                     "notes": local_notes, "error": e}

    scoped_results = {}
    if retry_pairs:
        with ThreadPoolExecutor(max_workers=min(4, len(retry_pairs))) as pool:
            for key, entry in pool.map(_scoped_search, retry_pairs):
                scoped_results[key] = entry

    # -----------------------------------------------------------
    # Phase B2 (v3.28) — DEED-GROUP fallback when narrowing by town is
    # exhausted. Salgado / 87 Marchmont St Hyannis, 2026-08-12: the broad
    # surname-only SALGADO search capped at 150 rows and Barnstable's grantor
    # search is already town-scoped (BARN), so retry_ok was False and the
    # check reported INCOMPLETE with no path forward — the one outcome the
    # v3.20 machinery exists to prevent. Narrowing by DOCUMENT TYPE is the
    # remaining axis: `*DD` (deed group) is exactly the question a capped
    # deed-out check still needs answered, and it took that search from
    # capped/150 to a complete 36 rows over 2 pages.
    #
    # Fires for a pair that capped county-wide AND has no usable town
    # retry, or whose town retry also capped/failed. Scoped to the
    # narrowest town available. Results are MERGED, never substituted, so
    # this can only add rows.
    # -----------------------------------------------------------
    def _dd_needed(pair):
        entry = searched.get(_pair_key(pair)) or {}
        if not entry.get("truncated") or entry.get("error") is not None:
            return False
        if _pair_key(pair) not in scoped_results:
            return True          # no town-scoped retry was available
        sr = scoped_results[_pair_key(pair)]
        return sr["error"] is not None or sr["meta"].get("truncated", False)

    dd_town = retry_town if retry_ok else town

    def _deed_group_search(pair):
        s = requests.Session()
        local_notes, meta = [], {}
        try:
            rows = _alis_search_http(
                s, base_url, pair[0], pair[1], "R", town=dd_town,
                land_court=land_court, doc_type="*DD",
                date_from=window_param,
                max_pages=_ALIS_RETRY_MAX_PAGES, notes=local_notes, meta=meta,
            )
            return _pair_key(pair), {"rows": rows, "meta": meta,
                                     "notes": local_notes, "error": None}
        except Exception as e:
            return _pair_key(pair), {"rows": [], "meta": {},
                                     "notes": local_notes, "error": e}

    dd_pairs = [p for p in name_pairs if _dd_needed(p)]
    dd_results = {}
    if dd_pairs:
        with ThreadPoolExecutor(max_workers=min(4, len(dd_pairs))) as pool:
            for key, entry in pool.map(_deed_group_search, dd_pairs):
                dd_results[key] = entry

    # -----------------------------------------------------------
    # Phase B3 (v3.29) — LIEN SWEEP, restricted by document type and
    # UNRESTRICTED IN TIME.
    #
    # The date window above is correct for the deed-out question but wrong
    # for one class of instrument: liens against the PERSON that can reach
    # after-acquired property (tax liens, executions, attachments,
    # bankruptcy). Those record before acquisition and can still cloud
    # title, so narrowing by date alone would hide them by construction —
    # the same "a filter that cannot see X reports no X" shape as the v3.20
    # null addresses. Restricting by TYPE instead of DATE asks exactly that
    # question over the full history, and the "*LN" group is rare enough
    # that the sweep costs a fraction of the history it replaces.
    #
    # FULL-NAME PAIRS ONLY. The broad surname-only search keeps conveyance
    # types only (v3.11), so lien rows from it would be discarded anyway,
    # and its namesake noise over all years is exactly what the window was
    # added to avoid.
    # -----------------------------------------------------------
    def _lien_search(pair):
        s = requests.Session()
        local_notes, meta = [], {}
        try:
            rows = _alis_search_http(
                s, base_url, pair[0], pair[1], "R", town=town,
                land_court=land_court, doc_type="*LN",
                date_from="",           # deliberate: all years
                max_pages=_ALIS_RETRY_MAX_PAGES, notes=local_notes, meta=meta,
            )
            return _pair_key(pair), {"rows": rows, "meta": meta,
                                     "notes": local_notes, "error": None}
        except Exception as e:
            return _pair_key(pair), {"rows": [], "meta": {},
                                     "notes": local_notes, "error": e}

    # v3.38 — the lien sweep is now OPT-IN (--lien-sweep). It answers a
    # different question from this workflow's: person-level liens that can
    # reach after-acquired property, not "who owns the parcel". Default OFF
    # keeps the grantor check focused; when off, the notes SAY so, because a
    # sweep that silently did not run must never read as a sweep that found
    # nothing.
    # Still only worth sweeping when a window was actually applied — with no
    # window the main pass already covers all years and all types. And never
    # sweep a deed-out NET pair: it is deed-group restricted by construction.
    lien_pairs = [p for p in name_pairs
                  if lien_sweep and window_param and p[1] and not _pair_is_net(p)]
    if not lien_sweep and window_param and check_meta is not None:
        check_meta["lien_sweep"] = "not run (--lien-sweep not passed)"
        notes.append(
            "Grantor check: the all-years LIEN SWEEP did NOT run (it is "
            "opt-in since v3.38 — pass --lien-sweep). This run therefore says "
            "nothing about tax liens, executions, attachments or bankruptcies "
            "against the owners personally; those can reach after-acquired "
            "property and belong to /title-rundown. The deed-out and "
            "current-owner questions are unaffected."
        )
    lien_results = {}
    if lien_pairs:
        with ThreadPoolExecutor(max_workers=min(4, len(lien_pairs))) as pool:
            for key, entry in pool.map(_lien_search, lien_pairs):
                lien_results[key] = entry

    # Phase C — serial merge + filter, in pair order.
    found, seen = [], set()
    for pair in name_pairs:
        last, first = pair[0], pair[1]
        is_net = _pair_is_net(pair)   # v3.38 — was: first == "" marked the net
        label = _pair_label(pair)
        entry = searched.get(_pair_key(pair))
        if entry is None:
            continue
        notes.extend(entry["notes"])
        if entry["error"] is not None:
            # v3.29 — a search that ERRORED is an open question, not a clean
            # one. Before this, a failed search appended a note and dropped
            # through, so a run in which every search failed reported "no
            # subsequent instruments found — clean title" at exit 0. (Caught
            # by the v3.29 test suite itself: a stub signature mismatch made
            # all four Keegan searches raise and the check still said clean.)
            # Same family as the v3.23 swallowed NameError and the v3.20 null
            # addresses — missing information read as a negative answer.
            if check_meta is not None:
                check_meta.setdefault("incomplete_searches", []).append(
                    f"{label} (search failed)")
                # v3.30 (item 11) — the searches log records the attempt too,
                # so "did not run" is never absent from the record.
                check_meta.setdefault("searches", []).append({
                    "name": label, "rows_returned": None, "rows_new": 0,
                    "status": f"ERROR — {entry['error']}",
                })
            notes.append(
                f"WARNING: grantor search '{label}' FAILED (non-fatal): "
                f"{entry['error']} — this name was NOT searched, so the "
                "grantor check is INCOMPLETE for it. Do not read the absence "
                "of hits here as clean title."
            )
            continue
        rows, truncated = entry["rows"], entry["truncated"]
        was_prefetched = entry["prefetched"]

        # v3.20 — town-scoped retry when the county-wide search caps.
        # v3.28 — then the deed-group (*DD) retry when town scoping is
        # exhausted or itself caps.
        if truncated:
            if check_meta is not None:
                check_meta.setdefault("capped_searches", []).append(label)
            resolved = False          # is the cap closed out for this pair?
            why_open = ("no narrower town scope was available to retry with"
                        if not retry_ok else None)
            if retry_ok:
                sr = scoped_results.get(_pair_key(pair)) or {
                    "rows": [], "meta": {}, "notes": [],
                    "error": RuntimeError("scoped retry result missing"),
                }
                notes.extend(sr["notes"])
                scoped_meta, scoped_ok, scoped = sr["meta"], sr["error"] is None, sr["rows"]
                if not scoped_ok:
                    notes.append(
                        f"Town-scoped grantor retry '{label}' failed "
                        f"(non-fatal): {sr['error']}"
                    )
                known = {_alis_row_identity(r) for r in rows}
                rows = rows + [r for r in scoped
                               if _alis_row_identity(r) not in known]
                if scoped_ok and not scoped_meta.get("truncated"):
                    resolved = True
                    notes.append(
                        f"Grantor search '{label}' hit the county-wide "
                        f"pagination cap — re-ran scoped to town {retry_town}: "
                        f"{len(scoped)} row(s), COMPLETE. A deed-out of the "
                        "subject parcel is indexed under the subject town, so "
                        "the subject-parcel check is complete; only the "
                        "seller's out-of-town dealings may be truncated."
                    )
                else:
                    why_open = ("the town-scoped retry "
                                + ("also hit the cap" if scoped_ok else "failed"))

            # v3.28 — deed-group fallback.
            if not resolved:
                dd = dd_results.get(_pair_key(pair))
                if dd is not None:
                    notes.extend(dd["notes"])
                    if check_meta is not None:
                        check_meta.setdefault("deed_group_retries", []).append(label)
                    known = {_alis_row_identity(r) for r in rows}
                    rows = rows + [r for r in dd["rows"]
                                   if _alis_row_identity(r) not in known]
                    dd_ok = dd["error"] is None
                    if not dd_ok:
                        notes.append(
                            f"Deed-group grantor retry '{label}' failed "
                            f"(non-fatal): {dd['error']}"
                        )
                    elif not dd["meta"].get("truncated"):
                        if is_net:
                            # The broad surname-only search is filtered to
                            # conveyance types anyway (filter (a) below), so a
                            # complete deed-group pass IS a complete broad
                            # pass — nothing it would have kept is missing.
                            resolved = True
                            notes.append(
                                f"Grantor search '{label}' hit the pagination "
                                f"cap and {why_open} — re-ran restricted to "
                                f"the deed group (*DD) in town {dd_town}: "
                                f"{len(dd['rows'])} row(s), COMPLETE. The "
                                "broad surname-only search keeps conveyance "
                                "types only, so this answers exactly what it "
                                "exists to ask: whether any same-surname "
                                "party deeded the parcel out."
                            )
                        else:
                            notes.append(
                                f"Grantor search '{label}' hit the pagination "
                                f"cap and {why_open} — re-ran restricted to "
                                f"the deed group (*DD) in town {dd_town}: "
                                f"{len(dd['rows'])} row(s), COMPLETE. The "
                                "DEED-OUT question is closed for this name. "
                                "Still truncated: this party's NON-conveyance "
                                "instruments (mortgages, homesteads, liens), "
                                "which a full-name search normally keeps."
                            )
                            why_open = ("only the deed group could be "
                                        "completed, so non-conveyance "
                                        "instruments may be missing")
                    else:
                        why_open = ("the town-scoped and deed-group retries "
                                    "both hit the cap")

            if not resolved:
                if check_meta is not None:
                    check_meta.setdefault("incomplete_searches", []).append(label)
                notes.append(
                    f"WARNING: grantor search '{label}' hit the pagination "
                    f"cap and {why_open} — the grantor check is INCOMPLETE "
                    "for this name; finish it manually before relying on a "
                    "clean-title statement."
                )
        # v3.29 — merge this pair's all-years lien sweep. Merged, never
        # substituted: it can only add rows the date window excluded.
        lien_ids = set()
        ls = lien_results.get(_pair_key(pair))
        if ls is not None:
            notes.extend(ls["notes"])
            if ls["error"] is not None:
                notes.append(
                    f"WARNING: the all-years lien sweep for '{label}' failed "
                    f"(non-fatal): {ls['error']}. Pre-acquisition liens against "
                    "this party were NOT searched — treat that question as open, "
                    "not as clean."
                )
            else:
                known = {_alis_row_identity(r) for r in rows}
                new_lien = [r for r in ls["rows"]
                            if _alis_row_identity(r) not in known]
                lien_ids = {_alis_row_identity(r) for r in new_lien}
                rows = rows + new_lien
                if ls["meta"].get("truncated"):
                    # Tracked SEPARATELY from incomplete_searches on purpose.
                    # The sweep asks a narrower question than the deed-out
                    # check exists to answer, and a truncated sweep says
                    # nothing about whether the seller conveyed the parcel
                    # away — so it must not flip an otherwise complete check
                    # to INCOMPLETE and turn a clean report CRITICAL. It is
                    # still surfaced: pre-acquisition liens are simply an
                    # open question, which is where this workflow's scope
                    # already leaves them.
                    if check_meta is not None:
                        check_meta.setdefault("lien_sweep_truncated", []).append(label)
                    notes.append(
                        f"NOTE: the all-years lien sweep for '{label}' hit the "
                        "pagination cap — pre-acquisition liens against this "
                        "party may be truncated. The deed-out check is "
                        "unaffected. Lien/discharge status is out of scope "
                        "here either way; route it to /title-rundown."
                    )

        hits = pre_acq = non_conv = lien_hits = 0
        for r in rows:
            if r.get("land_court") != land_court:
                continue
            inst = _alis_instrument_id(r)
            if acq_id and inst == acq_id:
                continue
            if is_net:
                # v3.36 (item 0a): only a KNOWN non-conveyance is dropped
                # from the broad surname-only pass. Blank AND unrecognised
                # types are KEPT — dropping an unknown row is the dangerous
                # direction for a deed-out check (a conveyance whose label
                # lacks the literal string "DEED" — probate distribution,
                # order of taking, a registry indexing QCD/WD — would vanish
                # silently). Surface it and let Claude assess. This is why
                # the design refused a pure allowlist.
                dt = (r.get("doc_type") or "").strip()
                if _classify_instrument(dt) == "non_conveyance":
                    non_conv += 1
                    continue
                if acq_date > (0, 0, 0):
                    row_date = _parse_deed_date(r.get("date_received") or "")
                    if (0, 0, 0) < row_date < acq_date:
                        pre_acq += 1
                        continue
            # Instrument-level dedupe: the same deed indexed under two name
            # variants ("RENWICK, GEORGE" + "RENWICK, GEORGE R") is one hit.
            if inst in seen:
                continue
            seen.add(inst)
            # NB: lien_ids is keyed by _alis_row_identity (the merge key used
            # above), NOT by _alis_instrument_id (the dedupe key) — mixing
            # the two silently dropped every sweep label.
            is_lien_sweep = _alis_row_identity(r) in lien_ids
            r["via_search"] = label + (" (lien sweep, all years)"
                                       if is_lien_sweep else "")
            found.append(r)
            hits += 1
            if is_lien_sweep:
                lien_hits += 1
        notes.append(
            f"Grantor search '{label}': {len(rows)} row(s), {hits} new hit(s)"
            + (f", {non_conv} non-conveyance row(s) skipped" if non_conv else "")
            + (f", {pre_acq} pre-acquisition row(s) skipped" if pre_acq else "")
            + (f", of which {lien_hits} from the all-years lien sweep"
               if lien_hits else "")
            + (" (prefetched during extraction)" if was_prefetched else "")
            + (f" [window: {window[1]:02d}/{window[2]:02d}/{window[0]} onward]"
               if window_param else " [window: all years]")
            + "."
        )
        # v3.30 (item 11) — the same per-search accounting Plymouth grew, in
        # structured form. The note above already said this, but notes are
        # the first thing lost when output is truncated, and a co-owner pass
        # whose rows all duplicate the named seller's is otherwise
        # indistinguishable from one that never ran.
        if check_meta is not None:
            check_meta.setdefault("searches", []).append({
                "name": label,
                "rows_returned": len(rows),
                "rows_new": hits,
                "rows_skipped_non_conveyance": non_conv,
                "rows_skipped_pre_acquisition": pre_acq,
                "lien_sweep_hits": lien_hits,
                "status": "ok",
            })
    return found


def _alis_apply_row_fields(result: dict, row: dict) -> None:
    """
    Populate the index-derived result fields from a selected result row.
    v3.14 — extracted from run_alis_http STEP 2 so the auto-retarget can
    re-apply them when it swaps the selected instrument.
    """
    result["book"]          = row["book"] or None
    result["page"]          = row["page"] or None
    result["ctl_num"]       = row["ctl_num"]
    result["certificate_of_title"] = row["certificate"] or None
    result["document_number"] = row["document_number"] or None
    result["deed_type"]     = row["doc_type"]
    result["recorded_date"] = row["date_received"]
    # Land Court index has no opposite-party column — grantors stays
    # empty and Claude reads them from the deed PDF.
    result["grantors"]      = [row["reverse_party"]] if row["reverse_party"] else []
    result["grantees"]      = [row["name"]] if row["name"] else []
    result["deed_property_address"] = row["doc_desc"] or ""
    # v3.44 (item 25) — the SELECTED ROW decides the section. This used to be
    # set by the grantee-search loop, which made it a property of "whichever
    # section answered first" rather than of the deed actually chosen. Setting
    # it here also covers the auto-retarget, which re-applies these fields and
    # can legitimately swap to a row in the other section.
    result["land_court"] = bool(row.get("land_court"))


def _alis_fetch_deed_files(
    session,
    base_url: str,
    row: dict,
    base_name: str,
    output_folder: Path,
    notes: list,
    errors: list,
    label: str = "deed",
) -> dict:
    """
    STEP 3+4 of run_alis_http — fetch the row's Document Image List and
    download every page PDF. v3.14 — extracted into a helper so the
    auto-retarget can run it a second time for the corrected instrument.
    Returns {"ok", "files", "img_info"}; appends its own notes/errors.
    """
    img_info = _alis_get_pdf_hrefs_http(session, base_url, row["img_href"])
    pdf_hrefs = img_info["pdf_hrefs"]
    if not pdf_hrefs:
        errors.append(
            f"Document Image List: no .PDF links found at {img_info['image_list_url']}"
        )
        return {"ok": False, "files": [], "img_info": img_info}

    if img_info["is_fallback"]:
        notes.append(
            "Document Image List: numbered-page pattern matched 0 links; "
            f"using permissive fallback — selected {len(pdf_hrefs)} .PDF "
            "link(s): " + ", ".join(pdf_hrefs)
        )
    else:
        notes.append(
            f"Document Image List: {len(pdf_hrefs)} page(s) — " + ", ".join(pdf_hrefs)
        )

    saved, dl_errors = _alis_download_pdfs_http(
        session, base_url, pdf_hrefs, base_name, output_folder, label=label
    )
    errors.extend(dl_errors)
    if not saved:
        errors.append(f"PDF download failed for all pages (label={label!r}).")
        return {"ok": False, "files": [], "img_info": img_info}
    notes.append(
        f"Downloaded {len(saved)} PDF(s): {[Path(f).name for f in saved]}"
    )
    return {"ok": True, "files": saved, "img_info": img_info}


class _Timings:
    """
    v3.31 — per-stage wall-clock measurement for one run.

    Measuring only. No scheduling, no transmission, nothing persisted
    outside the run's own output folder: stage names are fixed strings and
    the numbers are durations, but the FILE they land in also holds client
    addresses, so this data never leaves the machine.

    Why it exists: the one time run-shape mattered — establishing that the
    grantor check was 85% of a 6.4-minute run and that the fix was
    concurrent pagination rather than smaller caps — the numbers had to be
    reconstructed by hand from note ordering. Measuring is nearly free, so
    it is always on; `--timings` only controls whether the report shows a
    footer.

    Usage is one line per boundary:

        tm = _Timings()
        tm.mark("STEP 1 - grantee search")   # opens stage 1
        ...
        tm.mark("STEP 2 - select deed row")  # closes 1, opens 2
        ...
        tm.finish(result)                    # closes the last, writes JSON

    `finish` is idempotent so an early `return` path can call it without
    the caller tracking whether it already ran. Every method swallows its
    own errors: a timing bug must never be able to fail a registry run.
    """

    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self._open = None            # (label, start)
        self._stages: list[dict] = []
        self._done = False

    def mark(self, label: str) -> None:
        try:
            now = time.perf_counter()
            if self._open is not None:
                prev, start = self._open
                self._stages.append({"stage": prev,
                                     "seconds": round(now - start, 2)})
            self._open = (label, now)
        except Exception:
            pass

    def finish(self, result: dict) -> None:
        try:
            if self._done:
                return
            self._done = True
            self.mark(None)          # closes the last open stage
            self._open = None
            total = round(time.perf_counter() - self._t0, 2)
            stages = [s for s in self._stages if s["stage"]]
            result["timings"] = {
                "total_seconds": total,
                "stages": stages,
                # The slowest stage is the only one worth acting on, and
                # naming it saves reading the list on every run.
                "slowest": (max(stages, key=lambda s: s["seconds"])
                            if stages else None),
            }
        except Exception:
            pass

    def summary_line(self, result: dict) -> str:
        """One-line human summary, or "" when there is nothing to say."""
        try:
            t = result.get("timings") or {}
            if not t.get("stages"):
                return ""
            parts = ", ".join(f"{s['stage']} {s['seconds']}s"
                              for s in t["stages"])
            return f"Run took {t['total_seconds']}s — {parts}."
        except Exception:
            return ""


def _write_result_json(result: dict, base_name: str, output_folder: Path) -> None:
    """
    v3.30 — persist the complete result JSON beside the PDFs as
    '<base-name> - result.json'. Sets result["result_file"].

    WHY THIS EXISTS: stdout was the script's only output channel, so a run
    whose stdout was not redirected — or whose tail overflowed the caller's
    output limit — lost book, page and grantor_check.needs_review, and the
    only recovery was re-running the entire search. Measured at 36% of one
    bad run's wall clock (Ellsworth, log 2026-08-12-011) and it happened
    again on Grant (2026-08-13-001). With the file on disk, recovery is a
    Read.

    OVERWRITE POLICY is deliberately NOT the never-overwrite rule used for
    the report draft and the paste-out .txt. Those are hand-editable
    deliverables; this is the machine record of the latest run, and a
    re-run must refresh it (the re-run IS the recovery path this fixes).
    One exception protects real information: if the file on disk records a
    SUCCESSFUL run and this run did not succeed, the new result goes to a
    timestamped sibling instead of clobbering it.

    Never fatal — any failure here becomes a note and nothing more. The
    path is assigned BEFORE serialising so the file names itself.
    """
    result["result_file"] = None
    try:
        path = Path(output_folder) / f"{base_name} - result.json"
        if path.exists() and result.get("status") != "success":
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
                prior_ok = isinstance(prior, dict) and prior.get("status") == "success"
            except Exception:
                prior_ok = False    # unreadable/partial — safe to replace
            if prior_ok:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                path = path.with_name(f"{base_name} - result.{stamp}.json")
                result.setdefault("notes", []).append(
                    f"Result JSON written to '{path.name}' — the existing "
                    f"'{base_name} - result.json' records a SUCCESSFUL run and "
                    f"was not overwritten by this '{result.get('status')}' one."
                )
        result["result_file"] = str(path)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception as e:
        result["result_file"] = None
        try:
            result.setdefault("notes", []).append(
                f"Result JSON NOT written ({type(e).__name__}: {e}) — stdout "
                "is the only copy of this run's output; redirect it to a file."
            )
        except Exception:
            pass


def _write_markdown_report(result: dict, base_name: str, seller_display: str,
                           output_folder: Path,
                           show_timings: bool = True) -> None:
    """
    v3.16 — render the Step 6 markdown report DRAFT from the result JSON,
    using the skill's documented structure (LEGAL DESCRIPTION / Deed
    Metadata / Title Flags / Source Pages Saved). Runs only on a successful
    run with a populated legal_description; NEVER overwrites an existing
    report file (manual edits must survive a re-run). Sets
    result["report_file"] on success. Callers wrap non-fatally.
    """
    if result.get("status") != "success" or not result.get("legal_description"):
        return
    report_path = output_folder / f"Legal Description - {base_name}.md"
    if report_path.exists():
        result["notes"].append(
            f"Report draft NOT written — '{report_path.name}' already exists "
            "(existing reports are never overwritten)."
        )
        return

    lc = bool(result.get("land_court"))
    prop = result.get("deed_property_address_pdf") or base_name.split(" - ")[0]
    L = [
        "# Legal Description Report",
        f"Property: {prop}",
        f"Seller: {seller_display}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "> DRAFT — auto-generated by legal_desc_fetch.py (v3.16). Review the",
        "> Title Flags / Notes section (judgment calls are tagged) before",
        "> delivering. Remove this banner when finalized.",
        "",
        "---",
        "",
        "## LEGAL DESCRIPTION",
        "",
        result["legal_description"],
        "",
        "---",
        "",
        "## Deed Metadata",
        "",
        f"- Registry: {result.get('registry')}",
        f"- Section: {'Registered Land (Land Court)' if lc else 'Recorded Land'}",
    ]
    if not lc:
        L.append(f"- Book: {result.get('book')}")
        L.append(f"- Page: {result.get('page')}")
    if result.get("document_number"):
        L.append(f"- Document #: {result['document_number']}")
    if lc:
        L.append(f"- Certificate of Title: {result.get('certificate_of_title')}")
    L.append(f"- Recorded Date: {result.get('recorded_date')}")
    if result.get("signing_date"):
        L.append(f"- Signing Date: {result['signing_date']}")
    if result.get("consideration"):
        L.append(f"- Consideration: {result['consideration']}")
    L.append(f"- Deed Type: {result.get('deed_type')}")
    grantors = result.get("grantors_full") or result.get("grantors") or []
    if grantors:
        L.append("- Grantors (sellers as shown on deed):")
        L.extend(f"  - {g}" for g in grantors)
    grantees = result.get("grantees_full") or result.get("grantees") or []
    if grantees:
        L.append("- Grantees (current owners as shown on deed):")
        L.extend(f"  - {g}" for g in grantees)
        if result.get("tenancy"):
            L.append(f"  - (held {result['tenancy']})")
    if result.get("prior_deed_reference"):
        L.append(f"- Prior Deed Reference: {result['prior_deed_reference']}")
    # v3.48 (item 42) — the extracted address is the best source, but it can
    # be null on an instrument that states no address (a metes-and-bounds
    # deed, an old paper filing). Fall back to what the registry indexed
    # rather than printing "None", and say which source it came from so the
    # two are never confused — the abstract-vs-PDF disagreement check (v3.26)
    # exists precisely because they can differ.
    _addr_pdf = result.get("deed_property_address_pdf")
    _addr_idx = (result.get("deed_property_address_abstract")
                 or result.get("deed_property_address"))
    if _addr_pdf:
        L.append(f"- Deed Property Address: {_addr_pdf}")
    elif _addr_idx:
        L.append(f"- Deed Property Address: {_addr_idx} "
                 "(from the registry index — the instrument itself states "
                 "no address; confirm on the page images)")
    else:
        L.append("- Deed Property Address: NOT STATED on the instrument and "
                 "not indexed — confirm the parcel on the page images")
    if result.get("recording_stamp"):
        L.append(f"- Recording Stamp (verification): {result['recording_stamp']}")
    L += ["", "---", "", "## Title Flags / Notes", ""]

    flags = []
    if len(grantees) > 1:
        flags.append(
            "**FLAG — MULTIPLE OWNERS ON DEED (review):** Title vests in "
            + "; ".join(grantees)
            + (f" ({result['tenancy']})" if result.get("tenancy") else "")
            + ". All current owners must sign the deed and closing documents."
        )
    for t in result.get("title_flags") or []:
        flags.append(f"**NOTE — from deed (extraction):** {t}")
    gc = result.get("grantor_check") or {}
    deeds = gc.get("deeds") or []
    summary = gc.get("summary")
    if deeds and isinstance(summary, dict):
        # v3.23 — classification ran: lead with the short review set, then
        # the full tagged list (nothing is dropped).
        #
        # v3.48 (item 42) — isinstance, not truthiness. ALIS and Plymouth
        # set summary to a dict of counts; run_suffolk sets it to the STRING
        # "hits_found" / "no_hits" / "incomplete". A truthy string reached
        # summary['total'] and raised TypeError, which the caller's
        # try/except swallowed into "Report draft failed (non-fatal)" — so
        # the first Suffolk run to reach the report writer would have got no
        # report and only a soft note saying why. Suffolk falls into the
        # unclassified `elif deeds:` branch below, which is correct: that
        # registry has no parcel classification.
        flags.append(
            f"**GRANTOR CHECK — {summary['total']} instrument(s) found; "
            f"{summary['needs_review']} need review (subject parcel: "
            f"{summary['subject']}, possible subject: "
            f"{summary['possible_subject']}, parcel unknown in subject town: "
            f"{summary['unknown_same_town']}):**"
        )
        flags.extend(f"- {d}" for d in gc.get("needs_review") or [])
        flags.append(
            f"**Full grantor-check list ({summary['total']} instrument(s), "
            "ordered most-relevant first — a 'parcel unknown' tag means no "
            "address was available and the row was NOT ruled out):**"
        )
        flags.extend(f"- {d}" for d in deeds)
    elif deeds:
        flags.append(
            f"**GRANTOR CHECK — {len(deeds)} instrument(s) found (review "
            "each; see workflow notes below for sampled address checks):**"
        )
        flags.extend(f"- {d}" for d in deeds)
    elif gc.get("incomplete_searches"):
        # v3.20 — a truncated zero-hit check must not render as "Clean".
        flags.append(
            "**CRITICAL — Grantor check INCOMPLETE.** No subsequent "
            "instruments in the rows searched, but one or more searches "
            "were TRUNCATED at the pagination cap — complete them before "
            "any clean-title statement."
        )
    else:
        flags.append(
            "**NOTE — Grantor check: Clean.** No subsequent instruments "
            "found for the seller (or deed co-owners) as grantor."
        )
    # v3.30 (item 11) — name the searches behind the verdict above. "Clean"
    # is not auditable without them: on a co-owned parcel every hit is
    # labelled with the FIRST search that found it, so the co-owner pass
    # leaves no trace in the hit list even when it ran. The Grant / 23
    # Harrowgate Dr report could not say the co-owner had not conveyed
    # until that pass was re-run by hand.
    _searches = gc.get("searches") or []
    if _searches:
        _ok = [s for s in _searches if not str(s.get("status", "")).startswith("ERROR")]
        flags.append(
            f"**Names searched as grantor ({len(_ok)} of {len(_searches)} "
            "completed) — the basis for the verdict above:**"
        )
        for s in _searches:
            if str(s.get("status", "")).startswith("ERROR"):
                outcome = f"**DID NOT RUN** — {s['status']}; this name is an OPEN question"
            elif not s.get("rows_returned"):
                outcome = "0 rows — searched, nothing indexed under this name"
            elif not s.get("rows_new"):
                outcome = (f"{s['rows_returned']} rows, 0 new — searched; every "
                           "row was already found under an earlier name "
                           "(duplicate, *not* skipped)")
            else:
                outcome = f"{s['rows_returned']} rows, {s['rows_new']} new"
            flags.append(f"- `{s['name']}` — {outcome}")
    for n in result.get("notes") or []:
        if (n.startswith(("CRITICAL", "AUTO-RETARGETED", "ADDRESS MISMATCH",
                          "ADDRESS MATCH", "Address verified", "Grantor hit",
                          "POSSIBLE SUBJECT", "WARNING", "Candidate"))
                or "not sampled" in n or "sampling capped" in n):
            tag = "CRITICAL" if n.startswith("CRITICAL") else "NOTE"
            flags.append(f"**{tag} — workflow:** {n}")
    for idx, f in enumerate(flags):
        L.append(f)
        nxt = flags[idx + 1] if idx + 1 < len(flags) else None
        if not (f.startswith("-") and nxt and nxt.startswith("-")):
            L.append("")

    # v3.26 — Recorded Cross-References. The registry's own index of what
    # else touches this instrument; collected for years by four different
    # code paths and never shown. Rendered as its own section rather than a
    # title flag because it is a LEAD LIST, not a finding.
    xrefs = result.get("cross_references") or []
    if xrefs:
        L += ["---", "", "## Recorded Cross-References", "",
              "The registry's own index cross-references for this deed — "
              "instruments that reference it or that it references. "
              "**These are leads, not findings: this workflow does not "
              "verify discharges or examine these instruments.** Hand them "
              "to `/title-rundown` or the discharge search.", ""]
        _dir_label = {"later": "recorded after (references this deed)",
                      "earlier": "prior (this deed references it)",
                      "related": "related"}
        L += ["| Instrument | Cite | Date | Relationship | Type |",
              "|---|---|---|---|---|"]
        for r in xrefs:
            cite = (f"Bk {r['book']}/{r['page']}" if r["book"]
                    else f"Doc #{r['doc_number']}" if r["doc_number"] else "—")
            if r["certificate"]:
                cite += f" (Ctf {r['certificate']})"
            L.append(
                f"| {r['instrument'] or r['raw']} | {cite} | {r['date'] or '—'} "
                f"| {_dir_label.get(r['direction'], r['direction'])} "
                f"| {r['kind']} |"
            )
        L.append("")
        _disc = [r for r in xrefs if r["kind"] == "discharge"]
        if _disc:
            L += [f"**{len(_disc)} discharge-type cross-reference(s) above.** "
                  "A discharge in the index is not proof a mortgage was "
                  "discharged — the instrument itself has not been read here. "
                  "Verify before any payoff or clean-title statement.", ""]

    # v3.31 — timing footer. Local measurement only; never transmitted.
    # Its one job is to make an abnormal run shape obvious at a glance —
    # the grantor check quietly taking 85%% of a 6.4-minute run was
    # reconstructed by hand from note ordering before this existed.
    _t = result.get("timings") or {}
    if show_timings and _t.get("stages"):
        L += ["---", "", "## Run Timings", "",
              f"Total: **{_t['total_seconds']}s**"
              + (f" — slowest stage: {_t['slowest']['stage']} "
                 f"({_t['slowest']['seconds']}s)" if _t.get("slowest") else ""),
              "",
              "| Stage | Seconds |", "|---|---|"]
        L += [f"| {s['stage']} | {s['seconds']} |" for s in _t["stages"]]
        L.append("")
    # v3.47 — "Source Pages Saved": the requirement is a human-auditable copy
    # of each page the description was taken from, whatever the format.
    L += ["---", "", "## Source Pages Saved", ""]
    for i, f in enumerate(result.get("files") or [], 1):
        L.append(f"- [{Path(f).name}] — Page {i}")
    extras = []
    for c in result.get("multiple_deed_candidates") or []:
        # v3.20 — deep-sampled candidates carry several pages in sample_files.
        extras += c.get("sample_files") or [c.get("sample_file")]
    extras += [s.get("sample_file") for s in (result.get("grantor_check") or {}).get("samples") or []]
    ver = result.get("grantor_hit_verification") or {}
    extras += ver.get("files") or []
    extras = [e for e in extras if e]
    if extras:
        L.append("")
        L.append("Additional instrument samples (candidates / grantor hits):")
        L.extend(f"- [{Path(e).name}]" for e in extras)

    report_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    result["report_file"] = str(report_path)
    result["notes"].append(
        f"Markdown report DRAFT written: '{report_path.name}' — review the "
        "Title Flags section (and remove the DRAFT banner) before delivering."
    )


# ---------------------------------------------------------------------------
# v3.19 — Step 7 delivery: paste-out forms, .txt/.docx writers, clipboard
# ---------------------------------------------------------------------------

# Character normalization for the paste-ready form: curly quotes and prime
# marks → ASCII quotes (primes appear as feet/inches marks in bearings),
# en/em/horizontal-bar dashes and the minus sign → hyphen, exotic spaces →
# plain space. Nothing outside this table is touched — the degree sign in a
# bearing, ligatures, and accented names all pass through verbatim.
_PASTE_CHAR_MAP = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",
})


def _reflow_legal_description(text: str) -> str:
    """
    Conservative, whitespace-only reflow of the verbatim legal description
    into paste-ready text. Per the skill spec this may ONLY: join
    hard-wrapped lines, rejoin words split by a line-break hyphen, collapse
    space runs, and normalize quote/dash characters. It must NEVER correct
    spelling, expand abbreviations, fix apparent OCR errors, or
    re-punctuate — a silently "improved" metes-and-bounds call is invisible
    in review and wrong in a recorded instrument.

    Blank-line paragraph breaks are preserved (multi-parcel descriptions —
    Parcel I / Parcel II — must not collapse into one paragraph).
    """
    text = text.translate(_PASTE_CHAR_MAP)
    paragraphs = re.split(r"\n[ \t]*\n", text)
    out = []
    for p in paragraphs:
        # prop-\nerty → property. A hyphen kept at a line break for a
        # genuinely hyphenated word is indistinguishable from a soft split;
        # the spec resolves the ambiguity in favor of joining.
        p = re.sub(r"(\w)-[ \t]*\n[ \t]*(\w)", r"\1\2", p)
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p)
    return "\n\n".join(out)


def _derivation_clause(result: dict) -> str:
    """
    "For title, see ..." reference built from the deed metadata. Missing
    values become ___ blanks for the attorney to fill in — never guessed.
    """
    reg = result.get("registry") or "___"
    if result.get("land_court"):
        doc = result.get("document_number") or "___"
        ctf = result.get("certificate_of_title") or "___"
        return (f"For title, see deed filed with the {reg} Registry District "
                f"of the Land Court as Document No. {doc}, as noted on "
                f"Certificate of Title No. {ctf}.")
    book = result.get("book") or "___"
    page = result.get("page") or "___"
    return (f"For title, see deed recorded with the {reg} Registry of Deeds "
            f"in Book {book}, Page {page}.")


def _copy_text_to_clipboard(text: str) -> bool:
    """
    Put `text` on the system clipboard with OS-native tools only (no pip
    dependency). Returns True on success, False on any failure — callers
    treat False as a note, never an error.
    """
    import subprocess
    import tempfile

    def _run(cmd, **kw):
        return subprocess.run(cmd, timeout=15, capture_output=True, **kw)

    try:
        if sys.platform == "win32":
            # clip.exe mangles non-ANSI text; Set-Clipboard reading a UTF-8
            # temp file is deterministic regardless of console codepage.
            tmp = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False)
            try:
                tmp.write(text)
                tmp.close()
                r = _run([
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Set-Clipboard -Value (Get-Content -LiteralPath "
                    f"'{tmp.name}' -Raw -Encoding UTF8)",
                ])
                return r.returncode == 0
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
        data = text.encode("utf-8")
        if sys.platform == "darwin":
            return _run(["pbcopy"], input=data).returncode == 0
        for cmd in (["xclip", "-selection", "clipboard"],
                    ["xsel", "--clipboard", "--input"],
                    ["wl-copy"]):
            try:
                if _run(cmd, input=data).returncode == 0:
                    return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False


def _deliver_legal_description(result: dict, base_name: str,
                               output_folder: Path,
                               copy_to_clipboard: bool = False,
                               write_docx: bool = False) -> None:
    """
    v3.19 — Step 7 delivery, run centrally for every registry. On a
    successful run with a populated legal_description this writes the
    three-form .txt (verbatim / paste-ready / paste-ready + derivation
    clause), optionally a .docx, and optionally puts the paste-ready form
    on the clipboard. Existing .txt/.docx files are NEVER overwritten
    (same policy as the report draft). Callers wrap non-fatally; every
    outcome lands in result["txt_file"] / ["docx_file"] /
    ["clipboard_copied"] / ["legal_description_paste_ready"] + notes.
    """
    result.setdefault("txt_file", None)
    result.setdefault("docx_file", None)
    result.setdefault("clipboard_copied", None)
    result.setdefault("legal_description_paste_ready", None)
    if result.get("status") != "success" or not result.get("legal_description"):
        return
    notes = result.setdefault("notes", [])

    verbatim = result["legal_description"].strip("\n")
    paste_ready = _reflow_legal_description(verbatim)
    result["legal_description_paste_ready"] = paste_ready
    clause = _derivation_clause(result)

    lc = bool(result.get("land_court"))
    if lc:
        source = (f"{result.get('registry')}, Land Court Document No. "
                  f"{result.get('document_number')}, Certificate of Title "
                  f"No. {result.get('certificate_of_title')}, filed "
                  f"{result.get('recorded_date')}")
    else:
        source = (f"{result.get('registry')}, Book {result.get('book')}, "
                  f"Page {result.get('page')}, recorded "
                  f"{result.get('recorded_date')}")

    forms = [
        ("1. VERBATIM (as recorded — line breaks preserved)", verbatim),
        ("2. PASTE-READY (whitespace-only reflow; wording untouched)",
         paste_ready),
        ("3. PASTE-READY + DERIVATION CLAUSE", paste_ready + "\n\n" + clause),
    ]

    txt_path = output_folder / f"Legal Description - {base_name}.txt"
    if txt_path.exists():
        notes.append(
            f"Legal-description .txt NOT written — '{txt_path.name}' already "
            "exists (existing deliverables are never overwritten)."
        )
    else:
        L = [
            f"LEGAL DESCRIPTION — {base_name}",
            f"Source deed: {source}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by "
            "legal_desc_fetch.py — verify against the deed images before use",
        ]
        for heading, body in forms:
            L += ["", "=" * 66, heading, "=" * 66, "", body]
        txt_path.write_text("\n".join(L) + "\n", encoding="utf-8")
        result["txt_file"] = str(txt_path)
        notes.append(f"Legal-description .txt written: '{txt_path.name}'")

    if write_docx:
        docx_path = output_folder / f"Legal Description - {base_name}.docx"
        try:
            import docx  # python-docx — optional
        except ImportError:
            docx = None
        if docx is None:
            notes.append(
                ".docx skipped — python-docx is not installed "
                "(pip install python-docx)."
            )
        elif docx_path.exists():
            notes.append(
                f".docx NOT written — '{docx_path.name}' already exists "
                "(existing deliverables are never overwritten)."
            )
        else:
            try:
                d = docx.Document()
                d.add_heading(f"Legal Description — {base_name}", level=1)
                d.add_paragraph(f"Source deed: {source}")
                for heading, body in forms:
                    d.add_heading(heading, level=2)
                    for para in body.split("\n\n"):
                        d.add_paragraph(para)
                d.save(str(docx_path))
                result["docx_file"] = str(docx_path)
                notes.append(f"Legal-description .docx written: "
                             f"'{docx_path.name}'")
            except Exception as e:
                notes.append(f".docx write failed (non-fatal): {e}")

    if copy_to_clipboard:
        ok = _copy_text_to_clipboard(paste_ready)
        result["clipboard_copied"] = ok
        notes.append(
            "Paste-ready legal description copied to clipboard." if ok else
            "Clipboard copy failed (non-fatal) — paste from the .txt instead."
        )


def run_alis_http(
    registry_label: str,
    base_url: str,
    seller_last: str,
    seller_first: str,
    base_name: str,
    output_folder: Path,
    town: str,
    grantor_town: str = None,
    target_book: str = "",
    target_page: str = "",
    extract_pdf: bool = True,
    extraction_mode: str = "api",
    verify_grantor_hit: str = "",
    show_timings: bool = True,
    lien_sweep: bool = False,
    office: str = "auto",   # v3.44 (item 25) — "auto" | "recorded" | "registered"
    land_court_tripwire: bool = True,   # v3.46 (item 28) — see STEP 6.5
) -> dict:
    """
    Shared pure-HTTP runner for the Browntech ALIS registries (Norfolk,
    Barnstable). Same workflow and result JSON as run_barnstable()/
    run_norfolk(), plus:
      engine                      "http"
      multiple_deed_candidates    populated when the grantee search yields
                                  >1 distinct conveyance instrument — each
                                  entry carries index metadata, whether it
                                  was the selected row, and a downloaded
                                  page-1 sample PDF for address verification
      --book/--page targeting     target_book (+ optional target_page)
                                  overrides the most-recent heuristic; on
                                  Land Court, target_book matches the
                                  document number
      pdf_extraction (v3.10)      when extract_pdf is True, the downloaded
                                  deed (and candidate page-1 samples) are
                                  read by the Claude API and the structured
                                  fields returned in the JSON — no Read
                                  tool step needed on success
      auto_retargeted (v3.14)     True when the selected deed's extracted
                                  address failed to match the street from
                                  --base-name and exactly one candidate's
                                  did, so the script swapped to that
                                  instrument in the same invocation
      grantor_check.samples       (v3.15) page-1 sample PDF + light
                                  extraction for each conveyance-type
                                  grantor-check hit (cap 5), with a
                                  subject-address comparison note
      grantor_check.needs_review  (v3.23) the short set of hits that need
      grantor_check.summary       judgment + per-tier counts — Plymouth
                                  v3.21 shape; hit addresses resolved from
                                  registry abstracts in parallel
      grantor_hit_verification    (v3.15) full download + extraction of
                                  the one grantor hit named by
                                  verify_grantor_hit ("BOOK/PAGE", or the
                                  document number on Land Court)
    """
    grantor_town = grantor_town if grantor_town is not None else town
    result = {
        "status": "error",
        "engine": "http",
        # v3.27 — "api" or "claude-code"; claude-code is a supported mode,
        # not a failure (extraction_error stays null in it).
        "extraction_mode": extraction_mode,
        "registry": registry_label,
        "registry_url": f"{base_url}/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N",
        "registry_system": "Browntech ALIS",
        "land_court": False,
        "book": None,
        "page": None,
        "ctl_num": None,
        "certificate_of_title": None,  # Land Court only — read from the search index
        "document_number": None,   # Land Court: from search index | Recorded Land: from PDF
        "recorded_date": None,
        "deed_type": None,
        "consideration": None,     # extracted from PDF by Claude
        "grantors": [],
        "grantees": [],
        "deed_property_address": None,
        # v3.23 — needs_review + summary mirror the Plymouth v3.21 shape.
        # v3.30 — `searches`: per-search accounting (see _plymouth_record_searches).
        "grantor_check": {"has_subsequent_deed": False, "deeds": [],
                          "needs_review": [], "summary": None, "samples": [],
                          "searches": []},
        "multiple_deed_candidates": [],
        "auto_retargeted": False,   # v3.14 — True when the address check swapped the selected deed
        # v3.22 — the registry's own abstract record for the selected row
        # (address, Doc$ consideration, page count, cross-references).
        "abstract": None,
        "deed_property_address_abstract": None,
        # v3.26 — normalised cross-references (shared shape across all
        # registries); leads for the discharge / title-rundown workflows,
        # NOT discharge verification.
        "cross_references": [],
        "grantor_hit_verification": None,   # v3.15 — populated by --verify-grantor-hit
        "report_file": None,   # v3.16 — path of the script-rendered Step 6 report draft
        "files": [],
        "total_pages_in_deed": None,
        # v3.10 — populated by inline PDF extraction (null/[] when skipped
        # or failed; see extraction_error / notes in that case)
        "legal_description": None,
        "signing_date": None,
        "grantors_full": [],
        "grantees_full": [],
        "tenancy": None,
        "prior_deed_reference": None,
        "title_flags": [],
        "deed_property_address_pdf": None,
        "recording_stamp": None,
        # v3.28 — set when an extraction failure will recur for the rest of
        # the run (no credit, bad key, revoked model access), after which
        # the remaining extraction calls are skipped rather than repeated.
        "extraction_unavailable": None,
        "notes": [],
        "errors": [],
    }
    # v3.31 — measure the run's shape. Always on (the cost is a
    # perf_counter read per stage); --timings only adds the report
    # footer. Nothing here is ever transmitted.
    _tm = _Timings()
    session = requests.Session()

    _tm.mark("STEP 1 - grantee search")
    # -----------------------------------------------------------
    # STEP 1 — GRANTEE SEARCH (Recorded Land, then Land Court fallback)
    # -----------------------------------------------------------
    # v3.44 (item 25) — search BOTH sections and select across the COMBINED
    # candidate set.
    #
    # This loop used to `break` on the first section that returned rows, which
    # made Land Court UNREACHABLE for any seller who also owned a Recorded Land
    # parcel: the Recorded hit won at exit 0 with no warning that a Registered
    # Land parcel existed. Live 2026-08-24 — a Registered Land subject parcel
    # (Land Court deed, noted on its own certificate) came back as the seller's
    # ADJOINING Recorded Land parcel, the Kilbride / 29 Fox Meadow failure mode.
    #
    # `--book` could not rescue it either: the pin was only applied within the
    # section that had returned rows, so targeting the Land Court document
    # failed with "did not match any result row" and `deed_not_found`. Nor
    # could a name prefix — the item-24 28-character Land Court cap truncates
    # both of that entity's indexed spellings to the same string.
    #
    # Every downstream step is already per-row section-aware (each parsed row
    # carries `land_court`; the abstract URL, the image list and the --book
    # match all key off it), so merging is safe. Suffolk has selected across
    # both offices since v3.40; this brings the ALIS registries in line.
    rows = []
    sections_with_rows = []
    for land_court in (False, True):
        section = "Land Court" if land_court else "Recorded Land"
        if office == "recorded" and land_court:
            result["notes"].append("Skipping Land Court (--office recorded).")
            continue
        if office == "registered" and not land_court:
            result["notes"].append("Skipping Recorded Land (--office registered).")
            continue
        result["notes"].append(
            f"Searching {section}: "
            + _alis_url(base_url, seller_last, seller_first, "E",
                        town=town, land_court=land_court, doc_type="*DD", per_page=30)
        )
        try:
            sect_rows = _alis_search_http(
                session, base_url, seller_last, seller_first, "E", town=town,
                land_court=land_court, doc_type="*DD", notes=result["notes"],
            )
        except AlisDegenerateResultError as e:
            # v3.43 (item 24) — a result set that does not answer the query is
            # NOT "no rows". Say so; never let it read as an empty section.
            sect_rows = []
            result["notes"].append(
                f"WARNING: the {section} grantee search returned an "
                f"unusable result set and was NOT searched: {e}"
            )
        if sect_rows:
            sections_with_rows.append(section)
            rows.extend(sect_rows)
            result["notes"].append(f"Found {len(sect_rows)} result(s) in {section}.")
        else:
            result["notes"].append(f"No results in {section}.")

    # Both sections answered: the seller holds parcels in each, which is
    # exactly the case that used to be silently resolved in favour of
    # Recorded Land. Selection now happens across the merged set, but say so
    # plainly — the wrong-parcel guard downstream needs the reader's attention.
    if len(sections_with_rows) > 1:
        result["notes"].append(
            "CRITICAL: this seller has conveyance rows in BOTH Recorded Land "
            "and Registered Land (Land Court). Selection ran across the "
            "COMBINED candidate set, but a seller with a parcel in each "
            "section is the classic wrong-parcel trap — confirm the selected "
            "deed's address/certificate against the subject property before "
            "relying on it, and see multiple_deed_candidates. Pin the section "
            "with --office recorded|registered if you already know it."
        )

    if not rows:
        result["status"] = "deed_not_found"
        result["notes"].append(
            f"No results for {seller_last}, {seller_first} as Grantee "
            f"in {registry_label} (town={town})."
        )
        _tm.finish(result)
        return result

    result["notes"].append(
        "All rows: " + " | ".join(
            f"[{_alis_row_id(r)} {r['doc_type']!r} {r['date_received']} "
            f"{'cert=' + repr(r['certificate']) if r.get('land_court') else 'rev=' + repr(r['reverse_party'])}]"
            for r in rows
        )
    )

    _tm.mark("STEP 2 - select deed row")
    # -----------------------------------------------------------
    # STEP 2 — SELECT DEED ROW (--book/--page target, else heuristic)
    #          + multi-candidate detection (v3.9)
    # -----------------------------------------------------------
    # Distinct conveyance instruments (dual-indexed rows collapse to one).
    candidates, cand_seen = [], set()
    for r in rows:
        if _is_non_conveyance_instrument(r.get("doc_type") or ""):
            continue
        inst = _alis_instrument_id(r)
        if inst in cand_seen:
            continue
        cand_seen.add(inst)
        candidates.append(r)

    row = None
    if target_book:
        tb, tp = _norm_num(target_book), _norm_num(target_page)
        for r in rows:
            if r.get("land_court"):
                match = _norm_num(r.get("document_number")) == tb
            else:
                match = (_norm_num(r.get("book")) == tb
                         and (not tp or _norm_num(r.get("page")) == tp))
            if match:
                row = r
                break
        if row is None:
            result["status"] = "deed_not_found"
            result["notes"].append(
                f"--book {target_book}" + (f" --page {target_page}" if target_page else "")
                + " did not match any result row. Available: "
                + ", ".join(_alis_row_id(r) for r in rows)
            )
            return result
        result["notes"].append(f"Selected by --book/--page target: {_alis_row_id(row)}")
    else:
        row = _alis_select_deed_row(rows)
        if row is None:
            result["status"] = "deed_not_found"
            result["notes"].append("Could not select a deed row from results.")
            return result

    result["notes"].append(
        f"Selected: {row['doc_type']} {_alis_row_id(row)} {row['date_received']} | "
        + (f"Certificate: {row['certificate']}" if row.get("land_court")
           else f"Grantor: {row['reverse_party']}")
        + f" | Grantee: {row['name']} | Desc: {row['doc_desc']}"
    )

    # v3.36 (item 0a) — the ALIS analogue of Plymouth's
    # `selected_row_is_not_a_deed` guard, which this path never had.
    # `_alis_select_deed_row` falls back to the unfiltered rows when every
    # row is excluded, so a non-conveyance — or, before v3.36, an
    # UNRECOGNISED type silently treated as a conveyance — could be
    # reported as the vesting deed with no warning at all.
    _sel_class = _classify_instrument(row.get("doc_type") or "")
    if _sel_class != "conveyance":
        result["selected_row_is_not_a_deed"] = True
        if _sel_class == "unknown":
            result["notes"].append(
                f"CRITICAL: the selected instrument has an UNRECOGNISED type "
                f"{row.get('doc_type')!r} — the script cannot confirm it is a "
                f"conveyance deed. DO NOT report it as the vesting deed or "
                f"extract a legal description from it until you have read it. "
                f"If it IS a conveyance, add the type to the script vocabulary; "
                f"if not, check the other section (Recorded vs Registered Land) "
                f"and check for a misindexed grantee name."
            )
        else:
            result["notes"].append(
                f"CRITICAL: the selected instrument is a {row.get('doc_type')!r}, "
                f"NOT a conveyance deed — no deed-type row was found for this "
                f"party. DO NOT report it as the vesting deed or extract a legal "
                f"description from it. Check the other section (Recorded vs "
                f"Registered Land) and check for a misindexed grantee name."
            )
    else:
        result["selected_row_is_not_a_deed"] = False

    _alis_apply_row_fields(result, row)

    _tm.mark("STEP 2.5 - document abstract")
    # -----------------------------------------------------------
    # STEP 2.5 — DOCUMENT ABSTRACT for the selected row (v3.22)
    # The registry's own index record carries the property address as
    # plain text. Fetch it before any PDF work: it verifies the parcel
    # with no download and no model call, and it still answers when
    # extraction is disabled or has no API key.
    # -----------------------------------------------------------
    sel_abstract = _alis_fetch_abstract_http(session, base_url, row, result["notes"])
    if sel_abstract:
        sel_addrs = _alis_abstract_address_strings(sel_abstract)
        result["abstract"] = {
            "url": sel_abstract.get("url"),
            "addresses": sel_abstract.get("addresses"),
            "consideration": sel_abstract.get("consideration"),
            "pages": sel_abstract.get("pages"),
            "refs": sel_abstract.get("refs"),
            # v3.28 — every party on both sides, in index format. The
            # grantor check derives co-owner search names from these.
            "grantors": sel_abstract.get("grantors"),
            "grantees": sel_abstract.get("grantees"),
        }
        result["deed_property_address_abstract"] = sel_addrs[0] if sel_addrs else None
        if not result.get("consideration") and sel_abstract.get("consideration"):
            result["consideration"] = sel_abstract["consideration"]
        # v3.25 — Land Court: the abstract's Ctf# fills certificate_of_title
        # when the index row didn't carry one.
        if not result.get("certificate_of_title") and sel_abstract.get("certificate"):
            result["certificate_of_title"] = sel_abstract["certificate"]
        # v3.26 — normalise the abstract's cross-references into the shared
        # `cross_references` shape (see _normalize_cross_references).
        result["cross_references"] = _normalize_cross_references(
            sel_abstract.get("refs"),
            "registry abstract (Land Court)" if result["land_court"]
            else "registry abstract",
        )
        xnote = _cross_reference_note(result["cross_references"])
        if xnote:
            result["notes"].append(xnote)
        result["notes"].append(
            f"Abstract (v3.22) for {_alis_row_id(row)}: "
            + (f"address {sel_addrs}" if sel_addrs
               else "NO address field on the abstract (parcel unverified from "
                    "the index — the PDF check below still applies)")
            + (f", Doc$ {sel_abstract['consideration']}"
               if sel_abstract.get("consideration") else "")
            + (f", {len(sel_abstract.get('refs') or [])} cross-reference(s)"
               if sel_abstract.get("refs") else "")
        )

    # Multi-candidate guard: the most-recent heuristic picks the wrong
    # parcel when the seller owns several same-town properties (Renwick —
    # ALIS Desc "UNIT 8T01" vs "LOT 38" can't be matched to a street
    # address from the index alone). Surface every candidate with a
    # page-1 sample so the address on each can be verified. v3.14: the
    # auto-retarget (STEP 6) resolves a mismatch in this invocation when
    # it can; --book/--page re-run remains the manual fallback.
    selected_inst = _alis_instrument_id(row)
    cand_rows = []   # v3.14 — raw rows aligned with multiple_deed_candidates
    if len(candidates) > 1 and not target_book:
        result["notes"].append(
            f"MULTIPLE DEED CANDIDATES ({len(candidates)}) — verify the selected "
            "deed's property address against the subject property; if wrong, "
            "re-run with --book/--page targeting the correct instrument."
        )
        for cand in candidates[:8]:
            inst_selected = _alis_instrument_id(cand) == selected_inst
            entry = {
                "book": cand["book"] or None,
                "page": cand["page"] or None,
                "document_number": cand["document_number"] or None,
                "certificate_of_title": cand["certificate"] or None,
                "doc_type": cand["doc_type"],
                "recorded_date": cand["date_received"],
                "town": cand["town"],
                "doc_desc": cand["doc_desc"],
                "grantor": cand["reverse_party"] or None,
                "grantee": cand["name"] or None,
                "selected": inst_selected,
                "sample_file": None,
                # v3.22 — addresses straight off the registry's abstract page
                "abstract_addresses": [],
                "abstract_url": None,
            }
            # v3.22 — try the abstract FIRST. When it names an address there
            # is nothing left to learn from a page-1 scan, so the download
            # and its vision-model call are both skipped. When it does not
            # (the `Addr:` field is often blank), fall through to the
            # existing page-1 sample — an absent address means UNVERIFIED,
            # never "a different parcel".
            if inst_selected:
                cand_abs = sel_abstract
            else:
                cand_abs = _alis_fetch_abstract_http(
                    session, base_url, cand, result["notes"])
            cand_addrs = _alis_abstract_address_strings(cand_abs)
            if cand_abs:
                entry["abstract_url"] = cand_abs.get("url")
                entry["abstract_addresses"] = cand_addrs
            if not inst_selected and not cand_addrs:
                # Page-1 sample only — full deed is downloaded for the
                # selected row below.
                info = _alis_get_pdf_hrefs_http(session, base_url, cand["img_href"])
                if info["pdf_hrefs"]:
                    label = ("candidate_Doc" + (cand["document_number"] or cand["ctl_num"])
                             if cand.get("land_court")
                             else f"candidate_Bk{cand['book']}_Pg{cand['page']}")
                    saved, errs = _alis_download_pdfs_http(
                        session, base_url, info["pdf_hrefs"][:1],
                        base_name, output_folder, label=label,
                    )
                    if saved:
                        entry["sample_file"] = saved[0]
                    result["errors"] += errs
            result["multiple_deed_candidates"].append(entry)
            cand_rows.append(cand)

        _by_abstract = sum(1 for c in result["multiple_deed_candidates"]
                           if c["abstract_addresses"] and not c["selected"])
        _by_sample = sum(1 for c in result["multiple_deed_candidates"]
                         if c.get("sample_file"))
        result["notes"].append(
            f"Candidate address resolution (v3.22): {_by_abstract} from the "
            f"registry abstract (no PDF, no model call), {_by_sample} needing "
            "a page-1 sample because the abstract carried no address."
        )

    _tm.mark("STEP 3+4 - download deed PDFs")
    # -----------------------------------------------------------
    # STEP 3+4 — DOCUMENT IMAGE LIST → DOWNLOAD PDFs
    # -----------------------------------------------------------
    fetch = _alis_fetch_deed_files(
        session, base_url, row, base_name, output_folder,
        result["notes"], result["errors"],
    )
    if not fetch["ok"]:
        result["image_list_url"] = fetch["img_info"]["image_list_url"]
        result["all_pdf_hrefs_on_image_list"] = fetch["img_info"]["all_pdfs"]
        return result
    result["files"] = fetch["files"]
    result["total_pages_in_deed"] = len(fetch["img_info"]["pdf_hrefs"])

    _tm.mark("STEP 4.5 - prefetch grantor searches")
    # -----------------------------------------------------------
    # STEP 4.5 — PREFETCH ROW-INDEPENDENT GRANTOR SEARCHES (v3.16)
    # The user-name and broad-surname searches depend on neither the
    # retarget outcome nor the extracted co-owner names, so they run on a
    # worker thread (own Session) while the extraction API calls run.
    # Filtering still happens in STEP 7 against the FINAL row. Fails
    # soft: STEP 7 just searches live for any pair that isn't here.
    # -----------------------------------------------------------
    prefetched, prefetch_notes = {}, []
    prefetch_pool = prefetch_future = None

    def _prefetch_grantor_searches():
        psession = requests.Session()
        # v3.38 — prefetch the named seller (all types) and the SELLER'S
        # deed-out net (surname + first initial, deed group). The retired
        # surname-only pass used to be prefetched here, and because it
        # returned 150-190 rows it did not finish during extraction — the
        # grantor check then blocked on it, which is where 53s of a 94s run
        # actually went. Co-owner nets are searched live; they are cheap.
        # v3.45 (item 29b) — SNAPSHOT the section ONCE, at the top, and use
        # this local everywhere below. `result["land_court"]` is mutated on
        # the MAIN thread by the v3.14 auto-retarget, which since v3.44 can
        # move the selected deed ACROSS sections; reading the dict separately
        # for the search and for the bookkeeping let the two disagree, so a
        # Land Court result set got recorded as a Recorded Land one and the
        # staleness guard could not see it.
        pf_land_court = bool(result["land_court"])
        pairs = [(seller_last.upper(), seller_first.upper(), "*ALL")]
        if not pf_land_court and seller_first.strip():
            pairs.append((seller_last.upper(), seller_first.upper()[0],
                          _ALIS_DEED_GROUP))
        # v3.29 — window from the row selected SO FAR. A later auto-retarget
        # can move to an earlier deed, which would make this window too late;
        # the window rides along in the entry and _alis_grantor_check_http
        # discards and re-searches any prefetched set that is too narrow.
        pf_window = _grantor_window_start(
            _parse_deed_date(result.get("recorded_date") or ""))
        pf_param = _alis_date_param(pf_window)
        for last, first, pf_doc_type in pairs:
            try:
                # v3.20 — the truncation flag rides along so the grantor
                # check can trigger its town-scoped retry on capped
                # prefetched searches too.
                meta = {}
                rows = _alis_search_http(
                    psession, base_url, last, first, "R", town=grantor_town,
                    land_court=pf_land_court, doc_type=pf_doc_type,
                    date_from=pf_param, notes=prefetch_notes, meta=meta,
                )
                prefetched[(last, first, pf_doc_type)] = {
                    "rows": rows,
                    "truncated": meta.get("truncated", False),
                    "window": pf_window,
                    # v3.45 (item 29b) — record WHICH SECTION these rows came
                    # from. Since v3.44 the grantee search spans Recorded Land
                    # and Land Court, so an auto-retarget can move the selected
                    # deed ACROSS sections after this prefetch has run. Without
                    # this the grantor check would serve Land Court rows for a
                    # Recorded Land deed (or vice versa) and report the result
                    # as the seller's grantor history.
                    "land_court": pf_land_court,
                }
            except Exception as e:
                prefetch_notes.append(
                    f"Grantor-search prefetch for '{last}, {first or '(surname only)'}' "
                    f"failed (non-fatal, will search live): {e}"
                )

    try:
        prefetch_pool = ThreadPoolExecutor(max_workers=1)
        prefetch_future = prefetch_pool.submit(_prefetch_grantor_searches)
    except Exception as e:
        result["notes"].append(f"Grantor-search prefetch not started (non-fatal): {e}")

    _tm.mark("STEP 5 - PDF extraction")
    # -----------------------------------------------------------
    # STEP 5 — INLINE PDF EXTRACTION (v3.10, non-fatal)
    # v3.14: moved BEFORE the grantor check — the auto-retarget needs the
    # extracted addresses, and the grantor check needs the final
    # acquisition row plus the extracted co-owner names. The two steps
    # were sequential anyway, so the reorder costs nothing.
    # -----------------------------------------------------------
    if extract_pdf and result["files"]:
        _run_pdf_extraction(result, land_court=result["land_court"])
    elif not extract_pdf:
        # v3.27 — in claude-code mode this is a MODE, not a failure: the
        # mode note was already emitted by _resolve_extraction_mode and
        # extraction_error stays null. Only the legacy
        # --no-extract-pdf-text-without-a-mode path lands in the else.
        if extraction_mode != "claude-code":
            result["notes"].append(
                "PDF extraction disabled — Claude should Read the PDFs to "
                "extract deed details."
            )
        else:
            result["notes"].append(
                "READ THE DEED PDFs to extract the legal description and "
                "deed fields (claude-code extraction mode): "
                + ", ".join(Path(f).name for f in result["files"])
            )

    _tm.mark("STEP 6 - auto-retarget check")
    # -----------------------------------------------------------
    # STEP 6 — AUTO-RETARGET BY EXTRACTED ADDRESS (v3.14, non-fatal)
    # The heuristic pick is only kept if its extracted address matches the
    # street parsed from --base-name; on a mismatch with exactly ONE
    # address-matching candidate, the script swaps to that instrument in
    # this same invocation (previously: a manual --book/--page re-run).
    # -----------------------------------------------------------
    # v3.22 — no longer gated on PDF extraction succeeding. The registry
    # abstract supplies addresses for the selected row and the candidates
    # with no API call, so the wrong-parcel guard now also runs under
    # --no-extract-pdf-text, and when extraction failed or has no API key.
    # It runs whenever there is at least one address to reason about.
    _have_address = bool(
        result.get("deed_property_address_pdf")
        or result.get("deed_property_address_abstract")
        or any(c.get("abstract_addresses")
               or (c.get("sample_extraction") or {}).get("property_address")
               for c in result["multiple_deed_candidates"])
    )
    # v3.26 — abstract vs PDF disagreement (see _address_sources_disagree).
    if _address_sources_disagree(result.get("deed_property_address_pdf"),
                                 result.get("deed_property_address_abstract"),
                                 base_name):
        result["notes"].append(
            f"WARNING: the registry abstract and the deed PDF disagree about "
            f"the property address — abstract "
            f"{result['deed_property_address_abstract']!r} vs PDF "
            f"{result['deed_property_address_pdf']!r}. One of them is wrong: "
            "either the abstract is misindexed or the downloaded PDF is a "
            "different parcel. Resolve before relying on the legal "
            "description; the deed image is authoritative for the premises "
            "conveyed."
        )

    if not target_book and _have_address:
        st_num, st_word = _parse_street_from_base_name(base_name)
        expected = f"{st_num} {st_word}".strip()
        # v3.22 — the selected deed's own address: PDF extraction first
        # (it reads the granting clause), then the registry abstract, so
        # the check still runs when extraction is off or came back null.
        main_addr = (result.get("deed_property_address_pdf")
                     or result.get("deed_property_address_abstract"))
        if not (st_num and st_word):
            if cand_rows:
                result["notes"].append(
                    "Auto-retarget skipped: no street number/name parsed from "
                    "the base name — verify the selected deed's address against "
                    "the candidate sample extractions manually."
                )
        elif _alis_address_matches(st_num, st_word, main_addr):
            result["notes"].append(
                f"Address verified: extracted deed address {main_addr!r} "
                f"matches expected street '{expected}' from the base name."
            )
        elif not cand_rows:
            result["notes"].append(
                f"ADDRESS MISMATCH: extracted deed address {main_addr!r} "
                f"does not match expected street '{expected}', and there is "
                "no other conveyance candidate to retarget to — verify the "
                "parcel manually (check the street number, Registered Land, "
                "and misindexed grantee names)."
            )
        else:
            cands = result["multiple_deed_candidates"]

            def _cand_addr(i):
                # v3.22 — prefer the registry abstract's address over the
                # vision-extracted page-1 sample. It is structured index
                # data rather than an OCR read, so it has no null-address
                # failure mode on deeds whose page 1 only says "SEE
                # ATTACHED FULL LEGAL" (the Keegan Bk15978/412 defect). On a
                # multi-parcel deed prefer whichever listed address matches
                # the subject street.
                abs_addrs = cands[i].get("abstract_addresses") or []
                for a in abs_addrs:
                    if _alis_address_matches(st_num, st_word, a):
                        return a
                if abs_addrs:
                    return abs_addrs[0]
                return (cands[i].get("sample_extraction") or {}).get(
                    "property_address")

            def _cand_date(i):
                return _parse_deed_date(cands[i].get("recorded_date") or "")

            def _cand_label(i):
                return (f"{_alis_row_id(cand_rows[i])} "
                        f"({cands[i]['doc_type']} {cands[i]['recorded_date']})")

            # v3.20 — a candidate whose sample yielded NO address is
            # UNVERIFIABLE, not a non-match. Keegan/402 Sedgefield St: the
            # operative 2002 deed's page 1 read only "SEE ATTACHED FULL
            # LEGAL", its sample address came back null, and the retarget
            # silently dropped it — selecting the superseded 1998 deed at
            # exit 0. Sample deeper before matching; whatever still can't
            # be verified is warned about, never discarded quietly.
            unverified = [
                i for i, c in enumerate(cands)
                if not c.get("selected") and not _cand_addr(i)
            ]
            if unverified:
                _alis_extend_candidate_samples(
                    session, base_url, result, cand_rows, unverified,
                    base_name, output_folder,
                )
                unverified = [i for i in unverified if not _cand_addr(i)]

            def _warn_unverified(chosen_idx=None):
                if not unverified:
                    return
                names = ", ".join(_cand_label(i) for i in unverified)
                newer = (chosen_idx is not None and any(
                    _cand_date(i) > _cand_date(chosen_idx)
                    for i in unverified))
                result["notes"].append(
                    ("CRITICAL" if newer or chosen_idx is None else "WARNING")
                    + f": candidate(s) {names} could NOT be address-verified "
                    "(no property address found in the sampled pages) and "
                    "were NOT ruled out"
                    + (" — at least one is recorded LATER than the selected "
                       "deed and could supersede it" if newer else "")
                    + ". Verify each with a --book/--page re-run before "
                    "relying on the selected deed."
                )

            match_idxs = [
                i for i, cand in enumerate(cands)
                if not cand.get("selected")
                and _alis_address_matches(st_num, st_word, _cand_addr(i))
            ]
            target_idx = None
            if len(match_idxs) == 1:
                target_idx = match_idxs[0]
            elif len(match_idxs) > 1:
                # v3.20 — several candidates match the subject street: they
                # are the same parcel's chain of deeds to this owner (e.g.
                # purchase deed + later re-vesting deed). The most recently
                # recorded match is the operative vesting instrument —
                # previously this branch gave up and asked for a manual
                # --book/--page pick.
                ranked = sorted(match_idxs, key=_cand_date, reverse=True)
                if (_cand_date(ranked[0]) > (0, 0, 0)
                        and _cand_date(ranked[0]) > _cand_date(ranked[1])):
                    target_idx = ranked[0]
                    result["notes"].append(
                        f"ADDRESS MATCH x{len(ranked)}: "
                        + ", ".join(_cand_label(i) for i in ranked[1:])
                        + f" also match '{expected}' but are recorded "
                        "EARLIER — selecting the most recent match "
                        f"{_cand_label(target_idx)} as the operative vesting "
                        "deed; the earlier one(s) are its chain of title and "
                        "are likely superseded."
                    )
                else:
                    result["notes"].append(
                        f"ADDRESS MISMATCH: extracted deed address "
                        f"{main_addr!r} does not match expected street "
                        f"'{expected}'; {len(match_idxs)} candidates match "
                        "it but their recorded dates are missing or tied, "
                        "so the script cannot rank them — pick via the "
                        "sample extractions and re-run with --book/--page."
                    )
            if target_idx is not None:
                new_row = cand_rows[target_idx]
                new_entry = result["multiple_deed_candidates"][target_idx]
                # v3.22 — the address that justified the swap, from whichever
                # source supplied it (abstract or page-1 sample). Reading
                # sample_extraction directly reported None for candidates the
                # abstract had resolved without a sample.
                new_addr = _cand_addr(target_idx)
                old_id = _alis_row_id(row)
                old_files = list(result["files"])
                old_grantees = list(result.get("grantees_full") or [])
                label = ("deed_Doc" + (new_row["document_number"] or new_row["ctl_num"])
                         if new_row.get("land_court")
                         else f"deed_Bk{new_row['book']}_Pg{new_row['page']}")
                refetch = _alis_fetch_deed_files(
                    session, base_url, new_row, base_name, output_folder,
                    result["notes"], result["errors"], label=label,
                )
                if refetch["ok"]:
                    # Demote the heuristic pick into the candidates list,
                    # keeping its page-1 file and extracted address so the
                    # evidence for the swap stays in the output.
                    for cand in result["multiple_deed_candidates"]:
                        if cand.get("selected"):
                            cand["selected"] = False
                            cand["sample_file"] = old_files[0]
                            cand["sample_extraction"] = {
                                "property_address": main_addr,
                                "lot_or_unit": None,
                                "grantees": old_grantees,
                            }
                    new_entry["selected"] = True
                    row = new_row
                    _alis_apply_row_fields(result, row)
                    result["files"] = refetch["files"]
                    result["total_pages_in_deed"] = len(refetch["img_info"]["pdf_hrefs"])
                    result["auto_retargeted"] = True
                    result["notes"].append(
                        f"AUTO-RETARGETED (v3.14): heuristic picked {old_id} "
                        f"({main_addr or 'no address extracted'}); address "
                        f"match selected {_alis_row_id(row)} "
                        f"({new_addr or 'address source unrecorded'}"
                        + (" — from the registry abstract"
                           if new_entry.get("abstract_addresses")
                           else " — from the page-1 sample") + "). "
                        f"The wrong pick's PDFs remain on disk: "
                        f"{[Path(f).name for f in old_files]}"
                    )
                    # Wipe every field extracted from the wrong deed before
                    # re-extracting — a failed re-extraction must not leave
                    # the wrong parcel's legal description in place.
                    result["consideration"] = None
                    result["legal_description"] = None
                    result["signing_date"] = None
                    result["grantors_full"] = []
                    result["grantees_full"] = []
                    result["tenancy"] = None
                    result["prior_deed_reference"] = None
                    result["title_flags"] = []
                    result["deed_property_address_pdf"] = None
                    result["recording_stamp"] = None
                    result.pop("pdf_extraction", None)
                    # v3.22 — the retarget can now fire without extraction
                    # ever having run; only re-extract if it is enabled.
                    # v3.28 — and not once extraction is known to be down.
                    if extract_pdf and not result.get("extraction_unavailable"):
                        _run_pdf_extraction(result, land_court=result["land_court"])
                    elif extract_pdf:
                        result["notes"].append(
                            "READ THE RETARGETED DEED PDFs — re-extraction "
                            "was skipped because extraction is unavailable "
                            f"({result['extraction_unavailable']}): "
                            + ", ".join(Path(f).name for f in result["files"])
                        )
                    # v3.22 — refresh the abstract for the newly selected row.
                    new_abs = _alis_fetch_abstract_http(
                        session, base_url, row, result["notes"])
                    if new_abs:
                        new_addrs = _alis_abstract_address_strings(new_abs)
                        result["abstract"] = {
                            "url": new_abs.get("url"),
                            "addresses": new_abs.get("addresses"),
                            "consideration": new_abs.get("consideration"),
                            "pages": new_abs.get("pages"),
                            "refs": new_abs.get("refs"),
                            "grantors": new_abs.get("grantors"),
                            "grantees": new_abs.get("grantees"),
                        }
                        result["deed_property_address_abstract"] = (
                            new_addrs[0] if new_addrs else None)
                        if not result.get("consideration") and new_abs.get("consideration"):
                            result["consideration"] = new_abs["consideration"]
                        result["notes"].append(
                            f"Abstract (v3.22) for the retargeted deed "
                            f"{_alis_row_id(row)}: "
                            + (f"address {new_addrs}" if new_addrs
                               else "no address field")
                            + (f", {len(new_abs.get('refs') or [])} cross-reference(s)"
                               if new_abs.get("refs") else "")
                        )
                    if (extract_pdf and not result.get("extraction_error")
                            and not _alis_address_matches(
                                st_num, st_word,
                                result.get("deed_property_address_pdf"))):
                        result["notes"].append(
                            "WARNING: the retargeted deed's full extraction "
                            f"address is {result.get('deed_property_address_pdf')!r}, "
                            f"which does not match '{expected}' either — "
                            "verify the parcel manually."
                        )
                    # v3.20 — grantor == grantee on the selected deed is
                    # affirmative evidence it is the operative instrument.
                    if _alis_same_party_reconveyance(new_entry):
                        result["notes"].append(
                            "Note: the selected deed's grantor and grantee "
                            "are the SAME party — a re-vesting deed "
                            "(marriage/trust/tenancy change), which "
                            "routinely supersedes the purchase deed as the "
                            "operative vesting instrument."
                        )
                    _warn_unverified(target_idx)
                else:
                    result["notes"].append(
                        f"Auto-retarget FAILED to download {_alis_row_id(new_row)} "
                        f"— keeping the heuristic pick {old_id}. Its address did "
                        f"NOT match '{expected}'; verify manually or re-run with "
                        "--book/--page."
                    )
                    _warn_unverified(None)
            elif not match_idxs:
                result["notes"].append(
                    f"ADDRESS MISMATCH: extracted deed address {main_addr!r} "
                    f"does not match expected street '{expected}', and no "
                    "candidate sample matches either — verify via the sample "
                    "extractions and re-run with --book/--page if wrong."
                )
                _warn_unverified(None)
            else:
                # Multi-match with unrankable dates (note appended above) —
                # still surface any unverified candidates.
                _warn_unverified(None)

    _tm.mark("STEP 6.5 - Land Court tripwire")
    # -----------------------------------------------------------
    # STEP 6.5 — LAND COURT TRIPWIRE (v3.46, backlog item 28)
    #
    # The selection above is final. If it landed on RECORDED LAND, ask the
    # NAME-INDEPENDENT combined address index whether this street carries any
    # Registered Land. v3.44 already searches both sections, but it can only
    # find what the NAME index holds — a misindexed or variant-spelled owner
    # is invisible to it, and that is exactly how a Land Court parcel gets
    # reported as the seller's adjoining Recorded parcel at exit 0.
    #
    # Deliberately NOT run when the selected deed is already Land Court
    # (nothing to warn about) and not run at all on a --book/--page pin,
    # where the operator has already stated the answer.
    result["land_court_tripwire"] = None
    if not land_court_tripwire:
        result["notes"].append(
            "Land Court tripwire (v3.46): DISABLED for this run (--no-land-court-tripwire). "
            "No conclusion about registered land at this address."
        )
    if land_court_tripwire and not result.get("land_court") and not target_book:
        try:
            _tw_num, _tw_word = _parse_street_from_base_name(base_name)
            _tw_street = _street_words_from_base_name(base_name) or _tw_word
            result["land_court_tripwire"] = _alis_land_court_tripwire(
                session, base_url, _tw_num, _tw_street, town, result["notes"]
            )
        except Exception as _tw_exc:                      # noqa: BLE001
            # Non-fatal by design: this is a corroborating check, and a
            # failure here must never take down a run that has already
            # found and verified a deed. But say so — a tripwire that did
            # not run is not a tripwire that found nothing.
            result["notes"].append(
                f"Land Court tripwire (v3.46) did NOT run: {_tw_exc}. "
                "No conclusion about registered land on this street."
            )

    _tm.mark("STEP 7 - grantor check")
    # -----------------------------------------------------------
    # STEP 7 — GRANTOR CHECK (v3.9: paginated, full-name variants;
    # v3.14: runs after extraction/retarget, so the acquisition row is
    # final and co-owner names from the deed join the search;
    # v3.16: the row-independent searches were prefetched in STEP 4.5)
    # -----------------------------------------------------------
    if prefetch_future is not None:
        try:
            prefetch_future.result()
        except Exception as e:
            result["notes"].append(f"Grantor-search prefetch failed (non-fatal): {e}")
        prefetch_pool.shutdown(wait=False)
        result["notes"].extend(prefetch_notes)

    grantor_rows = []
    try:
        lc = result["land_court"]
        # v3.45 (item 29) — an EMPTY --first is this tool's ENTITY convention
        # (the whole name goes in --last, per the Plymouth/Suffolk/ALIS
        # invocations), NOT an unknown first name. `_pair_is_net`'s default
        # rule is `not pair[1]`, so the seller's OWN pass was being
        # classified as a broad deed-out NET whenever the seller was an
        # entity — and a net is type-filtered to conveyances, on the
        # reasoning that its hits are probably same-surname strangers.
        #
        # For an entity that reasoning is exactly inverted: the "surname" IS
        # the complete, exact name of the seller, and its non-conveyance hits
        # are the seller's OWN mortgages, municipal lien certificates,
        # homesteads and liens. They were silently dropped. Live 2026-08-24:
        # a run found the right 3 instruments (`rows_returned: 3`) and
        # skipped all 3 as `rows_skipped_non_conveyance`, so
        # `grantor_check.deeds` came back EMPTY. The deed-out answer was
        # right, but the report showed none of the seller's encumbrances at
        # the subject parcel — including an open six-figure mortgage.
        #
        # Marking the pair `is_net=False` explicitly is a no-op for an
        # individual (a non-empty first name already evaluates False) and
        # the fix for an entity.
        _entity_seller = not seller_first.strip()
        name_pairs = [(
            seller_last.upper(), seller_first.upper(),
            (f"{seller_last.upper()} (entity seller — full name)"
             if _entity_seller else None),
            None,          # doc_type: *ALL — the seller's own pass is never
                           # restricted to the deed group
            False,         # is_net: this is the NAMED SELLER, not a net
        )]
        idx_pair = _alis_indexed_name_pair(row.get("name") or "")
        if idx_pair[0] and idx_pair not in name_pairs:
            name_pairs.append(idx_pair)

        # v3.14 — co-owner names extracted from the deed itself. A co-owner
        # with a different surname conveying alone was invisible to every
        # existing search; on Land Court even same-surname co-owners were
        # (the index shows one grantee + "(&AL)" and gets no broad search).
        co_pairs = []

        def _add_co_pair(co_last, co_first, label):
            if not co_last:
                return
            covered = any(
                p[0] == co_last and p[1] and co_first.startswith(p[1])
                for p in name_pairs + co_pairs
            )
            if not covered:
                co_pairs.append((co_last, co_first, label))

        for g in result.get("grantees_full") or []:
            # v3.34 (item 19): pass notes so an individual's entry that
            # yields no search name WARNS instead of vanishing — a garbage
            # or unparseable name must never render as a clean search.
            co_last, co_first = _grantee_full_name_pair(g, result["notes"])
            _add_co_pair(co_last, co_first,
                         f"{co_last}, {co_first} (co-owner from deed)")

        # v3.28 — the same names off the registry ABSTRACT, which needs no
        # API and covers two cases the deed extraction cannot: a run whose
        # extraction failed or was never enabled, and a co-owner REMOVED by
        # the vesting deed (named only on its grantor side). See
        # _alis_abstract_party_pairs.
        for co_last, co_first, label in _alis_abstract_party_pairs(
                result.get("abstract"), result["notes"]):
            _add_co_pair(co_last, co_first, label)

        if co_pairs:
            result["notes"].append(
                "Grantor check includes co-owner name(s) from the deed and "
                "its registry abstract: "
                + "; ".join(f"{p[0]}, {p[1]}" for p in co_pairs)
            )
        name_pairs.extend(co_pairs)

        if not lc:
            # Broad surname search — catches same-surname joint owners.
            # Skipped on Land Court (Kowalczyk: namesake noise buries the
            # seller's real instruments).
            # -----------------------------------------------------------
            # THE DEED-OUT NET (v3.38, replacing the always-on full
            # surname-only pass). Skipped on Land Court either way
            # (namesake noise buries the seller's real instruments).
            #
            # WHY IT CHANGED. Measured: the surname-only pass returned
            # 188 rows to keep 28 (and 154 to keep 24 on another run) and
            # was essentially the ENTIRE grantor-check runtime — 53s of a
            # 94s run, 42s of a 57s run — while the named-seller and
            # co-owner passes returned 4-6 rows each.
            #
            # WHAT IT UNIQUELY CAUGHT, and what replaces it. Both
            # platforms PREFIX-match, so a full-name search already
            # reaches longer index spellings ("PENN" finds "PENNE").
            # Prefix matching runs one way only, so a full-name search
            # genuinely misses an instrument indexed with an INITIAL
            # ("SMITH, J") or a misspelled first name. Surname + first
            # INITIAL catches both — "SMITH, J" reaches "J", "JOHN",
            # "JON" — at a fraction of the rows. Restricted to the deed
            # group server-side, because a deed-out net has no business
            # fetching mortgages. (Note what NEITHER form rescues: a
            # misspelled SURNAME. That is the address search's job.)
            #
            # The one thing surname-only still had: an UNKNOWN
            # same-surname co-owner. Since v3.28 the registry abstract
            # enumerates every party on both sides, so we normally know
            # the owners by name — which is why the full pass is now a
            # FALLBACK, fired only when that enumeration failed and the
            # net is actually load-bearing.
            # -----------------------------------------------------------
            known_owners = [(seller_last.upper(), seller_first.upper())]
            known_owners += [(p[0], p[1]) for p in co_pairs]
            net_pairs = []
            for o_last, o_first in known_owners:
                if not (o_last and o_first):
                    continue
                init = (o_last, o_first[0])
                if init in {(p[0], p[1]) for p in name_pairs + net_pairs}:
                    continue
                net_pairs.append((
                    o_last, init[1],
                    f"{o_last}, {init[1]}* (deed-out net, deed group)",
                    _ALIS_DEED_GROUP, True,
                ))

            # Fallback: no owner name yielded an initial — the party list
            # could not be enumerated at all (no abstract, extraction
            # failed, entity seller). THIS is when the broad net earns its
            # keep, so fire the full surname-only pass and say why.
            if not net_pairs and _entity_seller:
                # v3.45 (item 29) — for an ENTITY the fallback net would
                # re-run the seller's own query: same surname, same empty
                # first name, only narrowed to the deed group. The seller's
                # own pass (above) is a strict SUPERSET of it — all document
                # types, unfiltered — so the net adds nothing but a round
                # trip, and its "hits may be strangers" framing is wrong for
                # a name that IS the seller.
                result["notes"].append(
                    "Grantor check: entity seller — the deed-out net was NOT "
                    "run separately because the seller's own full-name pass "
                    f"({seller_last.upper()}) is the same query, unrestricted "
                    "by document type. Its hits are the SELLER'S OWN "
                    "instruments (mortgages, MLCs, homesteads, liens are all "
                    "kept), not same-surname strangers. Note the standing "
                    "limitation: neither pass reaches a MISSPELLED entity "
                    "name in the index — use the address search for that."
                )
            elif not net_pairs:
                net_pairs.append((
                    seller_last.upper(), "",
                    f"{seller_last.upper()} (surname only — FALLBACK: owner "
                    f"names could not be enumerated)",
                    _ALIS_DEED_GROUP, True,
                ))
                result["notes"].append(
                    "Grantor check: no owner first name was available, so the "
                    "deed-out net fell back to a FULL surname-only search "
                    "(deed group). This is the broad pass — its hits may be "
                    "same-surname strangers; verify the grantor's first name "
                    "before flagging one."
                )
            else:
                result["notes"].append(
                    "Grantor check deed-out net (v3.38): searched "
                    + "; ".join(f"{p[0]}, {p[1]}*" for p in net_pairs)
                    + " restricted to the deed group. Surname+initial is a "
                    "PREFIX match, so it reaches initial-only and "
                    "misspelled-first-name index entries; it does NOT reach "
                    "a misspelled SURNAME (use the address search) or an "
                    "unknown same-surname co-owner with a different initial."
                )
            for np_ in net_pairs:
                if (np_[0], np_[1]) not in {(p[0], p[1]) for p in name_pairs}:
                    name_pairs.append(np_)

        grantor_rows = _alis_grantor_check_http(
            session, base_url, name_pairs, town=grantor_town,
            acq_row=row, land_court=lc, notes=result["notes"],
            prefetched=prefetched,
            # v3.20 — subject town code for the capped-search retry, and
            # the grantor_check dict so truncation state lands in the JSON.
            retry_town=town, check_meta=result["grantor_check"],
            lien_sweep=lien_sweep,
        )
        result["grantor_check"]["has_subsequent_deed"] = len(grantor_rows) > 0
        if grantor_rows:
            # v3.23 — classify, order and summarise (Plymouth v3.21 parity).
            # Per-hit addresses come from registry abstracts, fetched in
            # parallel well beyond the PDF-sampling cap; builds
            # grantor_check.deeds (tagged, most-relevant first),
            # .needs_review and .summary, and emits the subject /
            # possible-subject notes.
            _alis_finalize_grantor_check(result, grantor_rows, base_name,
                                         town, base_url)
        elif result["grantor_check"].get("incomplete_searches"):
            # v3.20 — Keegan: a truncated check with zero hits in the rows
            # that DID come back is not a clean-title finding.
            result["notes"].append(
                "Grantor check: no subsequent instruments in the rows "
                "searched, but one or more searches were TRUNCATED (see "
                "warnings above) — do NOT report this as a clean title "
                "without completing the capped search(es)."
            )
        else:
            result["notes"].append(
                "Grantor check: no subsequent instruments found — clean title."
            )
    except Exception as e:
        result["notes"].append(f"Grantor check failed (non-fatal): {e}")

    _tm.mark("STEP 8 - grantor-hit samples")
    # -----------------------------------------------------------
    # STEP 8 — GRANTOR-HIT SAMPLES + TARGETED VERIFICATION (v3.15,
    # non-fatal). The grantor check *finds* instruments but its rows were
    # never fetchable — confirming a suspected deed-out took ad hoc
    # scripting (Brandt Bk36890/431, 2026-07-13). Now every
    # conveyance-type hit gets a page-1 sample + light extraction, and
    # --verify-grantor-hit fully fetches one named hit.
    # -----------------------------------------------------------
    try:
        st_num, st_word = _parse_street_from_base_name(base_name)

        def _hit_meta(r: dict) -> dict:
            return {
                "book": r["book"] or None,
                "page": r["page"] or None,
                "document_number": r["document_number"] or None,
                "certificate_of_title": r["certificate"] or None,
                "doc_type": r["doc_type"],
                "recorded_date": r["date_received"],
                "grantee": r["reverse_party"] or None,
                "via": r.get("via_search"),
            }

        def _hit_label(r: dict) -> str:
            return ("grantorhit_Doc" + (r["document_number"] or r["ctl_num"])
                    if r.get("land_court")
                    else f"grantorhit_Bk{r['book']}_Pg{r['page']}")

        def _hit_address_note(r: dict, address, what: str) -> None:
            """Compare a fetched hit's extracted address to the subject
            street. v3.23 — thin wrapper over the hoisted helper, which the
            classification pass shares for identical wording."""
            _alis_hit_address_note(result, r, address, st_num, st_word, what)

        # --- Targeted verification (--verify-grantor-hit) ---
        target_hit = None
        if verify_grantor_hit:
            vb, _, vp = verify_grantor_hit.partition("/")
            vb, vp = _norm_num(vb.strip()), _norm_num(vp.strip())
            for r in grantor_rows:
                if r.get("land_court"):
                    match = _norm_num(r.get("document_number")) == vb
                else:
                    match = (_norm_num(r.get("book")) == vb
                             and (not vp or _norm_num(r.get("page")) == vp))
                if match:
                    target_hit = r
                    break
            if target_hit is None:
                result["notes"].append(
                    f"--verify-grantor-hit {verify_grantor_hit} did not match "
                    "any grantor-check hit. Hits found: "
                    + (", ".join(_alis_row_id(r) for r in grantor_rows) or "none")
                    + ". (The hit must come from the same searches the check "
                    "runs — see the grantor-search notes above.)"
                )
            else:
                vfetch = _alis_fetch_deed_files(
                    session, base_url, target_hit, base_name, output_folder,
                    result["notes"], result["errors"], label=_hit_label(target_hit),
                )
                result["grantor_hit_verification"] = {
                    **_hit_meta(target_hit),
                    "files": vfetch["files"],
                    "extraction": None,
                }
                if not vfetch["ok"]:
                    result["notes"].append(
                        f"--verify-grantor-hit: download FAILED for "
                        f"{_alis_row_id(target_hit)} — see errors."
                    )

        # --- Page-1 samples for conveyance-type hits ---
        # v3.16 — pre-acquisition hits are not sampled: a conveyance
        # recorded before the seller acquired the subject property cannot
        # be a deed-out of it (Renwick: 3 of 5 sampled hits predated the
        # acquisition). They stay in grantor_check.deeds. Unparseable
        # dates are still sampled (safe default).
        acq_date = _parse_deed_date(row.get("date_received") or "")
        pre_acq_unsampled = 0
        conveyance_hits = []
        for r in grantor_rows:
            dt = (r.get("doc_type") or "").strip()
            # v3.36 (item 0a): grantor role — sample UNKNOWN types too. They
            # are exactly the rows whose parcel question is still open; the
            # wrapper's selection-role default would skip them.
            if _classify_instrument(dt) == "non_conveyance":
                continue
            if (target_hit is not None
                    and _alis_instrument_id(r) == _alis_instrument_id(target_hit)):
                continue
            if acq_date > (0, 0, 0):
                rd = _parse_deed_date(r.get("date_received") or "")
                if (0, 0, 0) < rd < acq_date:
                    pre_acq_unsampled += 1
                    continue
            conveyance_hits.append(r)
        if pre_acq_unsampled:
            result["notes"].append(
                f"{pre_acq_unsampled} pre-acquisition conveyance hit(s) not "
                "sampled (recorded before the seller acquired the subject "
                "property, so they cannot convey it away; still listed in "
                "grantor_check.deeds)."
            )
        if len(conveyance_hits) > _GRANTOR_HIT_SAMPLE_CAP:
            result["notes"].append(
                f"Grantor-hit sampling capped at {_GRANTOR_HIT_SAMPLE_CAP} of "
                f"{len(conveyance_hits)} conveyance-type hit(s) — assess the "
                "rest from the index rows or verify one with "
                "--verify-grantor-hit."
            )
        samples = []
        abstract_resolved = 0
        for r in conveyance_hits[:_GRANTOR_HIT_SAMPLE_CAP]:
            entry = {**_hit_meta(r), "sample_file": None, "sample_extraction": None,
                     "abstract_addresses": [], "abstract_url": None}
            # v3.22 — the abstract answers "which parcel?" for a grantor hit
            # with one GET. Only download and vision-read a page-1 sample
            # when the abstract carries no address. v3.23 — the
            # classification pass usually fetched it already; reuse the
            # cached copy ({} counts: it means "fetched, empty" — refetching
            # cannot help).
            if "_abstract" in r:
                hit_abs = r["_abstract"]
            else:
                hit_abs = _alis_fetch_abstract_http(session, base_url, r, result["notes"])
            hit_addrs = _alis_abstract_address_strings(hit_abs)
            if hit_abs:
                entry["abstract_url"] = hit_abs.get("url")
                entry["abstract_addresses"] = hit_addrs
            if hit_addrs:
                abstract_resolved += 1
                # Compare every listed address; a multi-parcel deed conveys
                # the subject away if ANY of its parcels is the subject.
                # v3.23 — skip the note when classification already emitted
                # it for this row (subject / possible-subject hits).
                if not r.get("_class_noted"):
                    matched = next(
                        (a for a in hit_addrs
                         if _alis_address_matches(st_num, st_word, a)), None)
                    _hit_address_note(r, matched or hit_addrs[0], "registry abstract")
            else:
                info = _alis_get_pdf_hrefs_http(session, base_url, r["img_href"])
                if info["pdf_hrefs"]:
                    saved, errs = _alis_download_pdfs_http(
                        session, base_url, info["pdf_hrefs"][:1],
                        base_name, output_folder, label=_hit_label(r),
                    )
                    result["errors"] += errs
                    if saved:
                        entry["sample_file"] = saved[0]
            samples.append(entry)
        result["grantor_check"]["samples"] = samples
        if abstract_resolved:
            result["notes"].append(
                f"Grantor-hit parcel check (v3.22): {abstract_resolved} of "
                f"{len(samples)} sampled hit(s) resolved from the registry "
                "abstract — no PDF download or model call needed."
            )

        # --- Extraction for the samples + the verified hit ---
        need_extract = ([s for s in samples if s["sample_file"]]
                        or (result["grantor_hit_verification"] or {}).get("files"))
        if extract_pdf and need_extract and result.get("extraction_unavailable"):
            # v3.28 — the API already failed in a way that will fail again;
            # name the PDFs instead of making N more doomed calls.
            pending = [Path(s["sample_file"]).name for s in samples if s["sample_file"]]
            pending += [Path(f).name for f in
                        ((result["grantor_hit_verification"] or {}).get("files") or [])]
            result["notes"].append(
                "READ THESE GRANTOR-HIT PDFs to answer the which-parcel "
                "question — extraction is unavailable for the rest of this "
                f"run ({result['extraction_unavailable']}), so these samples "
                "were downloaded but not extracted: " + ", ".join(pending)
            )
        elif extract_pdf and need_extract:
            client, reason = _anthropic_client()
            if client is None:
                result["notes"].append(
                    f"Grantor-hit extraction skipped ({reason}) — Read the "
                    "sample/verification PDFs to assess the hits."
                )
            else:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    jobs = []
                    for i, s in enumerate(samples):
                        if s["sample_file"]:
                            jobs.append((("sample", i), pool.submit(
                                _extract_pdf_fields_light, client, [s["sample_file"]],
                                _GRANTOR_HIT_SCHEMA,
                                "This is page 1 of an instrument the seller "
                                "(or a co-owner) executed as GRANTOR after "
                                "acquiring the subject property. Extract the "
                                "property address, lot/unit, and parties so "
                                "it can be determined whether it affects the "
                                "subject parcel.",
                            )))
                    ver = result["grantor_hit_verification"]
                    if ver and ver["files"]:
                        jobs.append((("verify", None), pool.submit(
                            _extract_pdf_fields, client, ver["files"],
                            _DEED_SCHEMA,
                            "This is a suspected subsequent conveyance "
                            "(deed-out) by the seller of the subject "
                            "property, surfaced by a grantor-index search. "
                            "Extract the requested fields.",
                        )))
                    for (kind, i), job in jobs:
                        try:
                            fields = job.result()
                        except Exception as e:
                            fields = {"error": f"{type(e).__name__}: {e}"}
                            # v3.28 — an account/credentials failure here
                            # (extraction was fine for the deed and died
                            # mid-run) latches the same way.
                            _mark_extraction_unavailable(result, e)
                        if kind == "sample":
                            # v3.16 — escalation: if the light model read a
                            # street-name match without a confirmable number,
                            # re-read with the main model before concluding
                            # (Renwick Bk39044/162: Haiku returned 'Cloverfield
                            # Avenue' with no number, which would have
                            # downgraded a real deed-out of the subject).
                            if "error" not in fields and st_num and st_word:
                                addr = fields.get("property_address")
                                if (not _alis_address_matches(st_num, st_word, addr)
                                        and _alis_street_word_matches(st_word, addr)):
                                    try:
                                        fields = _extract_pdf_fields(
                                            client, [samples[i]["sample_file"]],
                                            _GRANTOR_HIT_SCHEMA,
                                            "This is page 1 of an instrument the "
                                            "seller executed as GRANTOR. Extract "
                                            "the property address, lot/unit, and "
                                            "parties. Read the STREET NUMBER "
                                            "carefully, including margin "
                                            "notations, stamps, and the granting "
                                            "clause.",
                                            model=_EXTRACT_MODEL_MAIN,
                                        )
                                        result["notes"].append(
                                            f"Grantor hit "
                                            f"{_alis_row_id(conveyance_hits[i])}: "
                                            "street-name match without a number "
                                            "from the light model — re-extracted "
                                            "with the main model."
                                        )
                                    except Exception:
                                        pass  # keep the light-model fields
                            samples[i]["sample_extraction"] = fields
                            if "error" not in fields:
                                _hit_address_note(
                                    conveyance_hits[i], fields.get("property_address"),
                                    "page-1 sample")
                        else:
                            result["grantor_hit_verification"]["extraction"] = fields
                            if "error" not in fields:
                                _hit_address_note(
                                    target_hit, fields.get("property_address"),
                                    "full extraction via --verify-grantor-hit")
        elif not extract_pdf and need_extract:
            # v3.27 — name the files: in claude-code mode these are an
            # instruction, not a warning. Only hits whose registry abstract
            # carried no address get here (v3.22+ answers the rest).
            result["notes"].append(
                "READ these grantor-hit sample PDF(s) to answer the "
                "which-parcel question (claude-code extraction mode; the "
                "registry abstract carried no address for them): "
                + ", ".join(
                    Path(f).name for f in
                    ([s["sample_file"] for s in samples if s["sample_file"]]
                     + list((result.get("grantor_hit_verification") or {}).get("files") or []))
                )
            )
    except Exception as e:
        result["notes"].append(f"Grantor-hit sampling/verification failed (non-fatal): {e}")

    result["status"] = "success" if result["files"] else "error"
    if not result["files"] and not result["errors"]:
        result["errors"].append("No files downloaded.")

    # v3.31 — finalise timings here rather than at the return, because the
    # report footer below reads them. Report rendering is therefore the one
    # stage not measured; it cannot report its own duration anyway.
    _tm.finish(result)
    # -----------------------------------------------------------
    # STEP 9 — MARKDOWN REPORT DRAFT (v3.16, non-fatal)
    # -----------------------------------------------------------
    try:
        _write_markdown_report(
            result, base_name, f"{seller_first} {seller_last}".strip(),
            output_folder, show_timings=show_timings,
        )
    except Exception as e:
        result["notes"].append(f"Report draft failed (non-fatal): {e}")
    return result


async def run_barnstable(
    seller_last: str,
    seller_first: str,
    base_name: str,
    output_folder: Path,
    headless: bool,
    town: str = "BARN",
) -> dict:
    """
    Barnstable County Registry of Deeds — full workflow:
    1. Grantee search (Recorded Land, then Land Court fallback)
    2. Select best deed row
    3. Document Image List → extract individual-page PDF hrefs
    4. Download PDFs via page.request.get()
    5. Grantor check (last name only, blank first — catches joint owners)
    """
    result = {
        "status": "error",
        "registry": "Barnstable County",
        "registry_url": f"{BARNSTABLE_BASE}/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N",
        "registry_system": "Browntech ALIS",
        "land_court": False,
        "book": None,
        "page": None,
        "ctl_num": None,
        "certificate_of_title": None,  # Land Court only — read from the search index
        "document_number": None,   # Land Court: from search index | Recorded Land: from PDF
        "recorded_date": None,
        "deed_type": None,
        "consideration": None,     # extracted from PDF by Claude
        "grantors": [],
        "grantees": [],
        "deed_property_address": None,
        "grantor_check": {"has_subsequent_deed": False, "deeds": []},
        "files": [],
        "total_pages_in_deed": None,
        "notes": [],
        "errors": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # -----------------------------------------------------------
            # STEP 1 — GRANTEE SEARCH (Recorded Land, then Land Court fallback)
            # -----------------------------------------------------------
            rows = []
            for land_court in (False, True):
                url = _alis_url(
                    BARNSTABLE_BASE, seller_last, seller_first, "E",
                    town=town, land_court=land_court, doc_type="*DD",
                )
                result["notes"].append(
                    f"Searching {'Land Court' if land_court else 'Recorded Land'}: {url}"
                )
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    # v3.23 — a hard-down registry (ERR_CONNECTION_REFUSED /
                    # _RESET / _TIMED_OUT) gets the same handling as the
                    # maintenance page: retry later, conclude nothing.
                    if "ERR_CONNECTION" not in str(e).upper():
                        raise
                    result["status"] = "registry_unavailable"
                    result["errors"].append(
                        "REGISTRY UNAVAILABLE: connection refused/failed "
                        "(hard-down outage). Do NOT treat as deed-not-found; "
                        "retry later.")
                    await browser.close()
                    return result
                if _alis_registry_unavailable_html(await page.content()):
                    result["status"] = "registry_unavailable"
                    result["errors"].append(
                        "REGISTRY UNAVAILABLE: maintenance page detected "
                        "(nightly backup / periodic maintenance). Do NOT "
                        "treat as deed-not-found; retry later.")
                    await browser.close()
                    return result
                rows = await _alis_parse_results(page)
                if rows:
                    result["land_court"] = land_court
                    result["notes"].append(
                        f"Found {len(rows)} result(s) in "
                        f"{'Land Court' if land_court else 'Recorded Land'}."
                    )
                    break
                result["notes"].append(
                    f"No results in {'Land Court' if land_court else 'Recorded Land'}."
                )

            if not rows:
                result["status"] = "deed_not_found"
                result["notes"].append(
                    f"No results for {seller_last}, {seller_first} as Grantee "
                    f"in Barnstable (town={town})."
                )
                await browser.close()
                return result

            # -----------------------------------------------------------
            # STEP 2 — SELECT BEST DEED ROW
            # -----------------------------------------------------------
            row = _alis_select_deed_row(rows)
            if row is None:
                result["status"] = "deed_not_found"
                result["notes"].append("Could not select a deed row from results.")
                await browser.close()
                return result

            result["notes"].append(
                "All rows: " + " | ".join(
                    f"[{_alis_row_id(r)} {r['doc_type']!r} {r['date_received']} "
                    f"{'cert=' + repr(r['certificate']) if r.get('land_court') else 'rev=' + repr(r['reverse_party'])}]"
                    for r in rows
                )
            )
            result["notes"].append(
                f"Selected: {row['doc_type']} {_alis_row_id(row)} {row['date_received']} | "
                + (f"Certificate: {row['certificate']}" if row.get("land_court")
                   else f"Grantor: {row['reverse_party']}")
                + f" | Grantee: {row['name']} | Desc: {row['doc_desc']}"
            )

            result["book"]          = row["book"] or None
            result["page"]          = row["page"] or None
            result["ctl_num"]       = row["ctl_num"]
            result["certificate_of_title"] = row["certificate"] or None
            result["document_number"] = row["document_number"] or None
            result["deed_type"]     = row["doc_type"]
            result["recorded_date"] = row["date_received"]
            # Land Court index has no opposite-party column — grantors stays
            # empty and Claude reads them from the deed PDF.
            result["grantors"]      = [row["reverse_party"]] if row["reverse_party"] else []
            result["grantees"]      = [row["name"]] if row["name"] else []
            result["deed_property_address"] = row["doc_desc"] or ""

            # -----------------------------------------------------------
            # STEP 3 — DOCUMENT IMAGE LIST → extract PDF hrefs
            # -----------------------------------------------------------
            img_info = await _alis_get_pdf_hrefs(page, BARNSTABLE_BASE, row["img_href"])
            pdf_hrefs = img_info["pdf_hrefs"]
            if not pdf_hrefs:
                # Surface the image list URL and any hrefs we found so Claude
                # can recover manually without re-navigating from the search.
                result["errors"].append(
                    f"Document Image List: no .PDF links found at {img_info['image_list_url']}"
                )
                result["image_list_url"] = img_info["image_list_url"]
                result["all_pdf_hrefs_on_image_list"] = img_info["all_pdfs"]
                await browser.close()
                return result

            if img_info["is_fallback"]:
                result["notes"].append(
                    "Document Image List: numbered-page pattern matched 0 links; "
                    f"using permissive fallback — selected {len(pdf_hrefs)} .PDF "
                    f"link(s): " + ", ".join(pdf_hrefs)
                )
            else:
                result["notes"].append(
                    f"Document Image List: {len(pdf_hrefs)} page(s) — " + ", ".join(pdf_hrefs)
                )

            result["total_pages_in_deed"] = len(pdf_hrefs)

            # -----------------------------------------------------------
            # STEP 4 — DOWNLOAD PDFs
            # -----------------------------------------------------------
            saved, dl_errors = await _alis_download_pdfs(
                page, BARNSTABLE_BASE, pdf_hrefs, base_name, output_folder
            )
            result["files"]  = saved
            result["errors"] += dl_errors
            if not saved:
                result["errors"].append("PDF download failed for all pages.")
                result["image_list_url"] = img_info["image_list_url"]
                result["all_pdf_hrefs_on_image_list"] = img_info["all_pdfs"]
                await browser.close()
                return result
            result["notes"].append(
                f"Downloaded {len(saved)} PDF(s): {[Path(f).name for f in saved]}"
            )

        except Exception as e:
            result["errors"].append(f"Main workflow failed: {e}")
            await browser.close()
            return result
        finally:
            try:
                await page.close()
            except Exception:
                pass

        # -----------------------------------------------------------
        # STEP 5 — GRANTOR CHECK (last name only, blank first = catches all joint owners)
        # -----------------------------------------------------------
        try:
            g_page = await context.new_page()
            _lc = result.get("land_court", False)
            grantor_rows = await _alis_grantor_check(
                g_page, BARNSTABLE_BASE, seller_last, town=town,
                original_id=(result.get("document_number") if _lc
                             else result.get("book")) or "",
                land_court=_lc,
            )
            result["grantor_check"]["has_subsequent_deed"] = len(grantor_rows) > 0
            result["grantor_check"]["deeds"] = [
                (
                    f"Doc#{r['document_number']} Ctf#{r['certificate']} {r['doc_type']} "
                    f"{r['date_received']} | Desc: {r['doc_desc']} | Ctl#: {r['ctl_num']}"
                    if r.get("land_court") else
                    f"Bk{r['book']}/{r['page']} {r['doc_type']} {r['date_received']} "
                    f"| Grantee: {r['reverse_party']} | Desc: {r['doc_desc']} | Ctl#: {r['ctl_num']}"
                )
                for r in grantor_rows
            ]
            if grantor_rows:
                result["notes"].append(
                    f"Grantor check: {len(grantor_rows)} subsequent deed(s) found — "
                    "Claude must assess title flags."
                )
            else:
                result["notes"].append(
                    "Grantor check: no subsequent deeds found — clean title."
                )
            await g_page.close()
        except Exception as e:
            result["notes"].append(f"Grantor check failed (non-fatal): {e}")

        await browser.close()

    result["status"] = "success" if result["files"] else "error"
    if not result["files"] and not result["errors"]:
        result["errors"].append("No files downloaded.")
    return result


# ---------------------------------------------------------------------------
# Norfolk County (Browntech ALIS — uses shared _alis_* helpers)
# ---------------------------------------------------------------------------

async def run_norfolk(
    seller_last: str,
    seller_first: str,
    base_name: str,
    output_folder: Path,
    headless: bool,
    town: str = "*ALL",
) -> dict:
    """
    Norfolk County Registry of Deeds — full workflow:
    1. Grantee search (Recorded Land, then Land Court fallback)
    2. Select best deed row
    3. Document Image List → extract individual-page PDF hrefs
    4. Download PDFs via page.request.get()
    5. Grantor check (last name only, blank first — catches joint owners)

    Norfolk runs identical Browntech ALIS software to Barnstable — the entire
    workflow body is parallel to run_barnstable() and shares the _alis_* helpers.
    The only differences are NORFOLK_BASE as the base URL and the town code
    convention (each Norfolk municipality has its own code; no umbrella default).
    """
    result = {
        "status": "error",
        "registry": "Norfolk County",
        "registry_url": f"{NORFOLK_BASE}/ALIS/WW400R.HTM?WSIQTP=LR01D&WSKYCD=N",
        "registry_system": "Browntech ALIS",
        "land_court": False,
        "book": None,
        "page": None,
        "ctl_num": None,
        "certificate_of_title": None,  # Land Court only — read from the search index
        "document_number": None,   # Land Court: from search index | Recorded Land: from PDF
        "recorded_date": None,
        "deed_type": None,
        "consideration": None,     # extracted from PDF by Claude
        "grantors": [],
        "grantees": [],
        "deed_property_address": None,
        "grantor_check": {"has_subsequent_deed": False, "deeds": []},
        "files": [],
        "total_pages_in_deed": None,
        "notes": [],
        "errors": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # -----------------------------------------------------------
            # STEP 1 — GRANTEE SEARCH (Recorded Land, then Land Court fallback)
            # -----------------------------------------------------------
            rows = []
            for land_court in (False, True):
                url = _alis_url(
                    NORFOLK_BASE, seller_last, seller_first, "E",
                    town=town, land_court=land_court, doc_type="*DD",
                )
                result["notes"].append(
                    f"Searching {'Land Court' if land_court else 'Recorded Land'}: {url}"
                )
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    # v3.23 — a hard-down registry (ERR_CONNECTION_REFUSED /
                    # _RESET / _TIMED_OUT) gets the same handling as the
                    # maintenance page: retry later, conclude nothing.
                    if "ERR_CONNECTION" not in str(e).upper():
                        raise
                    result["status"] = "registry_unavailable"
                    result["errors"].append(
                        "REGISTRY UNAVAILABLE: connection refused/failed "
                        "(hard-down outage). Do NOT treat as deed-not-found; "
                        "retry later.")
                    await browser.close()
                    return result
                if _alis_registry_unavailable_html(await page.content()):
                    result["status"] = "registry_unavailable"
                    result["errors"].append(
                        "REGISTRY UNAVAILABLE: maintenance page detected "
                        "(nightly backup / periodic maintenance). Do NOT "
                        "treat as deed-not-found; retry later.")
                    await browser.close()
                    return result
                rows = await _alis_parse_results(page)
                if rows:
                    result["land_court"] = land_court
                    result["notes"].append(
                        f"Found {len(rows)} result(s) in "
                        f"{'Land Court' if land_court else 'Recorded Land'}."
                    )
                    break
                result["notes"].append(
                    f"No results in {'Land Court' if land_court else 'Recorded Land'}."
                )

            if not rows:
                result["status"] = "deed_not_found"
                result["notes"].append(
                    f"No results for {seller_last}, {seller_first} as Grantee "
                    f"in Norfolk (town={town})."
                )
                await browser.close()
                return result

            # -----------------------------------------------------------
            # STEP 2 — SELECT BEST DEED ROW
            # -----------------------------------------------------------
            row = _alis_select_deed_row(rows)
            if row is None:
                result["status"] = "deed_not_found"
                result["notes"].append("Could not select a deed row from results.")
                await browser.close()
                return result

            result["notes"].append(
                "All rows: " + " | ".join(
                    f"[{_alis_row_id(r)} {r['doc_type']!r} {r['date_received']} "
                    f"{'cert=' + repr(r['certificate']) if r.get('land_court') else 'rev=' + repr(r['reverse_party'])}]"
                    for r in rows
                )
            )
            result["notes"].append(
                f"Selected: {row['doc_type']} {_alis_row_id(row)} {row['date_received']} | "
                + (f"Certificate: {row['certificate']}" if row.get("land_court")
                   else f"Grantor: {row['reverse_party']}")
                + f" | Grantee: {row['name']} | Desc: {row['doc_desc']}"
            )

            result["book"]          = row["book"] or None
            result["page"]          = row["page"] or None
            result["ctl_num"]       = row["ctl_num"]
            result["certificate_of_title"] = row["certificate"] or None
            result["document_number"] = row["document_number"] or None
            result["deed_type"]     = row["doc_type"]
            result["recorded_date"] = row["date_received"]
            # Land Court index has no opposite-party column — grantors stays
            # empty and Claude reads them from the deed PDF.
            result["grantors"]      = [row["reverse_party"]] if row["reverse_party"] else []
            result["grantees"]      = [row["name"]] if row["name"] else []
            result["deed_property_address"] = row["doc_desc"] or ""

            # -----------------------------------------------------------
            # STEP 3 — DOCUMENT IMAGE LIST → extract PDF hrefs
            # -----------------------------------------------------------
            img_info = await _alis_get_pdf_hrefs(page, NORFOLK_BASE, row["img_href"])
            pdf_hrefs = img_info["pdf_hrefs"]
            if not pdf_hrefs:
                # Surface the image list URL and any hrefs we found so Claude
                # can recover manually without re-navigating from the search.
                result["errors"].append(
                    f"Document Image List: no .PDF links found at {img_info['image_list_url']}"
                )
                result["image_list_url"] = img_info["image_list_url"]
                result["all_pdf_hrefs_on_image_list"] = img_info["all_pdfs"]
                await browser.close()
                return result

            if img_info["is_fallback"]:
                result["notes"].append(
                    "Document Image List: numbered-page pattern matched 0 links; "
                    f"using permissive fallback — selected {len(pdf_hrefs)} .PDF "
                    f"link(s): " + ", ".join(pdf_hrefs)
                )
            else:
                result["notes"].append(
                    f"Document Image List: {len(pdf_hrefs)} page(s) — " + ", ".join(pdf_hrefs)
                )

            result["total_pages_in_deed"] = len(pdf_hrefs)

            # -----------------------------------------------------------
            # STEP 4 — DOWNLOAD PDFs
            # -----------------------------------------------------------
            saved, dl_errors = await _alis_download_pdfs(
                page, NORFOLK_BASE, pdf_hrefs, base_name, output_folder
            )
            result["files"]  = saved
            result["errors"] += dl_errors
            if not saved:
                result["errors"].append("PDF download failed for all pages.")
                result["image_list_url"] = img_info["image_list_url"]
                result["all_pdf_hrefs_on_image_list"] = img_info["all_pdfs"]
                await browser.close()
                return result
            result["notes"].append(
                f"Downloaded {len(saved)} PDF(s): {[Path(f).name for f in saved]}"
            )

        except Exception as e:
            result["errors"].append(f"Main workflow failed: {e}")
            await browser.close()
            return result
        finally:
            try:
                await page.close()
            except Exception:
                pass

        # -----------------------------------------------------------
        # STEP 5 — GRANTOR CHECK (last name only, blank first = catches all joint owners)
        # Norfolk's grantor check uses town=*ALL so subsequent deeds are caught even
        # if the seller has moved to a different Norfolk municipality.
        # -----------------------------------------------------------
        try:
            g_page = await context.new_page()
            _lc = result.get("land_court", False)
            grantor_rows = await _alis_grantor_check(
                g_page, NORFOLK_BASE, seller_last, town="*ALL",
                original_id=(result.get("document_number") if _lc
                             else result.get("book")) or "",
                land_court=_lc,
            )
            result["grantor_check"]["has_subsequent_deed"] = len(grantor_rows) > 0
            result["grantor_check"]["deeds"] = [
                (
                    f"Doc#{r['document_number']} Ctf#{r['certificate']} {r['doc_type']} "
                    f"{r['date_received']} | Desc: {r['doc_desc']} | Ctl#: {r['ctl_num']}"
                    if r.get("land_court") else
                    f"Bk{r['book']}/{r['page']} {r['doc_type']} {r['date_received']} "
                    f"| Grantee: {r['reverse_party']} | Desc: {r['doc_desc']} | Ctl#: {r['ctl_num']}"
                )
                for r in grantor_rows
            ]
            if grantor_rows:
                result["notes"].append(
                    f"Grantor check: {len(grantor_rows)} subsequent deed(s) found — "
                    "Claude must assess title flags."
                )
            else:
                result["notes"].append(
                    "Grantor check: no subsequent deeds found — clean title."
                )
            await g_page.close()
        except Exception as e:
            result["notes"].append(f"Grantor check failed (non-fatal): {e}")

        await browser.close()

    result["status"] = "success" if result["files"] else "error"
    if not result["files"] and not result["errors"]:
        result["errors"].append("No files downloaded.")
    return result


_PLACEHOLDER_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_.]*\}")


def _unresolved_placeholders(args) -> list:
    """
    v3.31 — find argument values that still contain an unsubstituted
    `${...}` placeholder.

    The plugin's skill text parameterises its invocations with
    `${user_config.output_dir}` and friends, which the plugin host
    substitutes at enable time. When the plugin is loaded straight from a
    directory (`claude --plugin-dir`, the documented way to develop and
    test one) those values are NOT configured, and the placeholders reach
    the command line as literal text.

    `--output` is the dangerous one, and it fails silently without this
    check: `Path("${user_config.output_dir}").mkdir(parents=True)` cheerfully
    creates a directory with that literal name in the current working
    directory and writes a client's deed PDFs into it. Nothing errors, the
    run reports success, and the documents are somewhere nobody will look —
    possibly inside a git repository.

    So: refuse, name every offending argument, and say how to fix it. The
    house rule is that missing information must never be read as a value,
    and an unsubstituted placeholder is the purest form of that.
    """
    bad = []
    for name, value in sorted(vars(args).items()):
        if isinstance(value, str) and _PLACEHOLDER_RE.search(value):
            bad.append(f"--{name.replace('_', '-')} = {value!r}")
    return bad


# ---------------------------------------------------------------------------
# doctor — preflight environment check (v3.31)
# ---------------------------------------------------------------------------

_DOCTOR_PROBE_TIMEOUT = 12      # seconds per registry probe


def _doctor_wrap(text: str, width: int = 68) -> list:
    """Wrap a detail string so long remediation advice stays readable."""
    lines, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def _doctor_check_deps() -> list:
    """
    Report on every dependency, TIERED BY WHAT IT ACTUALLY BLOCKS.

    The tiering is the point. This tool has one hard requirement —
    requests + beautifulsoup4, which drive the pure-HTTP engine behind
    Norfolk and Barnstable — and several that matter only if you use the
    county or the feature that needs them. A flat "missing dependency"
    list would send a new user to install a browser engine they may never
    launch and, worse, imply the API key is required. It is not: in
    claude-code extraction mode every safety check (deed selection, the
    abstract-based wrong-parcel guard, the grantor check and its
    classification) runs with no key at all. Reporting a supported
    configuration as broken is a lie that costs someone an afternoon.

    Returns [{name, status, detail, blocks}], status in ok|missing|note.
    """
    out = []
    v = sys.version_info
    out.append({
        "name": f"Python {v.major}.{v.minor}.{v.micro}",
        "status": "ok" if v >= (3, 9) else "missing",
        "detail": "" if v >= (3, 9) else "Python 3.9 or newer is required.",
        "blocks": "everything",
    })
    out.append({
        "name": "requests + beautifulsoup4",
        "status": "ok" if _HTTP_AVAILABLE else "missing",
        "detail": "" if _HTTP_AVAILABLE else _HTTP_INSTALL_MSG,
        "blocks": "everything",
    })

    pw_detail = ""
    if _PLAYWRIGHT_AVAILABLE:
        # Importing playwright does NOT mean a browser exists: `pip install
        # playwright` and `playwright install chromium` are separate steps
        # and the second is the one people skip. Checking the executable
        # turns a mid-run launch failure into one preflight line.
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                exe = p.chromium.executable_path
            if exe and Path(exe).exists():
                pw_status = "ok"
            else:
                pw_status = "note"
                pw_detail = ("the playwright package is installed but its "
                             "Chromium build is not. Run: python -m playwright "
                             "install chromium")
        except Exception as e:
            pw_status = "note"
            pw_detail = (f"playwright imported but its browser could not be "
                         f"located ({type(e).__name__}). Run: python -m "
                         f"playwright install chromium")
    else:
        pw_status = "note"
        pw_detail = _PLAYWRIGHT_INSTALL_MSG
    out.append({
        "name": "playwright + chromium",
        "status": pw_status,
        "detail": pw_detail,
        "blocks": "Plymouth and Middlesex South only — Norfolk and "
                  "Barnstable never launch a browser",
    })

    client, why = _anthropic_client()
    out.append({
        "name": "anthropic SDK + credentials",
        "status": "ok" if client else "note",
        "detail": "" if client else (
            f"{why}. This is NOT a problem — the plugin is fully usable "
            "without it. RECOMMENDED THOUGH: with a key the deed's legal "
            "description and fields come back in ONE API call and the run "
            "finishes on its own. Without it the plugin runs in claude-code "
            "extraction mode, where Claude reads the downloaded deed PDFs "
            "in-session — same results, but slower and with a few manual "
            "steps per run. The registry search, the wrong-parcel guard and "
            "the grantor check never use the API in any mode."),
        "blocks": "nothing — the run is slower and needs manual PDF reading",
    })

    try:
        import docx           # noqa: F401
        docx_ok = True
    except Exception:
        docx_ok = False
    out.append({
        "name": "python-docx",
        "status": "ok" if docx_ok else "note",
        "detail": "" if docx_ok else ("not installed — --docx is skipped with a "
                                      "note. Run: python -m pip install python-docx"),
        "blocks": "nothing — only --docx output",
    })
    return out


def _doctor_probe_registry(label: str, url: str) -> dict:
    """
    Probe one registry. Distinguishes three outcomes where a naive
    reachability check sees two, and the third is the one that matters: a
    registry serving its nightly-backup maintenance page answers HTTP 200
    with zero result rows. This workflow treats that as
    `registry_unavailable` precisely so it can never be read as "no deed
    found", and doctor reports it the same way.
    """
    if not _HTTP_AVAILABLE:
        return {"name": label, "status": "skip",
                "detail": "requests/beautifulsoup4 not installed"}
    try:
        r = requests.get(url, timeout=_DOCTOR_PROBE_TIMEOUT,
                         headers=_ALIS_HTTP_HEADERS)
        body = (r.text or "")[:4000].lower()
        if any(w in body for w in ("maintenance", "nightly backup",
                                   "temporarily unavailable")):
            return {"name": label, "status": "maintenance",
                    "detail": f"HTTP {r.status_code}, but the page reads as a "
                              "maintenance/backup window. Retry later: a run "
                              "now aborts as registry_unavailable rather than "
                              "reporting a missing deed."}
        if r.status_code >= 400:
            return {"name": label, "status": "down",
                    "detail": f"HTTP {r.status_code}"}
        return {"name": label, "status": "ok", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"name": label, "status": "down",
                "detail": f"{type(e).__name__}: {e}"}


def _doctor_check_output_dir(path_str: str) -> dict:
    """Is the configured output folder real and writable?"""
    if not path_str:
        return {"name": "output folder", "status": "skip",
                "detail": "not checked — pass --output to include it"}
    p = Path(path_str)
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".ma-registry-doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"name": "output folder", "status": "ok", "detail": str(p)}
    except Exception as e:
        return {"name": "output folder", "status": "down",
                "detail": f"{p} is not writable — {type(e).__name__}: {e}"}


_DOCTOR_ICON = {"ok": "  OK  ", "missing": " FAIL ", "note": " note ",
                "down": " FAIL ", "skip": " skip ", "maintenance": " note "}


def run_doctor(output_dir: str = "", probe_network: bool = True) -> int:
    """
    Print the preflight report; return the process exit code — 0 when
    everything REQUIRED is present, 1 otherwise.

    Optional components print as notes and never fail the check. A
    keyless, browser-less install is a fully supported configuration for
    Norfolk and Barnstable, and a registry being down is not a broken
    install either — both say so in as many words.
    """
    print("ma-registry doctor — preflight check\n")
    hard_fail = False

    print("Dependencies")
    for d in _doctor_check_deps():
        print(f"[{_DOCTOR_ICON[d['status']]}] {d['name']}")
        for line in _doctor_wrap(d["detail"]):
            print(f"           {line}")
        if d["status"] != "ok":
            print(f"           blocks: {d['blocks']}")
        if d["status"] == "missing":
            hard_fail = True

    print("\nOutput")
    o = _doctor_check_output_dir(output_dir)
    print(f"[{_DOCTOR_ICON[o['status']]}] {o['name']}: {o['detail']}")
    if o["status"] == "down":
        hard_fail = True

    if probe_network:
        print("\nRegistries (live probe)")
        for label, url in (("Norfolk (norfolkresearch.org)", NORFOLK_BASE),
                           ("Barnstable (search.barnstabledeeds.org)", BARNSTABLE_BASE),
                           ("Plymouth (titleview.org)", PLYMOUTH_SEARCH),
                           # Suffolk sits behind Incapsula, which answers a
                           # scripted GET with a block page. The probe reports
                           # reachability only — a browser-driven run still
                           # works when this line looks unhappy.
                           ("Suffolk (masslandrecords.com)", SUFFOLK_SEARCH)):
            p = _doctor_probe_registry(label, url)
            print(f"[{_DOCTOR_ICON[p['status']]}] {p['name']} — {p['detail']}")
            if p["status"] == "down":
                print("           the registry is unreachable right now; that "
                      "is not a problem with your install.")
    else:
        print("\nRegistries: skipped (--no-network)")

    print("\n" + ("FAIL — a required component is missing (see above)."
                  if hard_fail else
                  "OK — ready to run. Norfolk and Barnstable need neither a "
                  "browser nor an API key."))
    return 1 if hard_fail else 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _finish_run(result: dict, args, output_folder: Path) -> None:
    """
    STEP 7 delivery + result.json + stdout + exit code.

    v3.41: factored out of main() so the delivery-only re-entry path and the
    ordinary end-of-run path cannot drift apart — the whole point of the
    re-entry is that it produces byte-identical delivery output without the
    search, which is only true if it runs the same code. Never returns.
    """
    if getattr(args, "deliver_text_file", ""):
        try:
            _supplied = Path(args.deliver_text_file).read_text(encoding="utf-8").strip()
            if not _supplied:
                result.setdefault("notes", []).append(
                    f"--deliver-text-file {args.deliver_text_file!r} is empty "
                    "— nothing delivered.")
            else:
                result["legal_description"] = _supplied
                # Delivery is gated on status == "success"; a claude-code run
                # that found and downloaded its deed qualifies.
                if result.get("status") != "success" and result.get("files"):
                    result["status"] = "success"
                result.setdefault("notes", []).append(
                    f"Legal description supplied via --deliver-text-file "
                    f"({len(_supplied)} chars, read from "
                    f"{Path(args.deliver_text_file).name}) — delivering the "
                    "paste-ready forms from it. NOTE: this text was NOT read "
                    "off the deed by this script; whoever supplied it owns "
                    "its accuracy against the recorded instrument."
                )
        except Exception as e:
            result.setdefault("notes", []).append(
                f"--deliver-text-file could not be read (non-fatal): {e}")
    try:
        _deliver_legal_description(
            result, args.base_name, output_folder,
            copy_to_clipboard=args.copy, write_docx=args.docx,
        )
    except Exception as e:
        result.setdefault("notes", []).append(
            f"Legal-description delivery failed (non-fatal): {e}")

    # v3.30 (item 9b) — write the result beside the PDFs BEFORE printing, so
    # an unredirected run (or one whose stdout tail is truncated by the
    # caller) no longer loses needs_review/book/page to the terminal.
    _write_result_json(result, args.base_name, output_folder)
    print(json.dumps(result, indent=2))

    status = result.get("status")
    sys.exit(0 if status == "success" else 2 if status == "deed_not_found" else 1)


# Notes produced BY a delivery pass. On a delivery-only re-entry the prior
# run's copies are stale — regenerating them without dropping these would
# print "copied to clipboard" twice and read like two deliveries happened.
_DELIVERY_NOTE_PREFIXES = (
    "Legal-description .txt written",
    "Legal-description .docx written",
    "Paste-ready legal description copied to clipboard",
    "Paste-ready legal description could not be copied",
    "Legal description supplied via --deliver-text-file",
    "Legal-description delivery failed",
    "DELIVERY-ONLY RE-ENTRY",
)


def _deliver_only(prior: dict, args, output_folder: Path,
                  prior_path: Path) -> None:
    """Delivery-only re-entry (v3.41): no search, same delivery. Never returns."""
    prior["notes"] = [
        n for n in (prior.get("notes") or [])
        if not str(n).startswith(_DELIVERY_NOTE_PREFIXES)
    ]
    prior["delivery_only_reentry"] = True
    prior["notes"].append(
        f"DELIVERY-ONLY RE-ENTRY (v3.41): no search was run. Every registry "
        f"field below was read from {prior_path.name} as recorded by the "
        "earlier run; only the legal-description delivery is new. Re-run "
        "without --deliver-text-file to refresh the registry data itself.")
    _finish_run(prior, args, output_folder)


def main() -> None:
    # Declared up front: --model-main/--model-light rebind these below, and
    # Python rejects a `global` that appears after the name is first used.
    global _EXTRACT_MODEL_MAIN, _EXTRACT_MODEL_LIGHT

    # v3.31 — `--doctor` is handled before the main parser because that
    # parser requires --registry/--last/--first/--base-name/--output, and a
    # preflight check that cannot run until you have a search to run is
    # useless. Its own parser accepts the two flags it needs and ignores
    # the rest.
    if "--doctor" in sys.argv:
        dp = argparse.ArgumentParser(add_help=False)
        dp.add_argument("--doctor", action="store_true")
        dp.add_argument("--output", default="")
        dp.add_argument("--no-network", dest="network",
                        action="store_false", default=True)
        dargs, _ = dp.parse_known_args()
        sys.exit(run_doctor(dargs.output, probe_network=dargs.network))

    parser = argparse.ArgumentParser(
        description="Playwright fast-path for Legal Description Search Workflow"
    )
    parser.add_argument("--doctor", action="store_true",
                        help="v3.31: check the environment (dependencies, "
                             "Chromium install, API credentials, output "
                             "folder, registry reachability) and exit. Needs "
                             "none of the search arguments; --output is "
                             "checked when given and --no-network skips the "
                             "live registry probes.")
    parser.add_argument("--no-network", dest="network", action="store_false",
                        default=True,
                        help="With --doctor: skip the live registry probes.")
    parser.add_argument("--registry", required=True,
                        choices=["plymouth", "norfolk", "barnstable", "suffolk",
                                 "middlesex-south", "middlesex_south", "middlesexsouth"])
    parser.add_argument("--last",      required=True,  help="Seller last name")
    parser.add_argument("--first",     required=True,
                        help="Seller first name (compound names without spaces, e.g. JEANMARIE)")
    parser.add_argument("--base-name", required=True,
                        help="Base filename for images, e.g. '62 Halyard Way Plymouth - Donnelly'")
    parser.add_argument("--output",    required=True,  help="Output folder path")
    parser.add_argument("--town",       default="",
                        help="Town name or registry abbreviation for result filtering. "
                             "Plymouth: e.g. 'Scituate' or 'SCIT'. "
                             "Barnstable: town name (e.g. 'Dennis') or ALIS code (e.g. DENN, FALM, YARM). "
                             "If omitted, auto-derived from --base-name; falls back to BARN if unrecognized. "
                             "Norfolk: town name (e.g. 'Braintree') or ALIS code "
                             "(e.g. BRAI, QUIN, WEYM). If omitted, auto-derived from "
                             "--base-name; falls back to *ALL if unrecognized.")
    parser.add_argument("--headed", dest="headless", action="store_false", default=True,
                        help="Run with a visible browser window (default: headless — "
                             "pass --headed to watch the browser for debugging)")
    parser.add_argument("--street-number", default="",
                        help="Property street number for Plymouth address-search fallback "
                             "(auto-parsed from --base-name first numeric token if omitted)")
    parser.add_argument("--street", default="",
                        help="Property street name (first word recommended) for Plymouth "
                             "address-search fallback (auto-parsed from --base-name second "
                             "token if omitted)")
    parser.add_argument("--office", choices=["auto", "recorded", "registered"],
                        default="auto",
                        help="Suffolk, Norfolk and Barnstable: which index to search. "
                             "'auto' (default) searches BOTH Recorded Land and "
                             "Registered Land (Land Court) and selects across the "
                             "combined candidates — a Land Court parcel's vesting "
                             "deed is invisible to a Recorded Land search. Use "
                             "'recorded' or 'registered' to pin one index.")
    parser.add_argument("--force-address-search", action="store_true",
                        help="Plymouth and Suffolk: skip grantee name search entirely and go "
                             "directly to property address search. Requires --street-number "
                             "and --street (or a parseable --base-name).")
    parser.add_argument("--engine", choices=["auto", "http", "playwright"],
                        default="auto",
                        help="Norfolk/Barnstable only. 'http' = pure-HTTP engine "
                             "(requests+bs4, seconds instead of minutes); 'playwright' = "
                             "browser engine; 'auto' (default) = HTTP with automatic "
                             "Playwright fallback on hard HTTP failure.")
    parser.add_argument("--book", default="",
                        help="Norfolk/Barnstable (HTTP engine) and Plymouth: target a "
                             "specific instrument instead of the most-recent heuristic — "
                             "book number (Recorded Land) or document number (ALIS Land "
                             "Court). Use after a multiple_deed_candidates result "
                             "identified the correct deed, or when the vesting deed's "
                             "Bk/Pg is already known. Plymouth opens it by Book Search "
                             "and requires --page.")
    parser.add_argument("--page", default="",
                        help="Page number to pair with --book (Recorded Land only).")
    parser.add_argument("--verify-grantor-hit", default="",
                        help="Norfolk/Barnstable (HTTP engine) and Plymouth: fully download "
                             "and extract ONE grantor-check hit to confirm a "
                             "suspected deed-out — 'BOOK/PAGE' (Recorded Land) or "
                             "document number (ALIS Land Court); Plymouth requires "
                             "BOOK/PAGE. The hit must appear in "
                             "the grantor check's results. Result lands in the "
                             "grantor_hit_verification JSON field. Combine with "
                             "--book/--page to keep the main deed selection pinned.")
    parser.add_argument("--no-land-court-tripwire", dest="land_court_tripwire",
                        action="store_false", default=True,
                        help="v3.46 (item 28): skip the NAME-INDEPENDENT Land "
                             "Court tripwire on the combined address index. It "
                             "costs ~2s and runs only on a Recorded Land "
                             "selection. Turn it off for offline/replay runs — "
                             "it is the only step here that makes an extra "
                             "live registry request.")
    parser.add_argument("--lien-sweep", action="store_true", default=False,
                        help="v3.38: also run the all-years, type-restricted "
                             "LIEN SWEEP for each owner (tax liens, "
                             "executions, attachments, bankruptcies against "
                             "the person). OFF by default — it answers a "
                             "different question from this workflow's "
                             "(who owns the parcel / who signs), and it is "
                             "the slowest remaining part of the grantor "
                             "check. When it does not run, the notes say so.")
    parser.add_argument("--no-timings", dest="timings", action="store_false",
                        default=True,
                        help="v3.31: omit the per-stage timing footer from the "
                             "report draft. Timings are always recorded in the "
                             "result JSON (they cost one clock read per stage "
                             "and are what diagnosed the grantor check as 85%% "
                             "of a slow run); this only controls the report.")
    parser.add_argument("--extraction", choices=("auto", "api", "claude-code"),
                        default="auto",
                        help="v3.27 (Norfolk/Barnstable HTTP engine; Plymouth since "
                             "v3.47, on its downloaded page images): how the deed "
                             "PDFs get read. 'auto' (default) uses the Claude API "
                             "when ANTHROPIC_API_KEY and the anthropic SDK are "
                             "available and otherwise runs in claude-code mode; "
                             "'api' forces the API and errors out clearly if it is "
                             "unavailable; 'claude-code' skips the API entirely and "
                             "has Claude read the downloaded PDFs. The registry "
                             "search, the abstract-based wrong-parcel guard, the "
                             "grantor check and its classification need no API in "
                             "any mode.")
    parser.add_argument("--no-extract-pdf-text", dest="extract_pdf",
                        action="store_false", default=True,
                        help="Deprecated alias for --extraction claude-code "
                             "(kept so existing invocations keep working).")
    parser.add_argument("--model-main", default=_EXTRACT_MODEL_MAIN,
                        help="Model for the main deed extraction and "
                             "--verify-grantor-hit (default: %(default)s). Also "
                             "settable via MA_REGISTRY_MODEL_MAIN.")
    parser.add_argument("--model-light", default=_EXTRACT_MODEL_LIGHT,
                        help="Model for page-1 sample extractions (default: "
                             "%(default)s). Also settable via "
                             "MA_REGISTRY_MODEL_LIGHT.")
    parser.add_argument("--copy", action="store_true",
                        help="v3.19: on success, copy the paste-ready legal "
                             "description to the system clipboard "
                             "(Set-Clipboard / pbcopy / xclip — no extra "
                             "dependency; failure is a note, never an error).")
    parser.add_argument("--docx", action="store_true",
                        help="v3.19: also write the legal description as a "
                             ".docx (requires python-docx; skipped with a "
                             "note if unavailable).")
    parser.add_argument("--deliver-text-file", default="",
                        help="v3.27, claude-code extraction mode: path to a "
                             "UTF-8 text file holding the legal description "
                             "Claude transcribed from the deed PDFs. The "
                             "script re-enters delivery with it, so a no-API "
                             "run still gets the same three-form .txt "
                             "(plus --copy / --docx) as an API run instead of "
                             "the description being hand-assembled. Combine "
                             "with the same --base-name/--output as the "
                             "original run. Nothing else is re-fetched.")
    args = parser.parse_args()

    # CLI flags win over the environment, which wins over the built-in
    # defaults. Rebinding the module globals keeps every existing call site
    # (which reads these names directly) working unchanged. See the `global`
    # declaration at the top of main().
    _EXTRACT_MODEL_MAIN = args.model_main
    _EXTRACT_MODEL_LIGHT = args.model_light

    # v3.31 — refuse unsubstituted `${user_config.*}` placeholders before
    # anything is created on disk. See _unresolved_placeholders.
    _placeholders = _unresolved_placeholders(args)
    if _placeholders:
        print(json.dumps({
            "status": "error",
            "notes": [],
            "errors": [
                "Unsubstituted plugin configuration placeholder(s) reached the "
                "command line: " + "; ".join(_placeholders) + ". No search was "
                "performed and nothing was written. This happens when the "
                "plugin is loaded with `claude --plugin-dir` (or otherwise "
                "without its configuration), so ${user_config.*} values were "
                "never filled in. Fix: pass real values on the command line — "
                "in particular --output must be an actual folder path, or the "
                "run would have created a directory literally named "
                "'${user_config.output_dir}' and written client documents "
                "into it."
            ],
        }, indent=2))
        sys.exit(1)

    # v3.35 (item 14) — flags only the ALIS HTTP engine implements must be
    # REFUSED, never silently ignored. `--verify-grantor-hit` on
    # `--registry plymouth` used to run the whole search and return
    # `grantor_hit_verification: null` at exit 0 with no note and no error —
    # indistinguishable from a clean verification, on the exact path the
    # run's own CRITICAL note sends the operator down ("Verify before
    # closing"). Same family as the v3.27 `--extraction api` pre-flight:
    # if the request is knowably unsatisfiable, fail before any work.
    # `--book/--page` are the same class (silently ignored → the heuristic
    # pick reports at exit 0 as if the pin was honored).
    _http_only = [f for f, v in (
        ("--verify-grantor-hit", args.verify_grantor_hit),
        ("--book", args.book),
        ("--page", args.page),
    ) if v]
    # v3.50 — Plymouth implements all three via Book Search, but Book
    # Search is addressed by Book AND Page, so a half-specified request is
    # refused here rather than discovered mid-run.
    if args.registry == "plymouth":
        _ply_err = None
        if bool(args.book) != bool(args.page):
            _ply_err = ("--registry plymouth needs --book AND --page together "
                        "(Recorded Land Book Search is addressed by both).")
        elif args.verify_grantor_hit and "/" not in args.verify_grantor_hit:
            _ply_err = ("--registry plymouth needs --verify-grantor-hit as "
                        "BOOK/PAGE (e.g. 12345/67).")
        if _ply_err:
            print(json.dumps({"status": "error", "notes": [],
                              "errors": [_ply_err + " No search was performed."]},
                             indent=2))
            sys.exit(1)
    if _http_only and args.registry != "plymouth" and (
            args.registry not in ("norfolk", "barnstable")
            or args.engine == "playwright"):
        _why = (f"--registry {args.registry}"
                if args.registry not in ("norfolk", "barnstable")
                else "--engine playwright")
        _fix = ("Re-run with --engine auto (or http)."
                if args.registry in ("norfolk", "barnstable")
                else "Re-run without the flag(s); verify a grantor hit on "
                     "this registry by opening the instrument's images via "
                     "the registry UI or the detail panel.")
        print(json.dumps({
            "status": "error",
            "notes": [],
            "errors": [
                f"{_why} does not implement {', '.join(_http_only)} — these "
                f"are implemented only by the ALIS HTTP engine (Norfolk/"
                f"Barnstable) and Plymouth. No "
                f"search was performed: running anyway would silently ignore "
                f"the flag(s) and exit 0 with a result that LOOKS like the "
                f"request was honored. " + _fix
            ],
        }, indent=2))
        sys.exit(1)

    output_folder = Path(args.output)
    output_folder.mkdir(parents=True, exist_ok=True)

    # v3.27 — resolve the extraction mode once, before any network work, so
    # `--extraction api` with no key fails immediately instead of after a
    # full search. The deprecated --no-extract-pdf-text forces claude-code.
    _requested = "claude-code" if not args.extract_pdf else args.extraction
    extract_pdf, extraction_mode, _mode_note, _mode_err = \
        _resolve_extraction_mode(_requested)
    if _mode_err:
        # Print + exit, do NOT `return` — main() returns None and the
        # JSON is printed at the bottom, so a bare return would exit 0
        # with no output at all.
        print(json.dumps({"status": "error",
                          "extraction_mode": args.extraction,
                          "notes": [], "errors": [_mode_err]}, indent=2))
        sys.exit(1)
    if not args.extract_pdf and args.extraction == "api":
        _mode_note = ((_mode_note or "") + " NOTE: --no-extract-pdf-text "
                      "(deprecated) overrode --extraction api.").strip()

    def _run_alis_registry(label: str, base_url: str, town: str,
                           grantor_town: str, pw_runner) -> dict:
        """
        Engine dispatch for the ALIS registries: HTTP first (v3.9 default),
        Playwright on request or as automatic fallback when the HTTP engine
        errors out (network failure, WAF, markup change).
        """
        want_http = args.engine in ("auto", "http")
        if want_http and not _HTTP_AVAILABLE and args.engine == "http":
            return {"status": "error", "notes": [], "errors": [_HTTP_INSTALL_MSG]}

        if want_http and _HTTP_AVAILABLE:
            try:
                result = run_alis_http(
                    label, base_url, args.last, args.first, args.base_name,
                    output_folder, town=town, grantor_town=grantor_town,
                    target_book=args.book, target_page=args.page,
                    extract_pdf=extract_pdf, extraction_mode=extraction_mode,
                    verify_grantor_hit=args.verify_grantor_hit,
                    show_timings=args.timings,
                    lien_sweep=args.lien_sweep,
                    land_court_tripwire=args.land_court_tripwire,
                    office=args.office,
                )
                if _mode_note:
                    result.setdefault("notes", []).insert(0, _mode_note)
            except AlisRegistryUnavailableError as e:
                # No Playwright fallback: the browser would load the same
                # maintenance page and parse it as zero rows — a false
                # deed_not_found. Exit 1, retry the whole run later.
                return {"status": "registry_unavailable", "engine": "http",
                        "notes": [
                            "REGISTRY UNAVAILABLE: the registry is serving its "
                            "maintenance page (nightly backup / periodic "
                            "maintenance). No search was performed — do NOT "
                            "treat this as deed-not-found. Retry when the "
                            "registry is back online."],
                        "errors": [str(e)]}
            except Exception as e:
                result = {"status": "error", "engine": "http",
                          "notes": [], "errors": [f"HTTP engine failed: {e}"]}
            if args.engine == "http" or result.get("status") in ("success", "deed_not_found"):
                return result
            http_errors = "; ".join(result.get("errors") or []) or "unknown error"
        else:
            http_errors = "" if args.engine == "playwright" else _HTTP_INSTALL_MSG

        # Playwright path (requested, or auto-fallback).
        if not _PLAYWRIGHT_AVAILABLE:
            return {"status": "error", "notes": [],
                    "errors": [f"HTTP engine unavailable/failed ({http_errors}) "
                               f"and {_PLAYWRIGHT_INSTALL_MSG}"]}
        if args.book:
            print(f"WARNING: --book/--page targeting is HTTP-engine only; "
                  f"the Playwright engine uses the most-recent heuristic.",
                  file=sys.stderr)
        if args.verify_grantor_hit:
            print(f"WARNING: --verify-grantor-hit is HTTP-engine only; "
                  f"the Playwright engine ignores it.",
                  file=sys.stderr)
        pw_result = asyncio.run(pw_runner(
            args.last, args.first, args.base_name, output_folder,
            args.headless, town=town,
        ))
        pw_result["engine"] = "playwright"
        # v3.35 (item 14): the stderr warnings above never reached the result
        # JSON — the channel the skill reads since v3.30 — so an auto-fallback
        # run that dropped --verify-grantor-hit returned
        # grantor_hit_verification: null at exit 0, indistinguishable from a
        # clean verification. (The pre-flight guard refuses an EXPLICIT
        # --engine playwright with these flags; this path is only reachable
        # via --engine auto after an HTTP failure, which cannot be known
        # pre-flight.) Say it in the result: in the field itself, not just a
        # note — null must never be the encoding for "did not run".
        if args.verify_grantor_hit:
            pw_result["grantor_hit_verification"] = {
                "status": "not_performed",
                "requested": args.verify_grantor_hit,
                "reason": "run fell back to the Playwright engine, which does "
                          "not implement --verify-grantor-hit",
            }
            pw_result.setdefault("notes", []).insert(0,
                f"WARNING: --verify-grantor-hit {args.verify_grantor_hit} was "
                f"NOT performed — the run fell back to the Playwright engine, "
                f"which does not implement it. The verification DID NOT RUN; "
                f"re-run when the HTTP engine is available before relying on "
                f"the hit's status.")
        if args.book:
            pw_result.setdefault("notes", []).insert(0,
                f"WARNING: --book/--page targeting was NOT applied — the run "
                f"fell back to the Playwright engine, which uses the "
                f"most-recent heuristic. Verify the selected instrument is "
                f"the intended one before relying on this result.")
        if http_errors:
            pw_result.setdefault("notes", []).insert(
                0, f"HTTP engine failed ({http_errors}) — fell back to Playwright.")
        return pw_result

    # -----------------------------------------------------------
    # DELIVERY-ONLY RE-ENTRY (v3.41)
    #
    # --deliver-text-file exists so a run whose deed text this script could
    # not extract (claude-code mode, or a registry with no inline extraction
    # at all, i.e. Suffolk and Middlesex South) can come back and get the
    # standard three-form paste-out instead of it being hand-assembled.
    #
    # Its help text has always promised "Nothing else is re-fetched", and
    # that was false: delivery runs AFTER the dispatch below, so coming back
    # for a text file re-ran the ENTIRE registry search — a second headful
    # browser launch, a second pass over every office, a second grantor
    # check. Measured on a live Suffolk run (2026-08-20):
    # ~60 s of the 6.2-minute total, spent re-deriving a result already
    # sitting on disk, and a needless second hit on the registry.
    #
    # The run's own result.json IS the record (v3.30), so delivery reads it
    # and skips the search. A missing or unreadable file falls through to a
    # normal run rather than failing — the file is an optimisation, not a
    # dependency.
    # -----------------------------------------------------------
    if args.deliver_text_file:
        _prior_path = Path(output_folder) / f"{args.base_name} - result.json"
        try:
            _prior = json.loads(_prior_path.read_text(encoding="utf-8"))
        except Exception as _e:
            _prior = None
            _prior_err = f"{type(_e).__name__}: {_e}"
        if isinstance(_prior, dict) and _prior.get("status") == "success":
            _deliver_only(_prior, args, output_folder, _prior_path)  # exits
        else:
            print(json.dumps({
                "status": "info",
                "message": (
                    f"--deliver-text-file: no successful prior run found at "
                    f"{_prior_path} ("
                    + ("unreadable: " + _prior_err if _prior is None else
                       "status=" + str(_prior.get('status')))
                    + ") — running the full search first, then delivering."),
            }), file=sys.stderr)

    if args.registry in ("plymouth", "middlesex-south", "middlesex_south",
                         "middlesexsouth", "suffolk") and not _PLAYWRIGHT_AVAILABLE:
        print(json.dumps({"status": "error",
                          "error_message": _PLAYWRIGHT_INSTALL_MSG}))
        sys.exit(1)

    # v3.54 (item 57) — the browser registries start their extraction as
    # soon as the page images are saved, so it runs during the grantor
    # check instead of after it. Only when extraction will run at all.
    _prefetch = _ImageExtractionPrefetch() if extract_pdf else None

    if args.registry == "plymouth":
        sn = args.street_number
        st = args.street
        if not sn or not st:
            sn_auto, st_auto = _parse_street_from_base_name(args.base_name)
            if not sn:
                sn = sn_auto
            if not st:
                st = st_auto
        # Auto-detect town from base_name if --town not provided (v2.7)
        resolved_town = args.town or _parse_town_from_base_name(args.base_name)
        result = asyncio.run(
            run_plymouth(
                args.last, args.first, args.base_name, output_folder,
                args.headless, town=resolved_town,
                street_number=sn, street_name=st,
                force_address_search=args.force_address_search,
                lien_sweep=args.lien_sweep,
                target_book=args.book or "", target_page=args.page or "",
                verify_grantor_hit=args.verify_grantor_hit or "",
                on_images_ready=_prefetch.start if _prefetch else None,
            )
        )
        # v3.47 (47b) — inline extraction + report draft, exactly as the
        # ALIS flow does after its grantor check. Delivery (.txt/.docx/
        # clipboard) follows in _finish_run for every registry.
        # v3.48 (item 42) — shared with Suffolk and Middlesex South.
        _finish_image_registry(
            result, args, output_folder, street_number=sn, street_name=st,
            extract_pdf=extract_pdf, extraction_mode=extraction_mode,
            mode_note=_mode_note, prefetch=_prefetch,
        )
        _plymouth_extract_verified_hit(
            result, extract_pdf=extract_pdf, street_number=sn, street_name=st)
    elif args.registry == "barnstable":
        barnstable_town, barnstable_notes = _barnstable_resolve_town(args.town, args.base_name)
        result = _run_alis_registry(
            "Barnstable County", BARNSTABLE_BASE,
            town=barnstable_town, grantor_town=barnstable_town,
            pw_runner=run_barnstable,
        )
        if barnstable_notes:
            result.setdefault("notes", []).extend(barnstable_notes)
    elif args.registry == "norfolk":
        # Resolve --town: accepts town name ('Braintree'), ALIS code ('BRAI'),
        # or empty (auto-derive from base_name). Returns *ALL on unknown town.
        # Norfolk's grantor check always uses *ALL so subsequent deeds are
        # caught even if the seller moved to a different Norfolk municipality.
        norfolk_town, norfolk_notes = _norfolk_resolve_town(args.town, args.base_name)
        result = _run_alis_registry(
            "Norfolk County", NORFOLK_BASE,
            town=norfolk_town, grantor_town="*ALL",
            pw_runner=run_norfolk,
        )
        # Surface town-resolution notes in the result so the user sees them
        if norfolk_notes:
            result.setdefault("notes", [])
            for n in norfolk_notes:
                result["notes"].insert(0, n)
    elif args.registry in ("middlesex-south", "middlesex_south", "middlesexsouth"):
        sn = args.street_number
        st = args.street
        if not sn or not st:
            sn_auto, st_auto = _parse_street_from_base_name(args.base_name)
            sn = sn or sn_auto
            st = st or st_auto
        result = asyncio.run(
            run_middlesex_south(
                args.last, args.first, args.base_name, output_folder,
                args.headless, street_number=sn, street_name=st,
                on_images_ready=_prefetch.start if _prefetch else None,
            )
        )
        # v3.48 (item 42) — inline extraction + report draft on the page
        # images this runner already saved at CNTHEIGHT=2000.
        _finish_image_registry(
            result, args, output_folder, street_number=sn, street_name=st,
            extract_pdf=extract_pdf, extraction_mode=extraction_mode,
            mode_note=_mode_note,
            stage_label="STEP 5 - inline extraction", prefetch=_prefetch,
        )
    elif args.registry == "suffolk":
        # Suffolk is browser-only: masslandrecords sits behind Incapsula, which
        # answers a scripted request with a block page (verified 2026-08-18 —
        # a plain GET returns 212 bytes of WAF HTML). Saying so beats letting
        # an --engine http run look like it chose a faster path.
        if args.engine == "http":
            print("WARNING: --engine http is not available on Suffolk "
                  "(Incapsula WAF blocks non-browser requests); running the "
                  "browser engine instead.", file=sys.stderr)
        sn = args.street_number
        st = args.street
        if not sn or not st:
            sn_auto, st_auto = _parse_street_from_base_name(args.base_name)
            sn = sn or sn_auto
            st = st or st_auto
        result = asyncio.run(
            run_suffolk(
                args.last, args.first, args.base_name, output_folder,
                args.headless, town=args.town,
                street_number=sn, street_name=st,
                office=args.office,
                force_address_search=args.force_address_search,
                lien_sweep=args.lien_sweep,
                on_images_ready=_prefetch.start if _prefetch else None,
            )
        )
        # v3.48 (item 42) — inline extraction + report draft. The stamp
        # check inside reads land_court off the result, because Suffolk
        # selects across both offices and either section can win.
        _finish_image_registry(
            result, args, output_folder, street_number=sn, street_name=st,
            extract_pdf=extract_pdf, extraction_mode=extraction_mode,
            mode_note=_mode_note,
            stage_label="STEP 7 - inline extraction", prefetch=_prefetch,
        )
    else:
        result = asyncio.run(run_stub(args.registry))

    # -----------------------------------------------------------
    # STEP 7 DELIVERY (v3.19, non-fatal) — runs for every registry
    # v3.27: --deliver-text-file lets a claude-code-mode run come back for
    # delivery once Claude has read the deed PDFs. Delivery only fires on a
    # populated legal_description, so without this a no-API run would have
    # to hand-assemble the three paste forms.
    # -----------------------------------------------------------
    _finish_run(result, args, output_folder)


if __name__ == "__main__":
    main()
