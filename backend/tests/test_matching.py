import pytest
from app.matching import match_job

@pytest.mark.parametrize('title,description,confidence',[
    ('Software Engineer','Required: 0-2 years of professional experience.','confirmed'),
    ('Software Engineer','At least 1 year of experience with Java.','confirmed'),
    ('Software Engineer','Minimum 2+ years of relevant experience.','confirmed'),
    ('Software Engineer','No previous experience required.','confirmed'),
    ('Graduate Software Engineer','Strong communication skills.','possible'),
    ('Software Development Engineer I','BS in computer science.','possible'),
    ('Junior Frontend Engineer','Knowledge of React.','possible'),
])
def test_early_matches(title,description,confidence):
    assert match_job(title,description).confidence==confidence

@pytest.mark.parametrize('title,description',[
    ('Senior Software Engineer','0-2 years of experience.'),
    ('Software Engineer III','0-2 years of experience.'),
    ('Software Engineer','3 years of professional experience.'),
    ('Junior Software Engineer','5+ years of experience in Java.'),
    ('Software Engineer','2–5 years of professional experience.'),
    ('Software Engineer','1 year of experience in React. 4 years of experience building applications.'),
    ('Mechanical Engineer','0-2 years of experience.'),
    ('Software Engineer','We have served customers for 20 years. Great benefits.'),
    ('Software Engineer','A four-year degree and strong fundamentals.'),
    ('Software Engineer','Experience with Python.'),
])
def test_exclusions(title,description):
    assert match_job(title,description) is None

def test_html_and_evidence():
    m=match_job('Software Engineer','<ul><li>1–2 years of software development experience.</li></ul>')
    assert (m.experience_min,m.experience_max)==(1,2)
    assert '1–2 years' in m.evidence


def test_escaped_html_content_is_decoded():
    from app.matching import plain
    assert plain('&lt;p&gt;React and Python&lt;/p&gt;')=='React and Python'
    assert match_job('Software Engineer','&lt;p&gt;1–2 years of experience.&lt;/p&gt;').confidence=='confirmed'
