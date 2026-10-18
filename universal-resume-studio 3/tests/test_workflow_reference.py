"""V2 portable policy contract regression tests. Fictional test inputs only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workflow_reference import read_json, run, gate_1, gate_2, gate_3

ROOT=Path(__file__).resolve().parents[1]
C=read_json(ROOT/'examples/candidate.json')
J=read_json(ROOT/'examples/job.json')
E=read_json(ROOT/'examples/employer_evidence.json')
P=read_json(ROOT/'config/pipeline_policy.json')

def test_all_clear_generate():
    x=run(C,J,E,P)
    assert x['gate1']['status']=='PASS'
    assert x['gate2']['status']=='PASS'
    assert x['gate3']['status']=='PASS'
    assert x['may_generate']
    assert x['gate3']['baseline_score']>65
    assert x['gate3']['estimated_best_supported_score']>=x['gate3']['baseline_score']

def test_itar_hard_stop_before_fit_and_ats():
    j=deepcopy(J);j['jd_text']+='\nThis role requires access to ITAR restricted technical data.'
    x=run(C,j,E,P)
    assert x['gate1']['status']=='STOP'
    assert x['gate2'] is None and x['gate3'] is None and not x['may_generate']

def test_citizenship_hard_stop_not_eeo():
    j=deepcopy(J);j['jd_text']+='\nMust be a U.S. citizen to hold this role.'
    assert run(C,j,E,P)['gate1']['status']=='STOP'
    j['jd_text']=J['jd_text']+'\nEqual employment opportunity: without regard to citizenship or national origin.'
    assert run(C,j,E,P)['gate1']['status']=='PASS'

def test_explicit_visa_sponsorship_exclusion_only_if_needed():
    j=deepcopy(J);j['jd_text']+='\nNo visa sponsorship available for this position.'
    assert run(C,j,E,P)['gate1']['status']=='STOP'
    c=deepcopy(C);c['sponsorship_need']='none'
    assert run(c,j,E,P)['gate1']['status']=='PASS'

def test_e_verify_does_not_prove_sponsorship():
    e=deepcopy(E);e['e_verify']={'status':'ENROLLED','source_url':'https://example.invalid/everify','checked_at':'2026-10-17'}
    e['h1b_history']={}
    x=run(C,J,e,P)
    assert x['gate1']['status']=='REVIEW'
    assert x['gate1']['signals']['e_verify']=='SUPPORTED_BY_DATED_SOURCE'
    assert x['gate1']['signals']['h1b_history']=='NOT_ESTABLISHED'

def test_stale_unverified_e_verify_not_confirmed():
    e=deepcopy(E);e['e_verify']={'status':'ENROLLED'}
    assert gate_1(C,J,e,P)['signals']['e_verify']=='NOT_REPORTED'

def test_employer_entity_mismatch_not_auto_joined():
    e=deepcopy(E);e['legal_entity_name']='Unrelated Holding Company'
    a=gate_1(C,J,e,P)
    assert a['status']=='REVIEW'
    assert a['signals']['h1b_history']=='NOT_ESTABLISHED'

def test_gate2_year_gap_pauses_until_approved():
    j=deepcopy(J);j['jd_text']=J['jd_text'].replace('5+ years','10+ years')
    x=run(C,j,E,P)
    assert x['gate1']['status']=='PASS'
    assert x['gate2']['status']=='REVIEW' and x['gate3'] is None
    j['approve_gate2_gaps']=True
    assert run(C,j,E,P)['gate3'] is not None

def test_underrepresented_verified_fact_is_not_same_as_resume():
    v=gate_2(C,J,P)
    assert any(x['state']=='VERIFIED_BUT_UNDERREPRESENTED' for x in v['items'])
    c=deepcopy(C)
    c['verified_facts'][0]['verified']=False
    v2=gate_2(c,J,P)
    assert v2['status']=='REVIEW'

def test_no_low_score_generation_even_with_override():
    c=deepcopy(C)
    c['resume_text']='Archaeology specialist with museum artifacts, ceramic conservation and exhibition design. '*7
    c['verified_facts']=[]
    j=deepcopy(J);j['approve_gate2_gaps']=True
    x=run(c,j,E,P)
    assert x['gate3']['baseline_score']<=65
    assert x['gate3']['status']=='STOP' and not x['may_generate']

def test_unrelated_degree_field_cannot_be_claimed_verified():
    j=deepcopy(J)
    j['jd_text']=J['jd_text'].replace('Bachelor degree in business, engineering, or supply chain management.', 'Bachelor degree in nursing required for this position.')
    r=gate_2(C,j,P)
    assert r['status']=='REVIEW'
    assert any('degree specialization' in ';'.join(x['reasons']) for x in r['required_items_needing_decision'])

def test_unverified_or_model_generated_claims_are_excluded():
    c=deepcopy(C);c['verified_facts'].append({'statement':'100 years experience','source_type':'model_guess','verified':False})
    v=gate_2(c,J,P)
    assert v['status']=='PASS'

def test_schemas_load_without_errors():
    for p in (ROOT/'schemas').glob('*.json'):
        assert json.loads(p.read_text())['$schema'].startswith('https://json-schema.org/')
