"""Pure, reviewable matching logic for a universal, evidence-first resume tool.

No model calls, no remote APIs, no assumptions about a specific applicant.
All scoring is an internal alignment heuristic, never a predicted ATS acceptance.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re
from collections import Counter
from typing import Any

STOP = set('''a an and are as at be been being by can could do does for from has have having in into is it its of on or our should such than that the their these this those through to using was were will with within you your we work experience requirements qualification qualifications ability skills strong proven required preferred role position including demonstrated demonstrate knowledge manage managing management support supporting ability excellent experience year years professional related across which more'''.split())
STOP |= {'candidate','team','teams','position','operations','process','processes','business','ensure','leading','lead','develop','developing','using','provide','providing','support','supporting','understanding','effective'}

HEADER_REQUIRED = re.compile(r'^(minimum qualifications?|basic qualifications?|requirements?|required qualifications?|must[- ]have|what you (?:need|bring))\s*:?$',re.I)
HEADER_PREF = re.compile(r'^(preferred qualifications?|nice[- ]to[- ]have|desirable qualifications?|bonus qualifications?)\s*:?$',re.I)
HEADER_RESP = re.compile(r'^(?:[\w /&,-]{0,85} )?(?:responsibilities|key responsibilities|duties|what you.ll do|what you will do|the role|job responsibilities)\s*:?$',re.I)
HEADER_OTHER = re.compile(r'^(?:about (?:the role|us|the company)|benefits|equal employment opportunity|compensation|salary|why join us|legal|privacy)\s*:?$',re.I)

# Deliberate conservative US screening: hard stop on explicit role restrictions,
# never based on company industry, and never treat E-Verify as H-1B sponsorship.
ITAR = re.compile(r'\bITAR\b|international traffic in arms regulations|export[- ]controlled (?:technical )?data',re.I)
US_PERSON = re.compile(r'(?:must|required|only|need|necessar\w*|restricted to|limited to|eligible).{0,65}\b(?:U\.?S\.? persons?|U\.?S\.? citizens?|American citizens?|citizenship|green card holders?|permanent residents?|security clearance)\b|\b(?:U\.?S\.? citizens?|green card holders?|permanent residents?)\b.{0,55}(?:only|required|must)', re.I)
VISA_NO = re.compile(r'(?:no|not (?:offer|available|provided|providing|eligible|considered|supported|sponsoring)|will not|cannot|unable to)\s+(?:.{0,24}\s+)?(?:visa|immigration|employment)\s+sponsorship|sponsorship (?:is )?(?:not available|unavailable|not offered)|must (?:now and in the future|not) (?:require|need) (?:visa )?sponsorship',re.I)

def normal(s: str) -> str:
    s=s.lower().replace('–','-').replace('—','-').replace('’',"'")
    return re.sub(r'\s+',' ',s).strip()

def stem(word:str)->str:
    aliases={'suppliers':'supplier','supplier':'supplier','replenishment':'replenish','replenishing':'replenish',
        'purchasing':'procurement','procurement':'procurement','purchased':'procurement','purchase':'procurement',
        'forecasting':'forecast','forecasts':'forecast','forecast':'forecast','planning':'plan',
        'planned':'plan','plans':'plan','plan':'plan','shipments':'shipment','shipment':'shipment',
        'managing':'manage','managed':'manage','management':'manage','manager':'manage',
        'improvement':'improve','improving':'improve','improved':'improve',
        'analyzing':'analysis','analytics':'analysis','analyze':'analysis','analytical':'analysis',
        'bachelor':'bachelor','bachelors':'bachelor','bs':'bachelor','bsc':'bachelor','btech':'bachelor',
        'stakeholders':'stakeholder','stakeholder':'stakeholder','teams':'team','team':'team',
        'operations':'operations','operation':'operations'}
    if word in aliases:return aliases[word]
    if word.endswith('ies') and len(word)>6: return word[:-3]+'y'
    if word.endswith('s') and not word.endswith(('ss','us')) and len(word)>4:return word[:-1]
    return word

def terms(text: str) -> set[str]:
    # Deliberately avoid trailing punctuation in tokens (e.g. "planning.").
    return {stem(w) for w in re.findall(r"[a-z][a-z0-9+#/]*", normal(text)) if w not in STOP and len(w)>2}

def jd_sections(jd: str) -> dict[str,list[str]]:
    sec={'required':[], 'preferred':[], 'responsibilities':[]}
    state='preamble'
    for row in jd.splitlines():
        s=re.sub(r'^\s*(?:[-*•‣]\s*|\d+[.)]\s*)','',row).strip()
        if not s:continue
        if HEADER_REQUIRED.fullmatch(s):state='required';continue
        if HEADER_PREF.fullmatch(s):state='preferred';continue
        if HEADER_RESP.fullmatch(s):state='responsibilities';continue
        if HEADER_OTHER.fullmatch(s):state='ignore';continue
        if state in ('ignore','preamble'): continue
        if len(s)<18:continue
        if len(s)>420:
            # Avoid pretending that an entire pasted block is an individual requirement.
            s=s[:420]
        sec[state].append(s)
    return sec

def non_restriction_context(jd:str) -> str:
    # Exclude standard EEO language: "regardless of citizenship" isn't a requirement.
    return '\n'.join(x for x in jd.splitlines() if not re.search(r'non.?discriminat|equal (?:employment|opportunity)|without regard to|regardless of|protected veteran|all qualified applicants',x,re.I))

def gate1(jd: str, jurisdiction: str, candidate:dict, employer_evidence:dict|None=None)->dict:
    employer_evidence=employer_evidence or {}
    source=non_restriction_context(jd)
    blockers=[]
    if jurisdiction.upper()=='US':
        if ITAR.search(source):blockers.append('ITAR or export-controlled technical-data language appears in the posting. Conservative hard stop; verify actual role requirements.')
        if US_PERSON.search(source):blockers.append('Posting explicitly requires citizenship, permanent residency, U.S.-person status, or clearance. Conservative hard stop under configured policy.')
        if VISA_NO.search(source) and candidate.get('needs_sponsorship') in ('now','future','now_and_future'):
            blockers.append('Posting explicitly rules out sponsorship needed by this applicant.')
    h1b=employer_evidence.get('h1b')
    e_verify=employer_evidence.get('e_verify')
    public={ 'status':'STOP' if blockers else 'PASS', 'blockers':blockers,
            'h1b_history':h1b or None,
            'e_verify':e_verify if isinstance(e_verify,dict) and e_verify.get('verified') else None,
            'jurisdiction':jurisdiction }
    return public

def evidence_for(line:str, text:str, max_items:int=2)->dict:
    source_lines=[s.strip(' •\t-') for s in text.splitlines() if len(s.strip())>20]
    wanted=terms(line)
    if not wanted:return {'coverage':0,'evidence':[]}
    scores=[]
    overall=set()
    for original in source_lines:
        tokens=terms(original);overall |= tokens
        overlap=len(wanted & tokens)/len(wanted)
        if overlap:scores.append((overlap,original))
    scores.sort(key=lambda x:-x[0])
    candidates=[{'text':s,'similarity':round(v,2)} for v,s in scores[:max_items] if v>=.14]
    best=scores[0][0] if scores else 0
    aggregate=len(wanted & overall)/len(wanted)
    # Combining separate verified bullets is legitimate for composite requirements,
    # but score stays below direct, concentrated line-level evidence.
    score=min(1.0, .73*aggregate + .27*best)
    return {'coverage':round(score,2),'evidence':candidates}

def experience_years_requirement(line:str)->int|None:
    m=re.search(r'\b(\d{1,2})\s*\+?\s*(?:years|yrs)\b',line,re.I)
    return int(m.group(1)) if m else None

def gate2(jd:str, resume_text:str, questionnaire:dict)->dict:
    sec=jd_sections(jd)
    highlights='\n'.join([str(x).strip() for x in questionnaire.get('verified_facts',[]) if str(x).strip()])
    profile=resume_text+'\n'+highlights
    rows=[];gaps=[]
    for category in ('required','responsibilities','preferred'):
        for line in sec[category]:
            match=evidence_for(line,profile)
            req_years=experience_years_requirement(line)
            known_years=questionnaire.get('years_experience')
            shortfall=(req_years is not None and isinstance(known_years,(int,float)) and req_years>known_years)
            years_unknown=(req_years is not None and known_years is None)
            degree_required=bool(re.search(r'\b(?:bachelor(?:.s)?|undergraduate degree|b\.?s\.? degree)\b',line,re.I))
            degree_verified=bool(re.search(r'\b(?:bachelor(?:.s)?|b\.?s\.?|b\.?tech\.?|b\.?eng\.?|b\.?a\.?|master(?:.s)?|m\.?s\.?)\b',profile,re.I))
            formal_cert=re.findall(r'\b(?:CPIM|CSCP|PMP|CPA|SHRM-CP|CFA)\b',line,re.I)
            cert_missing=[c for c in formal_cert if c.lower() not in profile.lower()]
            hard_gap=shortfall or years_unknown or (degree_required and not degree_verified) or bool(cert_missing)
            covered=match['coverage']>=.38 and not hard_gap
            reason=('Fewer declared years than posting requires' if shortfall else
                    'Years of experience not supplied; cannot verify minimum' if years_unknown else
                    'Required degree not verified' if degree_required and not degree_verified else
                    'Required certification not verified: '+', '.join(cert_missing) if cert_missing else
                    'No strong lexical evidence; requires human review' if not covered else
                    'Candidate evidence; validate relevance')
            row={'category':category, 'text':line, 'status':'candidate_match' if covered else 'needs_review', 'reason':reason, **match}
            rows.append(row)
            if category=='required' and not covered: gaps.append(row)
    return {'status':'REVIEW' if gaps else 'PASS', 'required_gaps':gaps, 'items':rows,
            'caution':'Lexical matching only: even a candidate match may not meet an employer requirement. Confirm all claims.'}

def ats(jd:str, resume_text:str, verified_facts:list[str]|None=None)->dict:
    secs=jd_sections(jd)
    def measure(text:str)->dict:
        req=[evidence_for(r,text)['coverage'] for r in secs['required']]
        resp=[evidence_for(r,text)['coverage'] for r in secs['responsibilities']]
        # Sparse JD categories cannot score at full value without requirements.
        # Set 0 in missing categories, note coverage limitations.
        req_score=round(40*sum(x>=.38 for x in req)/len(req),1) if req else 0.
        resp_score=round(25*sum(x>=.38 for x in resp)/len(resp),1) if resp else 0.
        jd_keyword=Counter(x for line in secs['required']+secs['responsibilities'] for x in terms(line))
        top_keywords=[w for w,_ in jd_keyword.most_common(22)]
        tk=terms(text)
        vocab_score=round(20*sum(w in tk for w in top_keywords)/len(top_keywords),1) if top_keywords else 0.
        metric_count=len(re.findall(r'\b\d+(?:\.\d+)?\s*%|\$\s*[\d,.]+\s*[kmb]?|\b\d+\s*(?:locations|sites|employees|suppliers|projects|units)\b',text,re.I))
        evidence_score=round(10*min(metric_count/3,1),1)
        parse_score=5.0 if len(text.strip())>120 and not '\x00' in text else 0.0
        pts={'requirements':req_score,'responsibilities':resp_score,'terminology':vocab_score,'specific_evidence':evidence_score,'parse_safety_estimate':parse_score}
        return {'score':round(sum(pts.values()),1),'breakdown':pts,'missing_keywords':[w for w in top_keywords if w not in tk]}
    original=measure(resume_text)
    approved='\n'.join(str(x).strip() for x in (verified_facts or []) if str(x).strip())
    projected=measure(resume_text+'\n'+approved)
    projected['score']=max(original['score'],projected['score'])
    return {'baseline':original,'projected_max_from_verified_facts':projected,
            'threshold':65,'status':'STOP' if original['score']<=65 else 'PASS',
            'disclaimer':'Private heuristic, not a real ATS score or pass probability. Projected ceiling uses only supplied candidate-approved facts and does not assume missing qualifications.'}

def normalize_company(v:str)->str:
    s=re.sub(r'[^A-Z0-9 ]',' ',v.upper())
    s=re.sub(r'\b(INC|INCORPORATED|LLC|LTD|LIMITED|CORPORATION|CORP|COMPANY|CO)\b',' ',s)
    return ' '.join(s.split())

def application_assessment(jd:str,resume_text:str,questionnaire:dict, employer_evidence:dict, company:str, title:str, approve_gaps:bool=False):
    j=str(questionnaire.get('jurisdiction','US'))
    eligibility=gate1(jd,j,questionnaire,employer_evidence)
    res={'job':{'company':company,'title':title,'jurisdiction':j},'gate1':eligibility,'gate2':None,'gate3':None,'may_generate':False}
    if eligibility['status']=='STOP':return res
    fit=gate2(jd,resume_text,questionnaire);res['gate2']=fit
    if fit['status']=='REVIEW' and not approve_gaps:return res
    a=ats(jd,resume_text,questionnaire.get('verified_facts',[]));res['gate3']=a
    res['may_generate']=a['status']=='PASS'
    return res
