# Universal Resume Studio — runnable demo + portable v2 specification

**What's inside:** The original local-only browser application (`app.py`/`core.py`) plus a configurable, generic **v2 reference engine** (`workflow_reference.py`), JSON schemas, policy configuration, questionnaire and system-prompt specification. **The v2 engine is independently executable and tested; it is not yet connected to the v0.1 browser UI or document generator.** A hosted multi-user production application and live employer verification still require development.

## Code-first entry points

```bash
# 1) Run the local v0.1 browser experience (DOCX/PDF export and optional local profile save)
python -m pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8765
# Open http://127.0.0.1:8765

# 2) Run the new, independent v2 policy screening code on fictional sample JSON
python workflow_reference.py --candidate examples/candidate.json \
  --job examples/job.json --employer examples/employer_evidence.json \
  --policy config/pipeline_policy.json --output out/assessment.json

# 3) Execute regression tests
python -m pip install pytest httpx
python -m pytest -q tests/
```

**Canonical system docs:** [`spec/ARCHITECTURE.md`](spec/ARCHITECTURE.md), [`spec/MASTER_SYSTEM_PROMPT.md`](spec/MASTER_SYSTEM_PROMPT.md), [`spec/API_CONTRACT.md`](spec/API_CONTRACT.md), [`config/pipeline_policy.json`](config/pipeline_policy.json), `schemas/*.schema.json` and [`QUESTIONNAIRE.md`](QUESTIONNAIRE.md).

---

# Resume Studio — Universal, evidence-first application builder (MVP)

**A runnable, local browser application** for intake, resume upload, three-gate job screening, employer-history lookup, and conservative document generation. Built to work across industries, not for any single applicant. Includes only fictional sample candidate data. **No private resumes or employer workbooks from the source project are distributed.**

## Start (macOS / Windows / Linux)

Install Python 3.11+ and LibreOffice (optional, needed for PDF export), then from this folder:

