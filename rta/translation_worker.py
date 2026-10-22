"""Argos subprocess boundary; all network access is disabled, including model downloads.

May run under a separately configured compatible Python via RTA_ARGOS_PYTHON.
Only installed, direct-to-English models are permitted.
"""
import contextlib
import hashlib
import importlib.metadata
import io
import json
import socket
import sys


def deny_network(*args, **kwargs):
    raise OSError('Offline worker: network disabled.')


def main():
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    request = json.load(sys.stdin)
    # Suppress third-party diagnostics that might include uploaded text.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import argostranslate.package as package
        installed = [p for p in package.get_installed_packages() if p.to_code == 'en']
        versions = sorted((p.from_code, p.to_code, str(p.package_version)) for p in installed)
        fingerprint = hashlib.sha256(json.dumps(versions).encode()).hexdigest()
        if request['action'] == 'info':
            output = {'model': importlib.metadata.version('argostranslate') + ':' + fingerprint,
                      'languages': sorted({p.from_code for p in installed})}
        else:
            if not any(p.from_code == request['language'] for p in installed):
                raise ValueError('No installed direct English model.')
            import argostranslate.translate as translate
            output = {'english': translate.translate(request['text'], request['language'], 'en')}
    print(json.dumps(output))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No traceback, original text, credentials, or provider response bodies.
        sys.exit(1)
