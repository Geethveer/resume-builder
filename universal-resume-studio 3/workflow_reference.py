#!/usr/bin/env python3
"""Portable three-gate screening reference for ANY candidate / JD.

Runs offline on JSON inputs.  Does not claim immigration eligibility, perform
live research, generate resume files, or query an actual ATS.  The FastAPI UI
in app.py is a runnable v0.1 demo; this v2 policy engine is not yet wired in.

Usage:
  python workflow_reference.py \
    --candidate examples/candidate.json \
    --job examples/job.json \
    --employer examples/employer_evidence.json \
    --policy config/pipeline_policy.json \
    --output out/assessment.json
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from core import (
    ITAR, US_PERSON, VISA_NO, jd_sections, evidence_for, experience_years_requirement,
    ats as legacy_ats, non_restriction_context, normalize_company
)

ROOT = Path(__file__).resolve().parent
DEFAULT_POLICY = ROOT / 'config' / 'pipeline_policy.json'


def read_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding='utf8'))
    if not isinstance(data, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return data


def filled(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def verified_claims(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Only explicit, individually approved candidate claims may enter matching.

    Never turn an 'inferred' or 'AI-suggested' fact into resume content.
    """
    out = []
    for item in candidate.get('verified_facts', []):
        if (isinstance(item, dict) and item.get('verified') is True
                and filled(item.get('statement'))
                and filled(item.get('source_type'))
                and filled(item.get('source_reference'))):
            out.append(item)
    return out


def canonical_needs_sponsorship(candidate: dict[str, Any]) -> bool:
    return candidate.get('sponsorship_need') in ('now', 'later', 'both', 'now_and_future')


