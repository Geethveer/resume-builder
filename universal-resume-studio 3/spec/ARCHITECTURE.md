# Universal Resume Studio | portable architecture, Version 2

This document is the **canonical product contract**. The runnable `app.py`/`core.py` UI remains a **local-only v0.1 prototype**, whereas `workflow_reference.py`, the JSON schemas, and `config/pipeline_policy.json` define the expanded, portable v2 screening protocol. The v2 reference engine is independently runnable; its full policy is **not yet wired into the v0.1 browser app**. This distinction is important when integrating with other applications.

## Architecture and lifecycle

```text
A. Intake ── Resume DOCX/PDF/TXT + Questionnaire + Consent
     │
     ├── Parse + Normalize + SHA-256 source hash
     ├── Extract original employer chronology, titles, dates, achievements
     └── Fact ledger: resume-derived vs candidate-confirmed vs third-party-verified
     │
B. Job intake ── Complete JD + company + legal employing entity + source URL + snapshot date
     │
     ├── Identify jurisdiction, required vs preferred qualifications, duties
     └── Retrieve cached employer intelligence (recheck stale/mismatched evidence)
     │
C. Gate 1 | Legal / employer eligibility
     ├── STOP: posting explicitly says ITAR/role-controlled access, citizenship, LPR-only,
     │         or clearance restriction under applicant's *configured hard-stop policy*
     ├── STOP: posting explicitly says sponsorship unavailable AND applicant needs it
     ├── REVIEW: missing necessary employing-entity / immigration-jurisdiction evidence
     └── PASS: no stop (H-1B history is a signal, not a promise; E-Verify separate)
     │
D. Gate 2 | Professional fit
     ├── Compare required & preferred vs resume + verified claim ledger
     ├── MATCH = direct evidence
     ├── UNDERREPRESENTED = supported by ledger, not clear in resume
     ├── REVIEW = unclear: ask focused question, pause for approval
     ├── GAP = applicant confirms missing qualification, pause
     └── PASS only if no meaningful unresolved minimum gap or user explicitly opts to proceed
     │
E. Gate 3 | Internal ATS alignment
     ├── Baseline: immutable uploaded resume (40/25/20/10/5)
     ├── Projected maximum: fact-grounded wording changes only, never guaranteed
     ├── STOP if baseline <= 65/100
     └── PASS if baseline >= 66/100
     │
F. Generation | user-allowed only
     ├── Suggest edits -> validate every changed claim against original + verified facts
     ├── Produce DOCX/PDF resume & cover letter
     ├── Check page count, extraction, headings, role order, layout
     ├── Record version, diffs, evidence audit and unproven gaps
     └── Return documents for human approval. Never auto-submit.
     │
G. Learning / reuse
     ├── Cache company history by exact legal employing entity + fiscal year + source
     ├── Recheck job-specific restrictions for every NEW JD
     ├── Reuse validated wording with traceable claim IDs per candidate
     └── Track application outcomes without claiming they prove ATS vendor scores.
```

## Outputs and decision states

Use machine states: `PASS`, `REVIEW`, `STOP`, `NOT_RUN`; never flatten uncertain evidence into a binary `YES/NO`.

| Workflow event | Status | Action |
|---|---|---|
| Gate 1 explicit controlled-access, citizenship, residency or clearance phrase | STOP | No Gate 2 or Gate 3; show exact JD snippet/source. This is an applicant preference policy and may over-exclude people legally eligible. |
| Gate 1 explicit sponsorship exclusion + applicant requires sponsorship | STOP | No further processing. |
| Gate 1 employer H-1B history present; JD has no restrictions | PASS | Historical signal; never infer present sponsored employee count or a role sponsorship promise. |
| Gate 1 H-1B history not found and sponsorship needed | REVIEW | No false rejection; ask applicant whether to continue investigation. |
| Gate 2 verified facts cover a criterion but resume omits it | UNDERREPRESENTED | Include as candidate for **post-gate** truthful resume enhancement. |
| Gate 2 required criterion genuinely missing or unknown | REVIEW | Ask user whether to continue; never fabricate. |
| Gate 3 baseline score 65.0 or below | STOP | No resume or cover letter created. |
| Gate 3 baseline 65.1–100 | PASS | Generate after needed Gate 2 approval; never promise success. |
| Posting cannot be fully retrieved | REVIEW | Ask for pasted JD; do not score a guessed description. |

