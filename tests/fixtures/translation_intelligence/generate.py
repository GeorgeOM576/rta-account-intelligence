"""Generate small, entirely fictional XLSX fixtures; no network or customer data."""
import json
from pathlib import Path
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent
PAIRS = [
    ('Aster Lantern Analytics', 'Aster Lantern Analytics', 'SMB'),
    ('Les Ateliers de la Lune Violette', 'Violet Moon Workshops', 'Enterprise'),
    ('Servicios del Río de Cristal', 'Crystal River Services', 'Commercial'),
    ('Werkstätten am Silbernen Morgen', 'Silver Morning Workshops', 'SMB'),
    ('Amber Orchard Logistics', 'Logistique du Verger Ambré', 'Commercial'),
    ('Azure Harbor Research', 'Investigación del Puerto Azul', 'Enterprise'),
    ('Golden Meadow Systems', 'Systeme der Goldenen Wiese', 'SMB'),
    ('La Fabrique des Nuages Bleus', 'La Fábrica de las Nubes Azules', 'Commercial'),
    ('Cobalt Lantern Supply', 'Cobalt Lantarn Supply', 'SMB'),
    ('Pine Comet Design Services', 'Pine Comet Design Services', 'Enterprise'),
    ('Unmatched Copper Kite Observatory', 'Unmatched Velvet Acorn Atelier', 'Commercial'),
    ('Banque des Étoiles de Papier', 'Banque des Étoiles de Papier', 'Enterprise'),
]
TRANSLATIONS = {
    PAIRS[1][0]: 'Violet Moon Workshops',
    PAIRS[2][0]: 'Crystal River Services',
    PAIRS[3][0]: 'Silver Morning Workshops',
    PAIRS[4][1]: 'Amber Orchard Logistics',
    PAIRS[5][1]: 'Azure Harbor Research',
    PAIRS[6][1]: 'Golden Meadow Systems',
    PAIRS[7][0]: 'Blue Cloud Factory',
    PAIRS[7][1]: 'Blue Cloud Factory',
    PAIRS[11][0]: 'Paper Star Bank',
}


def main():
    for dataset, side, prefix in [('master', 0, 'M'), ('source', 1, 'S')]:
        book = Workbook()
        sheet = book.active
        sheet.title = 'Fictional Accounts'
        sheet.append(['Account ID', 'Account Name', 'Segment', 'Trading Name'])
        for index, pair in enumerate(PAIRS):
            # Identifiers deliberately differ; match on mapped Account Name, not fixture correspondence.
            sheet.append([f'{prefix}-{index + 1:03}', pair[side],
                          'Verify' if dataset == 'master' else pair[2], pair[side]])
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for column in ['A', 'B', 'C', 'D']:
            sheet.column_dimensions[column].width = 42 if column in ('B', 'D') else 18
        book.save(ROOT / f'fictional_{dataset}_accounts.xlsx')
    expected = {'translations': TRANSLATIONS,
                'master_flagged_rows': [1, 2, 3, 7, 11], 'source_flagged_rows': [4, 5, 6, 7, 11],
                'approve_master_rows': [1, 2, 3, 7], 'approve_source_rows': [4, 5, 6, 7],
                'translation_assisted_rows': list(range(1, 8)),
                'segments': [pair[2] for pair in PAIRS]}
    (ROOT / 'expected.json').write_text(json.dumps(expected, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
