"""Distinguish the user-selected visible schema from retained backend/export fields."""
import csv
import io
import os
from pathlib import Path

import pandas as pd

from rta.approved_names import ApprovedNames
from rta.export import result_row
from rta.models import Mapping, Result
from rta.storage import Store
from rta.translation import TranslationEngine


def csv_columns():
    raw = Path('tests/fixtures/reconciliation_table/visible_columns.csv').read_bytes()
    return next(csv.reader(io.StringIO(raw.decode('cp1252'))))


def rendered_table(app):
    return next(frame.value for frame in app.dataframe if 'Master Identifier' in frame.value.columns)


def backend_row(app, record_id):
    store = Store(os.environ['RTA_DB_PATH'])
    project = app.session_state['project']
    payload = store.load(project)
    result = Result(**next(r for r in payload['results'] if r['row_id'] == record_id))
    ApprovedNames(payload, Mapping(**payload['mapping']), TranslationEngine(store, project).records()).attach([result])
    return result_row(result)


def visible_and_backend_row(app):
    """Assert actual render schema, then expose hidden fields for backend regressions."""
    table = rendered_table(app)
    assert list(table.columns) == csv_columns()
    current = table.iloc[0]
    return pd.Series({**backend_row(app, current['Record ID']), **current.to_dict()})