### Screening legal nuance

The policy's default U.S. hard-stop for an *ITAR mention* is a **conservative preference**, not a universal legal test. ITAR can cover access by U.S. persons including lawful permanent residents and certain protected individuals. Some export-controlled roles can support employer authorization for other workers. A universal product must allow explicit candidate/organization policy configuration, distinguish an ITAR mention from an actual position's eligibility restriction, and never determine immigration status or legal eligibility from name, nationality, birthplace or appearance. Never ask for SSNs, passport numbers, I-94 identifiers, etc. Employment-authorization and sponsorship questions are optional and used only for screening when the applicant opts in.

### H-1B/E-Verify accuracy rules

- Identify exact employing entity and aliases before comparing with data. Recruiter or parent-company records alone do not prove the target legal employer's sponsorship.
- H-1B approvals / denials / DOL LCAs are **historical filing events**, not proof of current employees or this opening's sponsorship.
- USCIS approved petitions and DOL LCAs are **not interchangeable**.
- H-1B history is the primary *historical sponsorship signal* when requested. If unavailable, say "not established"; do not claim "does not sponsor".
- E-Verify participation is **not visa sponsorship**. Display positive participation only with dated, verifiable source; absence of a public match is inconclusive.
- Only report a position's positive/negative sponsorship policy if the JD or an authoritative employer communication explicitly says it.
- Role-specific ITAR/citizenship/green-card/security-clearance text must be checked in each new job description.

### Evidence / claim ledger schema principles

Every added line must have `fact_id`, `statement`, `source_type`, `source_reference`, `verified` and when available `employer_id`, `date_range` and `metrics`. Unknown employer attribution remains `null`; the system may list verified skills in a neutral Skills section, but **must not attach them to an invented job**. Keep original resume hash and change audit. Two separate statuses: *truth confirmed* and *shown in current resume*.

### ATS scoring contract

Weighted internal rubric: must-have requirements 40%, responsibilities 25%, terminology 20%, documented impact 10%, parsing safety 5%. Each requirement should retain matched evidence or explicit gap. The baseline score must use unmodified source text; the projected maximum can be estimated from *only approved claim-ledger facts*. The 5% parsing check is a rough textual estimate until the final DOCX/PDF are rendered and tested. Scores must be shown as `INTERNAL_ESTIMATE`, never labeled "actual ATS score," "100% guaranteed," or "chance of getting hired." Missing JD sections should be marked `UNASSESSED`, not filled in by inventing requirements. Revisit weights if actual outcomes show systematic errors.

### Candidate intake UX

Start with only name + resume + target JD. Offer contact and authorization screening as optional follow-up. Do not require 20 fields up front. Ask **one targeted question at a time** when a material JD requirement needs evidence. If the candidate wants the fuller questionnaire, collect: contact, work geography/preferences, employment timeline and employment type, education, skills, achievements and metrics, managed-team scope, tools/modules used firsthand, licenses/certifications and expiration, sponsorship preference, source documents, consent to local storage.

### Outputs / QA

- Optimized resume DOCX/PDF; tailored cover letter DOCX/PDF; `assessment.json`, `evidence_audit.json`, `qa.json`; optional compact application tracker record.
- Preserve employer names, dates, actual title, credential names, timelines, location metadata, verified quantities and systems. Reordering bullets must stay within an employer.
- Parse source + rendered PDF, visually inspect pages, detect header collisions and missing sections. Respect industry/seniority-appropriate length (usually 1–2 pages, not universally exactly 2).
- Explicit consent for profile persistence; per-user data boundaries; deletion and retention controls. Local v0.1 stores opted-in plaintext SQLite, so **never expose it publicly**.

### Implementation layers

- **Included:** `app.py` FastAPI single-user local UI/API, `core.py` original matching implementation, templates/static/questionnaire and tests.
- **Reference v2:** `workflow_reference.py` independently executable pure-Python gates driven by `config/pipeline_policy.json`; user-supplied JSON profile/JD/evidence examples; schema validation contracts.
- **Not included:** Live USCIS/E-Verify APIs, universal legal eligibility verification, an LLM factual-rewriting service, online multi-user account security, auto-submission, reliable job-link scraping. These require separate implementation and audit.
