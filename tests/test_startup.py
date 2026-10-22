"""Start the real Streamlit server and check its HTTP health endpoint."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


def test_review_imports_and_application_startup(tmp_path):
    """A healthy HTTP server alone does not execute app.py or catch import failures."""
    environment = dict(os.environ, RTA_DB_PATH=str(tmp_path / 'imports.sqlite3'))
    script = '''
import ast
import inspect
from pathlib import Path
import rta.review as review
from rta.review import source_suggestion, suggestion_version, validate_suggestion_approval
from streamlit.testing.v1 import AppTest

expected = Path('rta/review.py').resolve()
assert Path(review.__file__).resolve() == expected, review.__file__
assert expected.name == 'review.py'
assert not any('\\\\' in path.name for path in expected.parent.iterdir())
assert [path.name for path in expected.parent.glob('review*.py')] == ['review.py']
inspect.signature(source_suggestion).bind(object(), {}, 0)
inspect.signature(suggestion_version).bind(object(), {})
inspect.signature(validate_suggestion_approval).bind(object(), {}, {})
for node in ast.walk(ast.parse(Path('app.py').read_text())):
    if isinstance(node, ast.ImportFrom) and node.module == 'rta.review':
        for symbol in node.names:
            assert callable(getattr(review, symbol.name)), symbol.name
app = AppTest.from_file(Path('app.py').resolve(), default_timeout=30).run()
assert not app.exception, [error.message for error in app.exception]
print('Canonical review imports and application startup passed.')
'''
    completed = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                               env=environment, capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_streamlit_startup_smoke(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    environment = dict(os.environ, RTA_DB_PATH=str(tmp_path / 'smoke.sqlite3'))
    process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(Path('app.py').resolve()),
        '--server.headless=true', '--server.address=127.0.0.1', f'--server.port={port}'],
        env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            assert process.poll() is None, 'Streamlit exited during startup'
            try:
                with urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
                    assert response.status == 200
                    assert response.read().strip() == b'ok'
                    return
            except OSError:
                time.sleep(0.1)
        raise AssertionError('Streamlit did not become healthy within 30 seconds')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