```bash
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765/** in your browser. Do **not** expose this server to the public internet: this MVP intentionally has no user accounts or authentication and is suitable only for a trusted, single-user computer. For a public service, implement encryption at rest, authentication, access controls, job queues, upload malware scanning, audit logs, and security assessment first.

## Questionnaire

The guided intake collects: name (required), optional contact, target roles, location/jurisdiction, work and relocation preferences, optional sponsorship needs, years of experience, systems and credentials, verified accomplishments, leadership scope, and a resume (required). The user must **not** supply passport/SSN/immigration receipt numbers or other highly sensitive documents. Questionnaire field reference: [`QUESTIONNAIRE.md`](QUESTIONNAIRE.md).

Supports DOCX, searchable PDF, and TXT (8 MB maximum). Image-only PDFs require conversion outside the tool. English-language matching is the current implementation; non-US jurisdictions have **no** immigration-regulation automation yet.

## Application logic

1. **Gate 1: Eligibility:** Checks actual JD text for ITAR/export control, citizenship/permanent residency restrictions, and explicit exclusion of needed sponsorship. For US postings, ITAR/U.S.-person text triggers a conservative hard stop, reflecting the prototype's default screening preference, not a universal claim about legal ITAR eligibility. An EEO nondiscrimination statement is not a restriction. H-1B *history* is the primary employer sponsorship signal. E-Verify is shown only if evidence and source are provided. A company with no H-1B records is **unverified**, not rejected. The tool makes **no live employer/government queries**.
2. **Gate 2: Professional fit:** Compares minimum requirements and responsibilities with the applicant's original resume plus their questionnaire-confirmed facts. Reports evidence candidates and unresolved qualifications; requires explicit human approval to proceed on flagged minimum requirements. It is lexical matching and can miss synonyms or overestimate other kinds of fit.
3. **Gate 3: Internal ATS alignment:** Scores the unchanged resume using the planned 40/25/20/10/5 weights. Displays an evidence-supported projected ceiling using user-verified questionnaire facts. If the **initial** score is **65 or below**, stops regardless of the projection. **The score is NOT an official ATS grade, pass percentage, or hiring probability.**
4. **Export:** If all gates clear, generates a ZIP with a reformatted **resume DOCX/PDF**, **cover letter DOCX/PDF**, assessment JSON/TXT and QA JSON. The employer names, positions, achievements, qualifications, and dates in the source resume are reproduced, not rewritten. User-confirmed, additional achievements appear separately, with no unsupported attribution to an employer. Does not submit applications.

### Evidence import

Optionally import a self-sourced employer-history `.csv` or `.xlsx` (up to 15 MB, 120,000 rows) from the target-job step, under “Optional: employer research evidence”. The UI tries exact normalized company-name matches. **It cannot verify company subsidiaries, DBA names, or parent relationships automatically.** It does not imply historical petition counts are current employees or position-specific sponsorship. E-Verify claims require their own source URL.

Accepted generic CSV columns: `Employer`, `Fiscal Year`, `new_approvals`, `continuing_approvals`. The app also reads certain USCIS-style Excel columns (`B` fiscal year, `C` employer, `I` new employment approvals, `K` continuing employment approvals). This import is a historical aid, **not live verification**.

## Persistence and privacy

- Raw uploaded files are held in memory for parsing, **not saved** by the application.
- Extracted resume text and questionnaire answers live in temporary Python memory by default (cleared on restart).
- Checking “Save this profile on this computer” persists text/answers in `local_data/store.sqlite3` in **plaintext** on the local machine. This folder is excluded from the published ZIP. Saved profiles can be reused at the start of the next application.
- Local endpoint `DELETE /api/profile/{profile_id}` removes a saved profile and the active session. To delete all local data, stop the server and delete `local_data/`.
- No browser `localStorage` and no connections to hosted AI or recruitment APIs.
- No account-based multi-user isolation: do not deploy publicly until hardened.

## What the MVP does not do yet

- Does **not** browse URLs, scrape job boards, verify live E-Verify, query USCIS automatically, submit applications, or run actual third-party ATS software.
- Does **not** generate AI-rewritten bullets from a provenance-linked claims ledger yet. The document builder preserves original lines and appends user-verified extra facts as a separate section; this is safer than silently altering titles, metrics, dates, and scope.
- Does not guarantee two-page resumes for arbitrarily long original files. Exports contain actual PDF page counts in `QA.json` when LibreOffice is installed; human visual review is required.
- The cover letter is a conservative factual template, not a deeply customized persuasive letter.
- The internal ATS scoring model is intentionally **not calibrated** to real ATS decisions; high scores may be misleading. Use as a consistency and gap-finding aid, not as a guarantee.
- PDF generation requires LibreOffice; DOCX always works.

## Next product milestones

1. Add a verified *claim ledger* with fact-level sources, employer attribution, confidence, and edit-approval workflow before LLM-powered bullet rewrites.
2. Build a properly authenticated, encrypted and consent-driven multi-user backend.
3. Integrate officially permitted employer H-1B/E-Verify lookup with source dates, entity-resolution and legal caveats.
4. Add reliable JD URL import (public endpoints only), semantic cross-evidence assessment, and more accessible questionnaire guidance.
5. Add recruiter review and output version control, visual PDF QA, job-tracker and application outcomes; benchmark elapsed screening time.

## Tests

```bash
pip install pytest httpx
pytest -q
```

Tests cover immediate hard stops, applicant work authorization, missing qualifications, progress gating, low ATS threshold, profile intake, local historical employer data import, and application ZIP generation using fictional sample data. The sample dataset isn't based on a real person. `examples/` has test inputs; no secret is included.

**Useful API endpoints:** `GET /api/health`, `GET /api/questionnaire`, `POST /api/intake`, `GET /api/profiles`, `POST /api/analyze`, `POST /api/generate`, `POST /api/employer-data/import`, `DELETE /api/profile/{profile_id}`. API responses return `gate1`, `gate2`, `gate3` and `may_generate`.
