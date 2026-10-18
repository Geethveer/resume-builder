from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core

JD=Path(__file__).parents[1].joinpath('examples/sample_job_description.txt').read_text()
CV=Path(__file__).parents[1].joinpath('examples/sample_resume.txt').read_text()
Q={'full_name':'Alex Morgan','years_experience':7,'jurisdiction':'US','needs_sponsorship':'future','verified_facts':['Managed 14 suppliers with verified scorecards and lead-time metrics.']}

def test_itar_hard_stop():
    result=core.gate1('This role requires ITAR access to technical data and supplier planning.', 'US',Q)
    assert result['status']=='STOP'

def test_us_person_hard_stop():
    assert core.gate1('Must be a US citizen for engineering operations','US',Q)['status']=='STOP'
    assert core.gate1('Open to applicants without regard to citizenship','US',Q)['status']=='PASS'

def test_visa_exclusion_when_sponsorship_needed():
    assert core.gate1('No visa sponsorship available for this supply planning role.', 'US',Q)['status']=='STOP'
    assert core.gate1('No visa sponsorship available for this supply planning role.', 'US',{'needs_sponsorship':'none'})['status']=='PASS'

def test_parsing_jd():
    sec=core.jd_sections(JD)
    assert len(sec['required'])==4
    assert len(sec['responsibilities'])==4
    assert len(sec['preferred'])==1

def test_fit_pause_before_score():
    x=core.application_assessment(JD,CV,Q,{},'Example Distribution Co.','Senior Manager')
    if x['gate2']['status']=='REVIEW':assert x['gate3'] is None

def test_no_auto_creation_on_low_ats():
    unrelated='Certified fine art restoration assistant with oil painting and sculpting background, specializing in conservation.'
    x=core.application_assessment(JD,unrelated,Q,{},'Example Distribution Co.','Senior Manager',True)
    assert x['gate3']['status']=='STOP'
    assert not x['may_generate']

def test_evidence_based_max():
    x=core.ats(JD,CV,Q['verified_facts'])
    assert x['projected_max_from_verified_facts']['score']>=x['baseline']['score']
    assert 0<=x['baseline']['score']<=100

def test_company_normalization():
    assert core.normalize_company('Sample Industries, Inc.')=='SAMPLE INDUSTRIES'
    assert core.normalize_company('Sample Industries LLC')=='SAMPLE INDUSTRIES'
