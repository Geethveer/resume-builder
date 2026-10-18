"""Local-only, privacy-first universal resume screening MVP.
Run: uvicorn app:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
import csv, hashlib, io, json, mimetypes, os, re, shutil, sqlite3, subprocess, tempfile, uuid, zipfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import fitz
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from core import application_assessment, normalize_company, jd_sections, evidence_for

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'local_data'
DB=DATA/'store.sqlite3'
MAX_FILE=8*1024*1024
MAX_JD=50000
APP=FastAPI(title='Resume Studio',version='0.1.0',docs_url=None,redoc_url=None)
APP.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
# Local persistence only if the person explicitly opts in. Unpersisted sessions
# live in RAM until this single-user development server restarts.
SESSION: dict[str,dict[str,Any]]={}


def conn():
    DATA.mkdir(exist_ok=True)
    x=sqlite3.connect(DB)
    x.row_factory=sqlite3.Row
    x.execute('CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, json_text TEXT NOT NULL, saved_at TEXT NOT NULL)')
    x.execute('CREATE TABLE IF NOT EXISTS employers(company_key TEXT NOT NULL, employer TEXT NOT NULL, fiscal_year TEXT, new_approvals INTEGER, continuing_approvals INTEGER, source_note TEXT, PRIMARY KEY(company_key, employer, fiscal_year))')
    x.commit();return x


def profile(profile_id:str):
    if profile_id in SESSION:return SESSION[profile_id]
    with conn() as c:
        row=c.execute('SELECT json_text FROM profiles WHERE id=?',(profile_id,)).fetchone()
    if not row:raise HTTPException(404,'Profile not found. Import or complete the questionnaire first.')
    return json.loads(row['json_text'])


def resume_extract(name:str,data:bytes)->str:
    ext=Path(name.lower()).suffix
    if len(data)>MAX_FILE:raise HTTPException(413,'Maximum resume size is 8 MB.')
    if ext=='.docx':
        try:
            doc=Document(BytesIO(data))
            # Document text and table contents. Tables cannot be reliably parsed
            # by all ATS systems, but input reading should remain tolerant.
            ps=[]
            for p in doc.paragraphs:
                if not p.text.strip():continue
                v=p.text.strip()
                if ('list' in p.style.name.lower() or p._p.xpath('./w:pPr/w:numPr')) and not re.match(r'^[-•‣*]',v): v='• '+v
                ps.append(v)
            for t in doc.tables:
                for row in t.rows:ps.append(' | '.join(c.text for c in row.cells))
            text='\n'.join(ps)
        except Exception:raise HTTPException(422,'Cannot read this DOCX. Export a standard DOCX or text PDF.')
    elif ext=='.pdf':
        try:
            with fitz.open(stream=data,filetype='pdf') as pdf:
                if len(pdf)>20:raise HTTPException(422,'Upload a resume of 20 pages or fewer.')
                text='\n'.join(p.get_text('text',sort=True) for p in pdf)
        except HTTPException:raise
        except Exception:raise HTTPException(422,'Cannot parse this PDF.')
    elif ext=='.txt':
        text=data.decode('utf-8-sig',errors='replace')
    else:raise HTTPException(422,'Supported formats: DOCX, searchable PDF, TXT.')
    text=text.replace('\x00','').strip()
    if len(text)<100:raise HTTPException(422,'Little or no selectable resume text found. Upload a searchable PDF, DOCX, or TXT.')
    return text[:100000]


@APP.get('/')
def landing():return FileResponse(ROOT/'templates'/'index.html')

@APP.get('/api/health')
def health():return {'status':'ok','mode':'local','automatic_employer_verification':False,'server_persistence_opt_in':True}

@APP.get('/api/questionnaire')
def questionnaire():
    return {'steps':[
      {'title':'Contact & direction','fields':['full_name','email','phone','location','target_roles','jurisdiction','location_preferences','relocation','work_arrangement']},
      {'title':'Work authorization (optional)','fields':['needs_sponsorship','work_authorization_notes','employment_constraints']},
      {'title':'Verified professional experience','fields':['years_experience','verified_facts','systems','certifications','education_notes','leadership_scope']},
      {'title':'Preferences & privacy','fields':['preferred_resume_length','profile_persistence','consent_to_local_save']}
    ],'guidance':'Do not supply SSN, passport numbers, date of birth, immigration receipt numbers, or private references. Enter only what is necessary for screening.'}

@APP.post('/api/intake')
async def intake(file:UploadFile=File(...),answers:str=Form(...), save_locally:bool=Form(False)):
    data=await file.read(MAX_FILE+1)
    if len(data)>MAX_FILE:raise HTTPException(413,'Maximum file size is 8 MB.')
    try: q=json.loads(answers)
    except json.JSONDecodeError:raise HTTPException(422,'Answers must be valid JSON.')
    if not isinstance(q,dict):raise HTTPException(422,'Questionnaire must be an object.')
    name=str(q.get('full_name') or '').strip()
    if not name:raise HTTPException(422,'Full name is required.')
    if not isinstance(q.get('verified_facts',[]),list):raise HTTPException(422,'verified_facts must be a list')
    text=resume_extract(file.filename or '',data)
    pid=uuid.uuid4().hex
    record={'id':pid,'answers':q,'resume_text':text,'source_name':Path(file.filename or 'resume').name,
            'file_sha256':hashlib.sha256(data).hexdigest(), 'saved':bool(save_locally),
            'uploaded_at':datetime.now(timezone.utc).isoformat()}
    SESSION[pid]=record
    if save_locally:
        with conn() as c:c.execute('INSERT INTO profiles(id,json_text,saved_at) VALUES(?,?,?)',(pid,json.dumps(record),record['uploaded_at']))
    return {'profile_id':pid,'resume_characters':len(text),'resume_sha256':record['file_sha256'],
            'saved':bool(save_locally),'recognized_sections':len(re.findall(r'\b(experience|education|skills|projects|summary)\b',text,re.I)),
            'verified_fact_count':len(q.get('verified_facts',[]))}


@APP.get('/api/profiles')
def saved_profiles():
    with conn() as c:
        records=c.execute('SELECT id, json_text, saved_at FROM profiles ORDER BY saved_at DESC LIMIT 100').fetchall()
    result=[]
    for row in records:
        obj=json.loads(row['json_text'])
        result.append({'id':row['id'], 'name':obj.get('answers',{}).get('full_name','Unknown'),
                       'source_name':obj.get('source_name','resume'),'saved_at':row['saved_at']})
    return {'profiles':result}

@APP.get('/api/profile/{profile_id}/summary')
def profile_summary(profile_id:str):
    p=profile(profile_id)
    return {'id':p['id'],'full_name':p['answers'].get('full_name'),
            'resume_source':p['source_name'],'verified_facts':len(p['answers'].get('verified_facts',[])),
            'saved':p['saved']}

@APP.delete('/api/profile/{profile_id}')
def delete_profile(profile_id:str):
    SESSION.pop(profile_id,None)
    with conn() as c:c.execute('DELETE FROM profiles WHERE id=?',(profile_id,))
    return {'deleted':True,'id':profile_id}


def evidence(company:str, supplied:dict|None)->dict:
    ev=supplied or {}
    if not isinstance(ev,dict):raise HTTPException(422,'Employer evidence must be a JSON object.')
    # Exact company label match only; never substitute a nearby subsidiary or
    # recruiter. A parent-company record must be independently resolved.
    if not ev.get('h1b'):
        key=normalize_company(company)
        with conn() as c: rows=c.execute('SELECT * FROM employers WHERE company_key=? ORDER BY CAST(fiscal_year AS INTEGER) DESC LIMIT 5',(key,)).fetchall()
        if rows:
            positive=any((x['new_approvals'] or 0)>0 or (x['continuing_approvals'] or 0)>0 for x in rows)
            ev['h1b']={'status':'historical_approval_records_found' if positive else 'records_found_but_approvals_not_established','employer_matches':[{'name':x['employer'],'fiscal_year':x['fiscal_year'], 'new_approvals':x['new_approvals'],'continuing_approvals':x['continuing_approvals']} for x in rows],
                       'basis':'user-imported employer filing data; not proof of current role sponsorship or current employment'}
    if ev.get('h1b') and ev['h1b'].get('status') in ('verified','confirmed') and not ev['h1b'].get('source_url'):
        raise HTTPException(422,'Claims of verified H-1B sponsorship require source_url.')
    if ev.get('e_verify') and ev['e_verify'].get('verified') and not ev['e_verify'].get('source_url'):
        raise HTTPException(422,'Claims of E-Verify enrollment require source_url.')
    return ev

class AnalyzeRequest(BaseModel):
    profile_id:str
    company:str=Field(min_length=2,max_length=160)
    job_title:str=Field(min_length=2,max_length=180)
    job_description:str=Field(min_length=100,max_length=MAX_JD)
    employer_evidence:dict[str,Any]=Field(default_factory=dict)
    approve_gaps:bool=False

@APP.post('/api/analyze')
def analyze(body:AnalyzeRequest):
    p=profile(body.profile_id)
    ev=evidence(body.company,dict(body.employer_evidence))
    return application_assessment(body.job_description,p['resume_text'],p['answers'],ev,body.company,body.job_title,body.approve_gaps)


def sanitize_filename(s:str)->str:
    return re.sub(r'[^A-Za-z0-9 _.-]','',s).strip()[:65] or 'Application'


def add_heading(doc,title):
    p=doc.add_paragraph()
    p.style='Heading 2';p.paragraph_format.space_before=Pt(9);p.paragraph_format.space_after=Pt(3)
    p.add_run(title)


def base_style(doc:Document):
    sec=doc.sections[0]
    sec.top_margin=Inches(.65);sec.bottom_margin=Inches(.65);sec.left_margin=Inches(.72);sec.right_margin=Inches(.72)
    st=doc.styles['Normal'];st.font.name='Aptos';st.font.size=Pt(9.5);st.paragraph_format.space_after=Pt(3)
    for key in ('Heading 1','Heading 2'):
        doc.styles[key].font.name='Aptos Display';doc.styles[key].font.color.rgb=RGBColor(30,51,85)


def doc_files(profile_data:dict, req:AnalyzeRequest, screening:dict)->dict[str,bytes]:
    q=profile_data['answers']; resume_text=profile_data['resume_text']; facts=[str(x).strip() for x in q.get('verified_facts',[]) if str(x).strip()]
    candidate_name=str(q['full_name']);lines=[s.strip() for s in resume_text.splitlines() if s.strip()]
    doc=Document();base_style(doc)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    rr=p.add_run(candidate_name);rr.bold=True;rr.font.size=Pt(16);rr.font.color.rgb=RGBColor(30,51,85)
    contact=' | '.join(x for x in [str(q.get('location') or '').strip(),str(q.get('email') or '').strip(),str(q.get('phone') or '').strip()] if x)
    if contact:
        p=doc.add_paragraph(contact);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    # No automatic rewriting of experience: original source text retained
    # verbatim, including each original employer/date and metric.
    for ix,line in enumerate(lines):
        # Avoid repeated name/contact in the new header, but preserve the full
        # original employment, accomplishment and education records.
        if ix<6 and (line.lower()==candidate_name.strip().lower() or (q.get('email') and str(q['email']) in line) or (q.get('phone') and str(q['phone']) in line)):
            continue
        upper=line.upper().strip(':')
        if upper==line.strip(':') and upper in {'SUMMARY','PROFESSIONAL SUMMARY','EXPERIENCE','PROFESSIONAL EXPERIENCE','EDUCATION','SKILLS','TECHNICAL SKILLS','CERTIFICATIONS','PROJECTS','SYSTEMS','VOLUNTEER EXPERIENCE','PROFESSIONAL DEVELOPMENT'}:
            add_heading(doc,line.title());continue
        isbullet=bool(re.match(r'^[-•‣*]\s*',line))
        p=doc.add_paragraph(style='List Bullet' if isbullet else None)
        p.paragraph_format.keep_together=True
        p.add_run(re.sub(r'^[-•‣*]\s*','',line) if isbullet else line)
    # Only applicant-supplied self-verified facts, not inferred.
    novel_facts=[fact for fact in facts if fact.lower() not in resume_text.lower()]
    if novel_facts:
        add_heading(doc,'ADDITIONAL VERIFIED QUALIFICATIONS')
        for fact in novel_facts:
            p=doc.add_paragraph(style='List Bullet');p.add_run(fact)
    buf=BytesIO();doc.save(buf)

    letter=Document();base_style(letter)
    p=letter.add_paragraph();p.add_run(candidate_name).bold=True
    if contact:letter.add_paragraph(contact)
    letter.add_paragraph(datetime.now(timezone.utc).date().isoformat())
    letter.add_paragraph('Hiring Team\n'+req.company)
    letter.add_paragraph('Re: '+req.job_title)
    letter.add_paragraph('Dear Hiring Team,')
    letter.add_paragraph(f'I am applying for the {req.job_title} position at {req.company}. My background includes the responsibilities and qualifications documented in my attached resume. I am particularly interested in applying my experience to the priorities described in this opportunity.')
    # Prefer exact original-resume evidence; add extra confirmed facts only when
    # needed. This is an extractive cover letter, not generated experience.
    picked=[]
    required_and_responsibilities=jd_sections(req.job_description)
    for phrase in required_and_responsibilities['responsibilities']+required_and_responsibilities['required']:
        ev=evidence_for(phrase,resume_text)
        for obj in ev['evidence']:
            line=obj['text'].strip(' •‣-\t')
            if obj['similarity']>=.25 and line not in picked and len(line)>35 and len(line)<300:
                picked.append(line)
            if len(picked)>=2:break
        if len(picked)>=2:break
    for line in facts:
        if len(picked)>=2:break
        if line not in picked and len(line)>22:picked.append(line)
    if picked:
        letter.add_paragraph('Selected relevant experience includes:')
        for x in picked: letter.add_paragraph(x,style='List Bullet')
    letter.add_paragraph('I would welcome the opportunity to discuss the role and my qualifications in more detail. Thank you for your consideration.')
    letter.add_paragraph('Sincerely,\n'+candidate_name)
    b2=BytesIO();letter.save(b2)
    report={'screening':screening,'company':req.company,'role':req.job_title,
            'candidate_file_sha256':profile_data['file_sha256'],'source_name':profile_data['source_name'],
            'generated_at':datetime.now(timezone.utc).isoformat(),
            'audit':['Source resume lines reproduced unchanged','Additional claims come only from questionnaire verified_facts',
                     'No employer, degree, or work dates invented','H-1B evidence is historical and not a job-level sponsorship guarantee'],
            'warnings':['Document page length varies with applicant source resume. Review before applying.',
                        'ATS score is a heuristic, not an employer or vendor-provided score.',
                        'No live government employer verification is implemented.']}
    return {'Resume.docx':buf.getvalue(), 'Cover_Letter.docx':b2.getvalue(),
            'Assessment.json':json.dumps(report,indent=2,ensure_ascii=False).encode(),
            'Assessment.txt':('\n'.join([f'{req.company} - {req.job_title}',f"Gate 1: {screening['gate1']['status']}",
             f"Gate 2: {screening['gate2']['status']}",f"Gate 3: {screening['gate3']['status']}",
             f"Current match score: {screening['gate3']['baseline']['score']}/100",
             f"Evidence-supported projected maximum: {screening['gate3']['projected_max_from_verified_facts']['score']}/100",
             'Internal estimate only; not an actual ATS score.','',
             'Review every generated file and fact before submitting.'])).encode('utf-8')}


def convert_pdf(docx:bytes)->tuple[bytes|None,dict]:
    soffice=shutil.which('soffice')
    if not soffice:return None,{'status':'unavailable','reason':'LibreOffice not installed'}
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp);source=d/'Input.docx';source.write_bytes(docx)
        try:
            res=subprocess.run([soffice,'-env:UserInstallation=file://'+str(d/'lo'), '--headless','--convert-to','pdf','--outdir',tmp,str(source)],
                               capture_output=True,timeout=40,text=True)
            pdf=d/'Input.pdf'
            if res.returncode or not pdf.exists():return None,{'status':'failed','detail':res.stderr[:300]}
            data=pdf.read_bytes()
            with fitz.open(stream=data,filetype='pdf') as parsed:
                page_count=len(parsed);text=' '.join(p.get_text() for p in parsed)
            return data,{'status':'passed' if len(text)>100 else 'review','pages':page_count,'text_extractable':len(text)>100}
        except Exception as exc:return None,{'status':'failed','detail':str(exc)[:300]}

@APP.post('/api/generate')
def generate(req:AnalyzeRequest):
    if not req.approve_gaps:raise HTTPException(422,'You must explicitly approve Gate 2 gaps before generation.')
    p=profile(req.profile_id)
    screened=application_assessment(req.job_description,p['resume_text'],p['answers'],evidence(req.company,dict(req.employer_evidence)),req.company,req.job_title,True)
    if not screened['may_generate']:raise HTTPException(409,'Gates not cleared. No documents were generated.')
    contents=doc_files(p,req,screened)
    qa={}
    for name in ['Resume.docx','Cover_Letter.docx']:
        pdf,result=convert_pdf(contents[name]);qa[name]=result
        if pdf:contents[name.replace('.docx','.pdf')]=pdf
    contents['QA.json']=json.dumps(qa,indent=2).encode()
    # Return everything in memory, leaving no generated applicant documents on disk.
    buf=BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for filename,data in contents.items():z.writestr(filename,data)
    buf.seek(0)
    fn=sanitize_filename(req.company)+'_'+sanitize_filename(req.job_title)+'.zip'
    return StreamingResponse(buf,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{fn}"'})


def read_xlsx_employers(data:bytes):
    ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with zipfile.ZipFile(BytesIO(data)) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                for _,el in ET.iterparse(f,events=('end',)):
                    if el.tag==ns+'si':
                        strings.append(''.join(n.text or '' for n in el.iter(ns+'t')));el.clear()
        with z.open('xl/worksheets/sheet1.xml') as f:
            for _,row in ET.iterparse(f,events=('end',)):
                if row.tag!=ns+'row':continue
                vals={}
                for cell in row.findall(ns+'c'):
                    m=re.match(r'([A-Z]+)',cell.get('r',''))
                    v=cell.find(ns+'v')
                    if m and v is not None:
                        text=v.text or ''
                        vals[m.group(1)] = strings[int(text)] if cell.get('t')=='s' and text else text
                yield vals
                row.clear()

@APP.post('/api/employer-data/import')
async def employer_import(file:UploadFile=File(...), fiscal_year:str=Form('2026')):
    raw=await file.read(15*1024*1024+1)
    if len(raw)>15*1024*1024:raise HTTPException(413,'Employer data import limited to 15 MB.')
    ext=Path(file.filename or '').suffix.lower()
    if ext=='.csv':
        r=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        iterator=(dict(row) for row in r)
    elif ext=='.xlsx':
        iterator=read_xlsx_employers(raw)
    else:raise HTTPException(422,'Employer data supports CSV or XLSX only.')
    rows=[];count=0
    for row in iterator:
        # Accept user-supplied USCIS hub schema or canonical generic CSV column names.
        name=next((row.get(key) for key in ('C','Employer','Employer Name','EMPLOYER_NAME','employer_name') if row.get(key)),None)
        if not name or (str(name).lower().strip() in ('employer name','employer')):continue
        year=str(next((row.get(k) for k in ('B','Fiscal Year','FY','fiscal_year') if row.get(k)),fiscal_year))
        def parse_num(keys):
            for key in keys:
                try:return int(float(str(row.get(key,''))))
                except (ValueError,TypeError):pass
            return None
        new=parse_num(('I','new_approvals','Initial Approvals','INITIAL_APPROVALS'))
        continuing=parse_num(('K','continuing_approvals','Continuing Approvals','CONTINUING_APPROVALS'))
        rows.append((normalize_company(str(name)),str(name).strip(),year,new,continuing,'user-imported, not independently validated'))
        count+=1
        if count>120000:raise HTTPException(413,'Max 120,000 employer records.')
    with conn() as c:c.executemany('INSERT OR REPLACE INTO employers VALUES(?,?,?,?,?,?)',rows)
    return {'imported_records':count,'note':'Employer-name matches are historical petition records only. Verify legal entity and job-specific eligibility.'}

app=APP
