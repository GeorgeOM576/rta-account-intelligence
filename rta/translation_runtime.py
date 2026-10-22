"""Detect cached Python modules left behind by Streamlit app-only reloads."""
import hashlib
from pathlib import Path
import sys


def stale_translation_modules():
    stale = []
    for name in ('translation', 'translation_ui', 'translation_workspace', 'translation_providers',
                 'translation_diagnostics', 'export', 'google_detection', 'google_languages', 'google_auth'):
        module = sys.modules.get(f'rta.{name}')
        if module is None:
            continue
        path = Path(module.__file__)
        loaded = getattr(module, 'GOOGLE_BUILD' if name == 'google_detection' else 'LOADED_BUILD', None)
        if loaded != hashlib.sha256(path.read_bytes()).hexdigest():
            stale.append(str(path.resolve()))
    return stale
