# API contract and integration guide

## Local v0.1 UI (already runnable)

`GET /api/health` — deployment features; `GET /api/questionnaire` — intake steps;
`POST /api/intake` — multipart (`file`: DOCX/PDF/TXT, `answers`: JSON string, `save_locally`: bool);
`GET /api/profiles` — locally opted-in profiles; `POST /api/employer-data/import` — CSV/XLSX;
`POST /api/analyze` — applicant ID, company, title, JD, optional evidence and Gate-2 override;
`POST /api/generate` — validates the gates again, emits assessment and DOCX/PDF ZIP;
`DELETE /api/profile/{profile_id}` — deletes saved local profile.

The original `app.py` currently imports `core.application_assessment`, **not** `workflow_reference.run`; the reference module is the v2 implementation specification for a future API upgrade. Both are included for transparency. Do not claim the new v2 checks run from the browser interface until integrated and tested.

## Proposed v2 backend endpoints (design only)

```http
POST /v2/candidates/intake
POST /v2/verified-claims/add
POST /v2/jobs/analyze
POST /v2/gates/resolve-review
POST /v2/documents/generate
GET  /v2/applications/{id}
GET  /v2/applications/{id}/artifacts
DELETE /v2/candidates/{id}
```

Inputs validate against `schemas/candidate.schema.json`, `schemas/job.schema.json`, `schemas/employer_evidence.schema.json`. Analysis returns the shape in `schemas/assessment.schema.json`.

### Standalone v2 assessment CLI

```bash
python workflow_reference.py \
  --candidate examples/candidate.json \
  --job examples/job.json \
  --employer examples/employer_evidence.json \
  --policy config/pipeline_policy.json \
  --output out/assessment.json
```

**Data lineage:** Original resume is identified by a SHA-256 digest; JD is identified by posting ID/source. Every candidate-added statement has an ID, candidate confirmation and source reference. Generate a new application version for any subsequent changes.

**Employer-source integration:** Future adapters must fetch permitted official USCIS/DOL/E-Verify and company careers sources, store `legal_entity_name`, `source_url`, `checked_at`, `fiscal_year`, evidence type, and match confidence. Absence of evidence must never be converted to proof of absence.

**Local software security:** The existing prototype is a single-user local demonstration. The persisted SQLite store is not encrypted; do not deploy for multiple users. Limit network binding to `127.0.0.1`.
