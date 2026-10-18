# Universal candidate intake questionnaire (Version 0.1)

Designed for minimum necessary disclosure and repeat application use. Entries marked **required** are the only mandatory candidate intake fields. Request evidence before adding a claim to an output resume. Never ask for government ID numbers, SSNs, passport scans, visa receipt numbers, medical information, or other unnecessary sensitive data.

## Section 1 · Core identity and target roles

| Question | Required? | Example or response type | Why it is needed |
|---|---|---|---|
| Full name to appear on documents | **Yes** | Free text | Application documents |
| Upload existing resume | **Yes** | DOCX, searchable PDF, TXT | Source-of-truth resume text |
| Email and phone | No | Contact fields | Document header |
| Current location | No | City, region, country | Header and job compatibility |
| Preferred roles | No | Job titles / levels | Personalized opportunity relevance |

## Section 2 · Preferences and eligibility (confidential, optional)

| Question | Type | Purpose |
|---|---|---|
| What country's job market are you targeting? | US / Canada / UK / EU / Other | Apply relevant screening logic; US-only automation in MVP |
| Do you need employer immigration sponsorship now or later? | No / Now / Later / Both / Prefer not to say | Decide whether explicit *no sponsorship* language is a blocker |
| Are you open to relocating? | Yes / Depends / No | Geographic fit |
| Preferred work arrangement | Onsite / Hybrid / Remote / Any | Opportunity preference |
| Employment constraints? | Optional free text | Preserve user choices and avoid unsuitable roles |

**Eligibility principle:** ITAR language or explicit citizenship/permanent-residence restriction in a US JD triggers a conservative screening stop by default. This is a user-configurable preference for future versions, not a universal legal assertion about ITAR. E-Verify enrollment and H-1B sponsorship are separate questions.

## Section 3 · Verified experience and qualification expansion

| Question | Format | Verification expectation |
|---|---|---|
| Years of relevant experience | Number, optional | Must correspond to work history; no unexplained rounding |
| Additional verified accomplishments | One statement per line | Candidate confirms factual accuracy, employer/time attribution later |
| Systems and software | Free text | Only use if personally operated or implemented, describe level later |
| Certifications and licenses | Free text | Verify exact name, issuer and status before attributing |
| Team, budget, or supplier management scope | Free text | Do not infer direct reports or manager-of-managers from project collaboration |

Recommended **follow-up questions** when the supplied JD requires finer evidence (not yet automated in the MVP):

1. Which employer and dates correspond to each newly added verified accomplishment?
2. What did you personally own versus support or coordinate?
3. Which quantities, budgets, outcomes, and timeframes are documented?
4. Are there exact software modules, tools, or transactions you operated firsthand?
5. Were your direct reports individual contributors or other managers?
6. Did you manage a budget or influence spend without signatory authority?
7. Which outcomes were individual contributions versus team-wide results?
8. Should a private detail stay outside all application documents?

## Section 4 · Job-specific intake

| Question | Required? | Purpose |
|---|---|---|
| Hiring company name | **Yes** | Employer screening and document metadata |
| Exact role title | **Yes** | JD-specific analysis |
| Complete job description | **Yes** | Gate 1 restrictions, Gate 2 evidence match, Gate 3 heuristic |
| Official job URL | No, planned | Source verification, if available |
| H-1B filing source or dataset | No | Historical signal, not sponsorship guarantee |
| Official E-Verify record | No | Independent hiring eligibility system |

## Section 5 · Explicit approval and controlled output

- A documented hard-stop restriction **stops before** professional fit or ATS assessment.
- A material qualification gap **pauses** for the job seeker to review and approve continuing.
- An initial score of **65 or less** stops optimization for that job, regardless of projected improvements.
- Only candidate-confirmed facts may be added; core job history should remain unchanged.
- Optional “save locally” is off until user affirmatively selects it.
- Any publicly hosted version requires a separate consent notice, security controls and retention policy.
