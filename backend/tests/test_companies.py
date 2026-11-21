import json

from app.collectors import normalize
from app.companies import COMPANIES
from app.sources import identify, public_url


def test_expanded_directory_has_unique_public_sources_with_supported_collectors():
    from app.collectors import Collector

    expected = {'amazon', 'google', 'swish', 'ion-group', 'sprinto', 'zeta', 'mindtickle',
                'druva', 'harness', 'yugabytedb', 'glean', 'singlestore'}
    assert expected <= {c['id'] for c in COMPANIES}
    assert len(COMPANIES) >= 100
    assert len({c['id'] for c in COMPANIES}) == len(COMPANIES)
    assert len({c['url'] for c in COMPANIES}) == len(COMPANIES)
    for company in COMPANIES:
        assert public_url(company['url']) == company['url']
        assert callable(getattr(Collector, company['adapter']))


def test_corrected_sources_use_verified_boards():
    companies = {c['id']: c for c in COMPANIES}
    assert companies['browserstack']['url'] == 'https://browserstack.wd3.myworkdayjobs.com/External'
    assert companies['ibm']['url'] == 'https://www.ibm.com/in-en/careers/search'
    for company_id in ('browserstack', 'postman', 'phonepe', 'swiggy'):
        company = companies[company_id]
        assert identify(company['url']) == (company['adapter'], company['config'])
    assert companies['phonepe']['config']['token'] == 'PHONEPELIMITED'
    assert companies['swiggy']['config']['token'] == 'SWIGGY'
    assert companies['sap']['url'].startswith('https://careers.sap.com/')
    assert 'pid=' not in companies['ericsson']['url']


def test_restart_updates_old_portals_and_preserves_preferences_jobs_and_bookmarks(database):
    company = next(c for c in COMPANIES if c['id'] == 'browserstack')
    job = normalize(company, 'old-42', 'Software Engineer I', 'Mumbai, India',
                    '1–2 years of experience.', 'https://example.com/job/42')
    database.upsert_jobs(company['id'], [job], False)
    with database.connection() as conn:
        conn.execute("UPDATE companies SET enabled=0,adapter='html',url='https://www.browserstack.com/careers',config='{}' WHERE id='browserstack'")
        conn.execute('INSERT INTO bookmarks(job_id,saved_at) VALUES(?,?)', (job['id'], database.now()))
    database.initialize()
    with database.connection() as conn:
        updated = conn.execute("SELECT * FROM companies WHERE id='browserstack'").fetchone()
        assert updated['url'] == company['url'] and updated['adapter'] == 'workday'
        assert json.loads(updated['config']) == company['config'] and updated['enabled'] == 0
        assert conn.execute('SELECT active FROM jobs WHERE id=?', (job['id'],)).fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM bookmarks WHERE job_id=?', (job['id'],)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM companies WHERE id='ion-group'").fetchone()[0] == 1
