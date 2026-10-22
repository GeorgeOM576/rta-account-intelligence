"""Deployment packaging must exclude credentials and mutable workspace data."""
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def packaging_repo(tmp_path):
    subprocess.run(['git','init','--quiet',str(tmp_path)],check=True,capture_output=True)
    shutil.copyfile(ROOT / '.gitignore', tmp_path / '.gitignore')
    return tmp_path


@pytest.mark.parametrize('path', [
    '.venv/bin/python', '.venv_old/bin/python', '.env', '.env.production',
    '.streamlit/secrets.toml', 'application_default_credentials.json',
    'credentials/account.json', 'random-google-key.json', 'private.pem',
    'tests/fixtures/nested/service_account.json', 'my-resume-token.json',
    'data/rta.sqlite3', 'data/rta.sqlite3-wal', 'work.db-journal',
    'uploads/accounts.csv', 'customer.csv', 'customer.xlsx',
    'customer.parquet', 'logs/action.log', 'checkpoints/workspace.tar.gz',
    '__pycache__/app.pyc', 'outputs/customer-export.xlsx',
])
def test_sensitive_and_mutable_files_are_ignored(packaging_repo,path):
    result = subprocess.run(['git','-C',str(packaging_repo),'check-ignore','-q','--',path])
    assert result.returncode == 0, path


@pytest.mark.parametrize('path', ['app.py','requirements.txt','.streamlit/config.toml',
    '.streamlit/secrets.toml.example', 'samples/master.csv',
    'tests/fixtures/language_detection/labelled_cases.json',
    'tests/fixtures/translation_intelligence/fictional_master_accounts.xlsx'])
def test_runtime_and_reviewed_fixtures_remain_publishable(packaging_repo,path):
    result = subprocess.run(['git','-C',str(packaging_repo),'check-ignore','-q','--',path])
    assert result.returncode == 1, path


def test_secrets_template_is_valid_toml_with_empty_keys():
    data = tomllib.loads((ROOT / '.streamlit/secrets.toml.example').read_text())
    assert data == {'OPENAI_API_KEY':'','TAVILY_API_KEY':''}


def test_runtime_sources_and_template_contain_no_embedded_provider_keys():
    pattern = re.compile(r'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|tvly-[A-Za-z0-9_-]{15,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----')
    for path in [ROOT/'app.py', ROOT/'.streamlit/secrets.toml.example', *sorted((ROOT/'rta').glob('*.py'))]:
        assert not pattern.search(path.read_text()), f'Potential credential in {path.name}'
