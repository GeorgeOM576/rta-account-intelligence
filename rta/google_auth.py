"""Lazy, shared Google v3 client authentication; never persist credential material."""
from collections.abc import Mapping
import hashlib
from pathlib import Path

LOADED_BUILD = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
PROJECT = 'rta-translation'
SCOPES = ('https://www.googleapis.com/auth/cloud-platform',)
SETUP_ERROR = ('Google authentication unavailable. Check [gcp_service_account] in Streamlit Secrets '
               'or local Application Default Credentials, and project IAM permissions.')


def translation_client():
    """Use explicit Cloud secrets when present; otherwise let Google resolve ADC.

    Called only by an authorized provider action. Never fall back to another
    identity when an explicitly configured service account is invalid.
    """
    try:
        import streamlit as st
        from streamlit.errors import StreamlitSecretNotFoundError
        try:
            section = st.secrets.get('gcp_service_account')
        except StreamlitSecretNotFoundError as error:
            if getattr(error, 'error_id', None) not in (None, 'no-secrets-found') or error.__cause__ is not None:
                raise
            section = None
        except FileNotFoundError:
            section = None
        from google.cloud import translate_v3
        from google.api_core.client_options import ClientOptions
        options = {'client_options': ClientOptions(quota_project_id=PROJECT)}
        if section is not None:
            if not isinstance(section, Mapping) or not section:
                raise ValueError()
            from google.oauth2 import service_account
            options['credentials'] = service_account.Credentials.from_service_account_info(
                dict(section), scopes=SCOPES)
        return translate_v3.TranslationServiceClient(**options)
    except Exception:
        # SDK/TOML/parser errors can contain private key or credential fields.
        raise ValueError(SETUP_ERROR) from None