def gate_1(candidate: dict[str, Any], job: dict[str, Any], employer: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Employer-history/explicit-JD screening; do not assume unstated restrictions."""
    rules = policy['gate1']
    jd = job['jd_text']
    jurisdiction = str(job.get('jurisdiction') or candidate.get('jurisdiction') or 'unknown').upper()
    checked = non_restriction_context(jd)
    stop: list[dict[str, str]] = []
    review: list[str] = []
    signals: dict[str, Any] = {
        'ITAR': 'NOT_STATED_IN_POSTING',
        'citizenship_or_residency': 'NOT_STATED_IN_POSTING',
        'sponsorship_policy': 'NOT_STATED_IN_POSTING',
        'h1b_history': 'NOT_ESTABLISHED',
        'e_verify': 'NOT_REPORTED'
    }
    if jurisdiction != 'US':
        review.append('Automated legal/employment checks are US-only. Manual local-law review required.')
    if jurisdiction == 'US':
        itar = ITAR.search(checked)
        person = US_PERSON.search(checked)
        clearance = re.search(r'(?:required|must (?:have|obtain)|active|eligible for).{0,45}(?:security|secret|top secret) clearance|(?:security|secret|top secret) clearance.{0,40}(?:required|must|active)', checked, re.I)
        visa = VISA_NO.search(checked)
        if itar:
            signals['ITAR'] = 'MENTIONED_IN_POSTING'
            if rules.get('hard_stop_on_explicit_itar_or_role_export_control', True):
                stop.append({'code': 'EXPORT_CONTROL_POLICY_STOP', 'evidence': itar.group(0),
                    'note': 'Conservative configured screen. ITAR is not universally citizenship-only; confirm role requirements if reconsidered.'})
        if person:
            signals['citizenship_or_residency'] = 'RESTRICTION_STATED_IN_POSTING'
            if rules.get('hard_stop_on_explicit_citizenship_or_permanent_residency_restriction', True):
                stop.append({'code': 'PERSON_RESTRICTION_POLICY_STOP', 'evidence': person.group(0),
                    'note': 'Configured applicant preference. Do not infer whether an individual meets this restriction.'})
        if clearance and rules.get('hard_stop_on_clearance_requirement', True):
            stop.append({'code': 'CLEARANCE_POLICY_STOP', 'evidence': clearance.group(0), 'note': 'Role clearance requirement; confirm actual eligibility separately.'})
        if visa:
            signals['sponsorship_policy'] = 'EXPLICIT_NO_SPONSORSHIP'
            if canonical_needs_sponsorship(candidate) and rules.get('hard_stop_on_explicit_no_sponsorship_if_candidate_needs_it', True):
                stop.append({'code': 'NO_REQUIRED_SPONSORSHIP', 'evidence': visa.group(0),
                    'note': 'Candidate indicated sponsorship is required; posting explicitly excludes it.'})
        elif re.search(r'(?:we (?:offer|provide)|(?:visa|immigration) sponsorship (?:is )?(?:offered|available)|will sponsor)', checked,re.I):
            signals['sponsorship_policy'] = 'EXPLICIT_POSSIBLE_SPONSORSHIP'
    # Evidence must correspond to the target employing legal entity, not a recruiter or parent.
    provided_legal = employer.get('legal_entity_name')
    job_legal = job.get('legal_employer_name') or job.get('company_name')
    if provided_legal and normalize_company(provided_legal) != normalize_company(job_legal):
        review.append('Employer evidence legal name differs from job employer; verify entity/DBA before using history.')
    else:
        h1b = employer.get('h1b_history') or {}
        approvals = h1b.get('approved_petitions', 0)
        has_citable_history_source = (filled(h1b.get('source_url')) or filled(h1b.get('source_dataset_sha256')))
        if (isinstance(approvals, int) and approvals > 0 and filled(h1b.get('fiscal_year'))
                and filled(h1b.get('source_description')) and has_citable_history_source
                and filled(h1b.get('checked_at'))):
            signals['h1b_history'] = 'HISTORICAL_APPROVAL_EVIDENCE'
            signals['h1b_details'] = {k: h1b.get(k) for k in ('fiscal_year', 'approved_petitions', 'source_description', 'source_url', 'source_dataset_sha256', 'checked_at')}
    # Absence from a history dataset does not mean "does not sponsor".
    if (canonical_needs_sponsorship(candidate) and jurisdiction == 'US'
            and signals['h1b_history'] != 'HISTORICAL_APPROVAL_EVIDENCE'
            and signals['sponsorship_policy'] != 'EXPLICIT_POSSIBLE_SPONSORSHIP'):
        review.append('H-1B historical sponsorship evidence not established for the hiring legal entity. Research further; do not assume non-sponsorship.')
    # E-Verify is independent from sponsorship and only shown with dated source.
    ev = employer.get('e_verify') or {}
    if (ev.get('status') == 'ENROLLED' and filled(ev.get('source_url')) and filled(ev.get('checked_at'))):
        signals['e_verify'] = 'SUPPORTED_BY_DATED_SOURCE'
        signals['e_verify_details'] = {k: ev.get(k) for k in ('source_url', 'checked_at', 'legal_entity_name')}
    elif ev.get('status') == 'ENROLLED':
        review.append('E-Verify enrollment asserted without a dated source; not reported as confirmed.')
    if not filled(job.get('jd_text')) or len(jd) < 120:
        review.append('Job description is incomplete; request full JD before fit/ATS scoring.')
    status = 'STOP' if stop else ('REVIEW' if review else 'PASS')
    return {'status': status, 'blockers': stop, 'review_items': review, 'signals': signals,
            'jurisdiction': jurisdiction, 'reviewed_posting_id':job.get('job_id'),
            'scope_note': 'Employer history is a signal, not sponsorship for this role or evidence of current sponsored headcount.'}


def _degree_proven(profile_text: str) -> bool:
    return bool(re.search(r'\b(?:bachelor(?:\'s)?|b\.?tech\.?|b\.?s\.?\b|b\.?e\.?\b|b\.?a\.?\b|undergraduate degree|master(?:\'s)?|m\.?s\.?\b|m\.?b\.?a\.?\b|ph\.?d\.?\b)\b', profile_text, re.I))


def _named_credentials_missing(line: str, profile_text: str) -> list[str]:
    known = re.findall(r'\b(?:CPIM|CSCP|PMP|CPA|CFA|CISSP|SHRM-CP|RN|LPN|PE|CCNA|AWS-SAA|CNA|CDL)\b', line, re.I)
    return [x.upper() for x in known if not re.search(r'\b' + re.escape(x) + r'\b', profile_text, re.I)]


def gate_2(candidate: dict[str, Any], job: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Human-review-friendly matching that separates visible resume facts from approved additions."""
    secs = jd_sections(job['jd_text'])
    resume_text = candidate['resume_text']
    extra = verified_claims(candidate)
    claim_text = '\n'.join(x['statement'] for x in extra)
    profile_text = resume_text + '\n' + claim_text
    rows: list[dict[str,Any]] = []
    unresolved: list[dict[str,Any]] = []
    for section in ('required', 'responsibilities', 'preferred'):
        for req in secs[section]:
            in_resume = evidence_for(req, resume_text)
            in_profile = evidence_for(req, profile_text)
            reasons = []
            min_years = experience_years_requirement(req)
            applicant_years = candidate.get('years_experience')
            if min_years is not None:
                if not isinstance(applicant_years, (int, float)):
                    reasons.append(f'{min_years}+ years required, verified years missing')
                elif applicant_years < min_years:
                    reasons.append(f'{min_years}+ years required, declared verified years: {applicant_years}')
            if re.search(r'\b(?:bachelor(?:\'s)?|undergraduate degree|b\.?s\.? degree)\b', req, re.I) and not _degree_proven(profile_text):
                reasons.append('Required degree is not confirmed')
            absent = _named_credentials_missing(req, profile_text)
            if absent:
                reasons.append('Named credential not verified: ' + ', '.join(absent))
            # Degree requirements are verified structurally: a genuine BS/BTech/
            # BA/MS credential is not missed because 'bachelor' != 'BS'.
            # Domain-specific degrees still require the required field to appear.
            degree_rule = bool(re.search(r'\b(?:bachelor(?:\'s)?|undergraduate degree|b\.?s\.? degree)\b', req, re.I))
            accepted_domains = [x for x in ('supply chain', 'business', 'engineering') if x in req.lower()]
            degree_evidence = bool(degree_rule and _degree_proven(resume_text)
                                 and (not accepted_domains or any(x in resume_text.lower() for x in accepted_domains)))
            # Don't accept unrelated degree fields as exact minimum-qualification matches.
            fields = ('computer science', 'nursing', 'accounting', 'finance', 'electrical engineering',
                      'mechanical engineering', 'civil engineering', 'engineering', 'supply chain',
                      'business', 'statistics', 'data science', 'human resources', 'marketing')
            named_fields = [f for f in fields if f in req.lower()]
            if degree_rule and named_fields and not any(f in profile_text.lower() for f in named_fields):
                reasons.append('Required degree specialization has no clear supporting evidence')
                degree_evidence = False
            if reasons:
                state = 'GAP_OR_UNVERIFIED'
            elif degree_evidence:
                state = 'EVIDENCE_CANDIDATE_IN_RESUME'
            elif in_resume['coverage'] >= .45:
                state = 'EVIDENCE_CANDIDATE_IN_RESUME'
            elif in_profile['coverage'] >= .45 and in_resume['coverage'] < .45:
                state = 'VERIFIED_BUT_UNDERREPRESENTED'
            else:
                state = 'NEEDS_HUMAN_REVIEW'
            item = {'category': section, 'requirement':req, 'state':state,
                    'resume_coverage_heuristic':in_resume['coverage'],
                    'verified_profile_coverage_heuristic':in_profile['coverage'],
                    'evidence_candidates':in_profile['evidence'],
                    'reasons':reasons,
                    'note':'Lexical similarity is not verification of competency. Check relevance manually.'}
            rows.append(item)
            if section == 'required' and state in ('GAP_OR_UNVERIFIED','NEEDS_HUMAN_REVIEW'):
                unresolved.append(item)
    if not secs['required']:
        unresolved.append({'requirement':'No minimum qualifications parsed from full JD.', 'state':'UNASSESSED',
                           'reasons':['Provide complete posting or manually inspect qualification section.']})
    state = 'REVIEW' if unresolved else 'PASS'
    return {'status': state, 'required_items_needing_decision': unresolved, 'items': rows,
            'underrepresented_verified_facts_count': sum(x['state']=='VERIFIED_BUT_UNDERREPRESENTED' for x in rows),
            'approval_required':state=='REVIEW'}


def gate_3(candidate: dict[str, Any], job: dict[str, Any], policy: dict[str,Any]) -> dict[str,Any]:
    """Current immutable-resume score and candidate-fact-only score projection."""
    unmodified = candidate['resume_text']
    approved = [x['statement'] for x in verified_claims(candidate)]
    raw = legacy_ats(job['jd_text'], unmodified, approved)
    score = raw['baseline']['score']
    minimum = policy['gate3']['min_allowed_initial_score_exclusive']
    weights = policy['gate3']['weights']
    parsed = jd_sections(job['jd_text'])
    return {
        'status':'STOP' if score <= minimum else 'PASS',
        'baseline_score':score,
        'estimated_best_supported_score':raw['projected_max_from_verified_facts']['score'],
        'baseline_breakdown':raw['baseline']['breakdown'],
        'projected_breakdown':raw['projected_max_from_verified_facts']['breakdown'],
        'weights':weights,
        'threshold':minimum,
        'missing_keyword_candidates':raw['baseline']['missing_keywords'],
        'unassessed_sections':[k for k in ('required','responsibilities') if not parsed[k]],
        'parse_safety_warning':'Text-length-based estimation only; run actual extraction from rendered DOCX/PDF before release.',
        'score_disclaimer':'Internal lexical heuristic. Not a measured ATS score, employer decision, hiring probability, or guaranteed maximum.'
    }


def run(candidate: dict[str, Any], job: dict[str, Any], employer: dict[str,Any], policy: dict[str, Any] | None = None) -> dict[str,Any]:
    if policy is None:
        policy = read_json(DEFAULT_POLICY)
    for key in ('candidate_id','full_name','resume_text'):
        if not filled(candidate.get(key)):
            raise ValueError(f'Candidate requires {key}')
    for key in ('job_id','company_name','role_title','jd_text'):
        if not filled(job.get(key)):
            raise ValueError(f'Job requires {key}')
    if len(job['jd_text']) < 100:
        raise ValueError('Paste the complete job description; too little text to screen.')
    sha = hashlib.sha256(candidate['resume_text'].encode('utf8')).hexdigest()
    outcome: dict[str,Any] = {
        'application_key': f"{candidate['candidate_id']}::{job['job_id']}",
        'candidate_id':candidate['candidate_id'],
        'employer':job['company_name'],
        'job_id':job['job_id'],
        'job_title':job['role_title'],
        'source_resume_sha256':sha,
        'policy_version':policy['policy_version'],
        'checked_date':date.today().isoformat(),
        'gate1':None,'gate2':None,'gate3':None,
        'may_generate':False,
        'next_action':'NOT_EVALUATED',
        'protected_claims': 'All changes require an evidence link and candidate approval; no invented accomplishments.'
    }
    a = gate_1(candidate,job,employer,policy)
    outcome['gate1']=a
    if a['status'] == 'STOP':
        outcome['next_action']='STOP_AND_REPORT_GATE1_RESTRICTION'
        return outcome
    if a['status'] == 'REVIEW' and not job.get('approve_gate1_review', False):
        outcome['next_action']='REQUEST_GATE1_REVIEW_APPROVAL'
        return outcome
    b = gate_2(candidate,job,policy)
    outcome['gate2']=b
    if b['status']=='REVIEW' and not job.get('approve_gate2_gaps',False):
        outcome['next_action']='REQUEST_QUALIFICATION_REVIEW_APPROVAL'
        return outcome
    c = gate_3(candidate,job,policy)
    outcome['gate3']=c
    if c['status']=='STOP':
        outcome['next_action']='STOP_BECAUSE_BASELINE_ALIGNMENT_65_OR_BELOW'
        return outcome
    outcome['may_generate']=True
    outcome['next_action']='GENERATE_FACT_CHECKED_DOCUMENTS_AND_RUN_QA'
    return outcome


def main():
    p=argparse.ArgumentParser(description='Generic portable job-screening reference engine (not an ATS provider)')
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--job',type=Path,required=True)
    p.add_argument('--employer',type=Path)
    p.add_argument('--policy',type=Path,default=DEFAULT_POLICY)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    assessment=run(read_json(a.candidate),read_json(a.job),read_json(a.employer) if a.employer else {},read_json(a.policy))
    raw=json.dumps(assessment,indent=2,ensure_ascii=False)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(raw+'\n',encoding='utf8')
        print(f"Gate 1: {assessment['gate1']['status']}; Gate 2: {assessment['gate2']['status'] if assessment['gate2'] else 'NOT_RUN'}; Gate 3: {assessment['gate3']['status'] if assessment['gate3'] else 'NOT_RUN'}; Next: {assessment['next_action']}")
    else:print(raw)


if __name__=='__main__':main()
