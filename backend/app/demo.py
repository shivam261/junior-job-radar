"""Explicit, isolated demo fixtures. Never presented as real vacancies."""
import json
from . import db
from .collectors import normalize
from .companies import COMPANIES


def seed():
    db.initialize(mark_interrupted=False)
    rows=[
        ('autodesk','Software Engineer I','Bengaluru, India','Python · Java · AWS',0,2,'Hybrid'),
        ('mastercard','Software Engineer — Backend','Pune, India','Java · Spring · SQL',1,2,'Hybrid'),
        ('visa','Associate Software Engineer','Bengaluru, India','Java · React · Docker',0,2,'Not specified'),
        ('cisco','Software Engineer — Early Career','Bengaluru, India','C++ · Python · Linux',0,1,'Hybrid'),
        ('razorpay','Frontend Engineer I','Bengaluru, India','React · TypeScript · JavaScript',1,2,'Hybrid'),
        ('ge-vernova','Software Engineer — Graduate','Hyderabad, India','Python · Azure · SQL',0,0,'Not specified'),
        ('jpmorgan-chase','Software Engineer I — Java','Mumbai, India','Java · Spring · AWS',0,2,'Hybrid'),
        ('deutsche-bank','Associate Software Engineer','Pune, India','Java · SQL · Git',1,2,'Hybrid'),
        ('goldman-sachs','Software Engineer — New Analyst','Bengaluru, India','Python · Java · SQL',0,2,'Not specified'),
        ('hsbc','Graduate Software Engineer','Hyderabad, India','Python · React · Azure',0,1,'Hybrid'),
        ('atlassian','Graduate Software Engineer','Remote, India','Java · React · AWS',None,None,'Remote'),
        ('zomato','Software Development Engineer I','Gurugram, India','Go · Python · SQL',0,2,'Not specified'),
        ('cognizant','Junior Full Stack Developer','Chennai, India','React · Java · SQL',None,None,'Hybrid'),
        ('stripe','Software Engineer — New Grad','Remote, United States','Java · Python · Ruby',None,None,'Remote'),
        ('databricks','Software Engineer — University Graduate','San Francisco, United States','Python · Java · SQL',0,2,'Hybrid'),
        ('phonepe','Software Engineer I','Bengaluru, India','Java · Kubernetes · SQL',0,2,'Not specified'),
    ]
    lookup={c['id']:c for c in COMPANIES}
    for i,(company,title,location,skills,low,high,mode) in enumerate(rows):
        c=lookup[company]
        requirement=f'{low}–{high} years of professional experience.' if low is not None else 'We welcome university graduates and early-career engineers.'
        description=f'''DEMONSTRATION DATA — this is an illustrative role, not a current vacancy.\n\nAbout the role\nBuild thoughtful software and collaborate with a cross-functional engineering team.\n\nWhat you will do\nDesign and implement reliable services. Write maintainable code, review pull requests, and contribute to automated testing.\n\nWhat you will bring\n{requirement}\nWorking knowledge of {skills}. Strong problem-solving and communication skills.\n\nWork arrangement\n{mode}.\n\nThis example links to the company's careers page, not an individual job posting.'''
        job=normalize(c,f'demo-{i}',title,location,description,c['url'])
        if job:
            job['id']='demo-'+job['id']
            with db.connection() as conn:
                values={**job,'company_id':company,'first_seen':db.now(),'last_seen':db.now(),'active':1,'demo':1}
                values['skills']=json.dumps(values['skills'])
                fields=list(values)
                updates=','.join(f"{f}=excluded.{f}" for f in fields if f not in ('id','company_id','source_id','first_seen'))
                conn.execute(f"INSERT INTO jobs({','.join(fields)}) VALUES({','.join('?' for _ in fields)}) ON CONFLICT(company_id,source_id) DO UPDATE SET {updates}",[values[f] for f in fields])
    print('Demo fixtures created. Select Preview demo in the interface; live results remain separate.')


if __name__ == '__main__': seed()
