# Security and privacy reporting

## The report this project cares most about

Most projects' worst-case report is a vulnerability. This one's is different:

> **"Your repository contains a real person's name, address, or deed
> reference."**

This plugin was built while doing real conveyancing work, and the worked
examples throughout the code and docs come from real registry searches. Every
one of them has been pseudonymized — the client-identifying half of that map
is confidential and has never been committed — and a commit gate runs on every
change (`scripts/scrub_check.py`, plus a private name-identity verifier the
maintainer runs before pushing). That process has caught real leaks. It has
also *missed* real leaks that were then found by hand, which is exactly why
this page exists: the gate cannot be assumed sufficient.

**If you believe you have found a real identifier — a person, a street
address, a book/page or certificate number tied to an actual parcel — please
report it privately, not in a public issue.** A public issue would republish
the thing being reported, on a repository that already has it, with a bigger
audience.

## How to report privately

1. **Preferred:** GitHub → the **Security** tab → **Report a vulnerability**
   (private vulnerability reporting). It is private to the maintainer.
2. If that is unavailable, open a public issue containing **no specifics** —
   "possible identifier in `SKILL.md`, details sent privately" — and ask for a
   contact address.

Please include the file and line, and what makes you think it is real. You do
not need to be certain. A false alarm costs a look; the other error is
permanent, because git history survives a private-to-public flip.

## Scope

In scope, most to least urgent:

- A real client identifier anywhere in the tree **or in any commit in
  history**.
- A credential, API key, or absolute path naming a real user's home
  directory.
- A defect in the gate itself — `scripts/scrub_check.py` passing something it
  claims to block. The gate ships with a test that plants each violation and
  proves it fails; a case it does not cover is a real finding.
- Anything that would cause the plugin to **write outside its configured
  output folder**, or to transmit run data anywhere. It is designed to do
  neither: searches go to the public registry sites, deed text extraction goes
  to the Anthropic API only when a key is configured, and everything else —
  reports, deed images, run log, timings — stays on the local disk.

Out of scope:

- **Massachusetts town and village names.** They are deliberately kept
  throughout: they are load-bearing for the registry routing and
  town-abbreviation tables, and they identify nobody on their own.
- **Public registry data reached by running the tool.** Recorded instruments
  are public records; this project's concern is what gets *committed here*,
  not what a search returns on your machine.
- The registry websites themselves. If you operate one of these registries and
  want this traffic identified or throttled differently, please open an issue —
  see "Being a good citizen at the registry" in the README. That is a change
  worth making.

## What a fix looks like

For a leaked identifier, expect the maintainer to widen both halves of the
scrub — the applier and the verifier — add a regression case, and rewrite the
affected history rather than only the tip. A later commit does not remove
anything from a public repository's history.

## For contributors

CI runs only the structural half of the gate: it looks for client data by
*shape* (deed PDFs, images, run logs, home paths, credentials), and it needs no
list of real names by design. **A green CI run does not prove your patch is
free of real identifiers.** If you are adding a worked example, use an
obviously fictional name and parcel, or describe the shape of the problem
without a citation at all.
