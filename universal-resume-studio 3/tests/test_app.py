from pathlib import Path
import os,sys,json,io,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app import app

ROOT=Path(__file__).resolve().parents[1]
CV=(ROOT/'examples/sample_resume.txt').read_bytes()
JD=(ROOT/'examples/sample_job_description.txt').read_text()
Q={'full_name':'Alex Morgan','jurisdiction':'US','needs_sponsorship':'none','years_experience':7,'verified_facts':['Improved supplier on-time delivery from 82% to 96% through root-cause reviews.']}
client=TestClient(app)

def put_profile():
    response=client.post('/api/intake',data={'answers':json.dumps(Q),'save_locally':'false'},files={'file':('sample_resume.txt',CV,'text/plain')})
    assert response.status_code==200,response.text
    return response.json()['profile_id']

def test_health_and_form():
    assert client.get('/api/health').json()['status']=='ok'
    assert client.get('/api/questionnaire').json()['steps']
    assert '<html' in client.get('/').text

def test_end_to_end_gate_and_export():
    profile_id=put_profile()
    req={'profile_id':profile_id,'company':'Example Distribution Co.','job_title':'Senior Supply Planning Manager','job_description':JD}
    s=client.post('/api/analyze',json=req)
    assert s.status_code==200,s.text
    obj=s.json();assert obj['gate1']['status']=='PASS'
    req['approve_gaps']=True
    s2=client.post('/api/analyze',json=req)
    assert s2.status_code==200
    full=s2.json()
    # Even if baseline score too low, the tool MUST refuse ZIP.
    if full['may_generate']:
        result=client.post('/api/generate',json=req)
        assert result.status_code==200,result.text
        with zipfile.ZipFile(io.BytesIO(result.content)) as z:
            names=z.namelist()
            assert 'Resume.docx' in names and 'Cover_Letter.docx' in names and 'Assessment.json' in names
            from docx import Document
            text='\n'.join(p.text for p in Document(io.BytesIO(z.read('Resume.docx'))).paragraphs)
            assert '82% to 96%' in text
    assert client.delete('/api/profile/'+profile_id).json()['deleted']

def test_explicit_gate1_stop_no_output():
    p=put_profile()
    req={'profile_id':p,'company':'Example Defense Company','job_title':'Supply Manager','job_description':JD+'\nThis position is subject to ITAR requirements.','approve_gaps':True}
    r=client.post('/api/analyze',json=req)
    assert r.json()['gate1']['status']=='STOP'
    assert r.json()['gate3'] is None
    assert client.post('/api/generate',json=req).status_code==409

def test_import_csv_records():
    data=(ROOT/'examples/sample_employers.csv').read_bytes()
    x=client.post('/api/employer-data/import',files={'file':('employers.csv',data,'text/csv')})
    assert x.status_code==200,x.text
    assert x.json()['imported_records']==2
    p=put_profile()
    r=client.post('/api/analyze',json={'profile_id':p,'company':'Example Distribution Co.','job_title':'Senior Supply Planning Manager','job_description':JD})
    assert r.status_code==200
    assert r.json()['gate1']['h1b_history']['status']=='historical_approval_records_found'
