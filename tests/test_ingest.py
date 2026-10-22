from io import BytesIO

import polars as pl
import pytest
from openpyxl import Workbook

from rta.ingest import identifier_stats, parse_file
from rta.matching import Matcher
from rta.models import Mapping


@pytest.mark.parametrize('ids,missing,duplicates', [
    (pl.Series('ID', [], dtype=pl.Null), 0, 0),
    (pl.Series('ID', [None, None]), 2, 0),
    (pl.Series('ID', ['', '  ', '\t', None]), 4, 0),
    (pl.Series('ID', [0, 42, 42, None]), 1, 2),
    (pl.Series('ID', ['00042', '42', ' 42 ', None, '']), 2, 2),
])
def test_identifier_stats_dtypes(ids, missing, duplicates):
    frame = ids.to_frame()
    assert identifier_stats(frame, 'ID') == {
        'Missing identifiers': missing,
        'Rows with duplicate identifiers': duplicates,
    }
    assert frame['ID'].dtype == ids.dtype
    assert frame['ID'].to_list() == ids.to_list()


@pytest.mark.parametrize('suffix', ['csv', 'xlsx'])
def test_blank_ingested_columns(suffix):
    if suffix == 'csv':
        data = b'ID,Value\n,SMB\n,Enterprise\n'
    else:
        book = Workbook()
        book.active.append(['ID', 'Value'])
        book.active.append([None, 'SMB'])
        book.active.append([None, 'Enterprise'])
        output = BytesIO()
        book.save(output)
        book.close()
        data = output.getvalue()
    frame = parse_file(data, f'blank.{suffix}')
    assert frame['ID'].dtype == pl.Utf8
    assert identifier_stats(frame, 'ID') == {
        'Missing identifiers': 2, 'Rows with duplicate identifiers': 0,
    }
    mapping = Mapping('ID', 'ID', 'Value', 'Value')
    results = Matcher(frame, mapping).run(frame)
    assert all(r.match_status == 'Missing identifier' and not r.candidates for r in results)


def test_excel_mixed_ids_preserve_text_and_number_padding():
    book = Workbook()
    sheet = book.active
    sheet.append(['Unused', 'Value', 'ID'])
    for identifier in ['00042', 42, 7, 'AC-9', None, '  ']:
        sheet.append([None, 'SMB', identifier])
    sheet['C4'].number_format = '00000'
    output = BytesIO()
    book.save(output)
    book.close()
    frame = parse_file(output.getvalue(), 'mixed.xlsx')
    assert frame['ID'].to_list() == ['00042', '42', '00007', 'AC-9', None, '  ']
    assert frame['Unused'].dtype == pl.Utf8
    assert identifier_stats(frame, 'ID') == {
        'Missing identifiers': 2, 'Rows with duplicate identifiers': 0,
    }
    mapping = Mapping('ID', 'ID', 'Value', 'Value')
    results = Matcher(frame, mapping).run(frame)
    assert [r.identifier for r in results] == ['00042', '42', '00007', 'AC-9', '', '  ']
    assert [r.match_status for r in results] == ['Exact'] * 4 + ['Missing identifier'] * 2
    assert [r.proposed for r in results] == ['SMB'] * 4 + ['', '']
    assert [r.final for r in results] == [''] * 6


def test_numeric_and_null_mapped_identifiers():
    mapping = Mapping('Account', 'Company', 'Segment', 'Value')
    master = pl.DataFrame({'Account': [0, 42, None], 'Segment': ['SMB'] * 3})
    source = pl.DataFrame({'Company': ['0', '42', None], 'Value': ['SMB'] * 3})
    for left, right, columns in [(master, source, mapping), (
        source, master, Mapping('Company', 'Account', 'Value', 'Segment'),
    )]:
        results = Matcher(right, columns).run(left)
        assert [r.identifier for r in results] == ['0', '42', '']
        assert [r.match_status for r in results] == ['Exact', 'Exact', 'Missing identifier']
    blank = master.with_columns(pl.lit(None).alias('Account'))
    assert all(r.match_status == 'Missing identifier' for r in Matcher(source, mapping).run(blank))
    assert not Matcher(blank, Mapping('Company', 'Account', 'Value', 'Segment')).normal
    assert master['Account'].dtype == pl.Int64
