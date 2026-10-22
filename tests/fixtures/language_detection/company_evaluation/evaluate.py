"""Offline diagnostic only. Synthetic stimuli are NOT measured Google accuracy.

Run: PYTHONPATH=. .venv/bin/python tests/fixtures/language_detection/company_evaluation/evaluate.py
No Store, credentials, SDK client, network or workspace records are used.
"""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from rta.google_detection import interpret, CLASSIFICATION_POLICY, GOOGLE_BUILD
from rta.language_detection import ENGLISH, FOREIGN, AMBIGUOUS, EXCLUDED

ROOT = Path(__file__).resolve().parent
LANGUAGES = {
    'en': ['Harbor Coastal Research LLC', 'Silver Meadow Engineering', 'Northern Valley Logistics',
           'Bright River Medical Supplies', 'Oak Forest Financial Services', 'Blue Coast Energy Systems',
           'Golden Field Agricultural Products', 'Westbridge Industrial Equipment', 'Cedar Grove Digital Services',
           'Orchard Scientific Instruments', 'Lighthouse Community Healthcare', 'Pioneer Coastal Data Solutions',
           'Summit International Freight', 'Bluebird Creative Design Studio', 'Green Valley Business Services',
           'Moonlit Harbor Technology Group'],
    'fr': ['Les Ateliers du Rivage SAS', 'Société des Services Portuaires', 'Boulangerie des Trois Rivières',
           'Les Jardins du Lac Bleu', 'Compagnie des Énergies Renouvelables', 'Maison de la Santé Familiale',
           'Éditions de la Forêt Verte', 'Les Artisans du Vieux Moulin', 'Transport des Marchandises du Nord',
           'Fabrique de Produits Laitiers', 'Atelier Lumière', 'Banque des Petites Entreprises'],
    'es': ['Servicios de Ingeniería Rivera SA', 'Compañía de Energía Renovable', 'Panadería del Valle Verde',
           'Distribuidora de Productos Agrícolas', 'Soluciones de Salud Comunitaria', 'Talleres del Puerto Azul',
           'Jardines de la Sierra Dorada', 'Fábrica de Materiales Sostenibles', 'Transportes de la Costa Norte',
           'Servicios de Investigación Médica', 'Taller Azul', 'Comercio de Alimentos Frescos'],
    'de': ['Deutsche Werkstätten am Fluss GmbH', 'Bäckerei Sonnental', 'Gesellschaft für Erneuerbare Energien',
           'Werkstatt für Medizinische Geräte', 'Gärten am Silbernen See', 'Handel mit Landwirtschaftlichen Produkten',
           'Institut für Technische Forschung', 'Hersteller von Nachhaltigen Baustoffen', 'Dienstleistungen für Kleine Unternehmen',
           'Transport und Lagerung Nordhafen', 'Blumen Wiese', 'Bäckerei am Alten Rathaus'],
    'pt': ['Empresa de Energia Renovável Ltd', 'Comércio de Produtos Florestais', 'Padaria do Vale Verde',
           'Serviços de Saúde Comunitária', 'Distribuidora de Alimentos Frescos', 'Oficina de Equipamentos Médicos',
           'Jardins da Serra Dourada', 'Fábrica de Materiais Sustentáveis', 'Transportes da Costa Norte',
           'Sociedade de Investigação Científica', 'Padaria Sol', 'Soluções para Pequenas Empresas'],
    'ar': ['شركة الحدائق الخضراء للتجارة', 'مؤسسة النور للخدمات الطبية', 'شركة الطاقة المتجددة العربية',
           'مصنع المواد الغذائية الطازجة', 'خدمات النقل والتخزين الحديثة', 'شركة البحوث العلمية المتقدمة',
           'مؤسسة المعدات الصناعية الحديثة', 'مخبز الوادي الأخضر', 'شركة الحلول التقنية المتكاملة',
           'مركز الرعاية الصحية المجتمعية', 'الحدائق الخضراء', 'شركة المنتجات الزراعية المستدامة'],
    'zh': ['青山绿色能源科技有限公司', '晨光医疗设备有限公司', '海湾食品贸易有限公司',
           '长河物流运输有限公司', '春雨农业技术有限公司', '蓝天环保材料有限公司',
           '明月科学仪器有限公司', '绿洲社区健康服务中心', '金桥工业设备有限公司',
           '白云信息技术有限公司', '星河科技', '东方可再生能源研究所'],
    'ja': ['株式会社青空物流', '株式会社緑の森食品', 'さくら医療機器株式会社',
           '株式会社未来環境技術', 'ひかり地域健康サービス', '株式会社朝日農業研究',
           '株式会社海辺のパン工房', 'みどり再生可能エネルギー株式会社', '株式会社星空科学機器',
           '株式会社川辺の建築材料', 'さくら商事', '株式会社未来情報システム'],
}
BRANDS = ['Google', 'Microsoft', 'Apple', 'Amazon', 'Meta', 'Uber', 'Toyota', 'Sony',
          'Samsung', 'IKEA', 'Siemens', 'Nestlé', "L’Oréal", 'Alibaba', 'Huawei',
          'Toyota Motor Corporation', 'Samsung Electronics Ltd', 'Nova', 'Orion', 'Data Studio']
MIXED = ['شركة Sunrise للتجارة', '青山 Global Services', '東京 Digital Labs', 'Atelier Casa Verde']
# Same predeclared confidence schedule for every language: designed boundary
# coverage, not random sampling or confidence calibration of Google responses.
CONFIDENCES = [.99, .96, .92, .90, .899, .87, .84, .79, .94, .97, .93, .91, .98, .88, .95, .86]


def build_cases():
    saved = json.loads((ROOT.parent / 'google_live_25.json').read_text())
    cases = []
    for row in saved['results']:
        language = None if row['expected_language'] == 'ambiguous' else row['expected_language']
        cases.append({'text': row['name'], 'expected_language': language,
                      'expected_outcome': 'manual' if language is None else 'english' if language == 'en' else 'foreign',
                      'label_basis': 'User-provided expected language from approved 25-name dataset; ambiguity explicitly retained.',
                      'response_origin': 'saved_live_google', 'raw': deepcopy(row['raw']), 'tags': ['saved_25']})
    for language, texts in LANGUAGES.items():
        for index, text in enumerate(texts):
            cases.append({'text': text, 'expected_language': language,
                          'expected_outcome': 'english' if language == 'en' else 'foreign',
                          'label_basis': 'Author-labelled language of descriptive wording/script; fictional name, not entity nationality.',
                          'response_origin': 'synthetic', 'raw': {'language_code': language, 'confidence': CONFIDENCES[index], 'alternatives': []},
                          'tags': ['descriptive', 'confidence_boundary']})
    for index, text in enumerate(BRANDS):
        code = 'fr' if text in ('Nestlé', 'L’Oréal') else 'ja' if text in ('Toyota', 'Sony') else 'en'
        cases.append({'text': text, 'expected_language': None, 'expected_outcome': 'manual',
                      'label_basis': 'Brand/proper noun: country of origin does not determine the language of an account name.',
                      'response_origin': 'synthetic', 'raw': {'language_code': code, 'confidence': .97, 'alternatives': []},
                      'tags': ['international_brand_or_ambiguous']})
    for text in MIXED:
        cases.append({'text': text, 'expected_language': None, 'expected_outcome': 'manual',
                      'label_basis': 'Mixed-script/language or shared vocabulary; no single definitive language assigned.',
                      'response_origin': 'synthetic', 'raw': {'language_code': 'en', 'confidence': .96, 'alternatives': []},
                      'tags': ['mixed_or_conflicting']})
    # Deliberately wrong API suggestions test policy failure modes. These are
    # fabricated stress inputs, never observations about Google's error rates.
    overrides = {
        'Société des Services Portuaires': ('en', .96, []),
        'Bäckerei Sonnental': ('en', .96, []),
        'Comércio de Produtos Florestais': ('en', .87, []),
        'Moonlit Harbor Technology Group': ('fr', .86, []),
        'Harbor Coastal Research LLC': ('en', .99, []),
        'Westbridge Industrial Equipment': ('de', .79, []),
        'Les Artisans du Vieux Moulin': ('es', .97, []),
        'خدمات النقل والتخزين الحديثة': ('en', .96, []),
        '长河物流运输有限公司': ('en', .96, []),
        'Talleres del Puerto Azul': ('es', .97, [{'language_code': 'pt', 'confidence': .85}]),
    }
    for case in cases:
        if case['text'] in ('Atelier Lumière', 'Taller Azul', 'Blumen Wiese', 'Padaria Sol', '星河科技'):
            case['expected_language'] = None
            case['expected_outcome'] = 'manual'
            case['label_basis'] = 'Brief name/shared vocabulary or Han-only brand: intended language is not definitive without context.'
            case['tags'].append('explicitly_uncertain_short_name')
        if case['response_origin'] == 'synthetic' and case['text'] in overrides:
            code, score, alternatives = overrides[case['text']]
            case['raw'] = {'language_code': code, 'confidence': score, 'alternatives': alternatives}
            case['tags'].append('deliberate_mock_error_or_competition')
    assert len(cases) >= 100 and len({r['text'] for r in cases}) == len(cases)
    return cases


def evaluate(cases, classify=interpret):
    outputs = []
    for case in cases:
        result = classify(case['text'], 'account_name', raw=case['raw'])
        outcome = {ENGLISH: 'english', FOREIGN: 'foreign', AMBIGUOUS: 'manual', EXCLUDED: 'excluded'}[result['detection_outcome']]
        outputs.append({**case, 'actual_outcome': outcome, 'actual_language': result['language'], 'reason': result['reason']})
    definitive = [r for r in outputs if r['expected_language'] is not None]
    positives = [r for r in definitive if r['actual_outcome'] == 'foreign']
    foreign = [r for r in definitive if r['expected_outcome'] == 'foreign']
    tp = sum(r['expected_outcome'] == 'foreign' for r in positives)
    fp = len(positives) - tp
    correct = sum(r['actual_language'] == r['expected_language'] and r['actual_outcome'] == r['expected_outcome'] for r in definitive)
    incorrect = sum(r['actual_outcome'] in ('english', 'foreign') and (r['actual_language'] != r['expected_language'] or r['actual_outcome'] != r['expected_outcome']) for r in definitive)
    manual = [r for r in definitive if r['actual_outcome'] == 'manual']
    unnecessary = [r for r in manual if r['raw']['language_code'].split('-')[0] == r['expected_language'] and
                   r['raw']['confidence'] >= .90 and r['raw']['confidence'] - max(
                       (a['confidence'] for a in r['raw'].get('alternatives', []) if a['language_code'] != r['raw']['language_code']), default=0) >= .20]
    ambiguous = [r for r in outputs if r['expected_language'] is None]
    return {'cases': len(cases), 'definitive_cases': len(definitive), 'correct': correct, 'incorrect': incorrect,
            'definitive_manual_reviews': len(manual), 'potentially_unnecessary_manual_reviews': len(unnecessary),
            'foreign_missed': len(foreign) - tp, 'foreign_as_english': sum(r['actual_outcome'] == 'english' for r in foreign),
            'tp': tp, 'fp': fp, 'fn': len(foreign) - tp,
            'precision': tp / len(positives) if positives else None, 'recall': tp / len(foreign) if foreign else None,
            'correct_language_foreign_recall': sum(r['actual_language'] == r['expected_language'] and r['actual_outcome'] == 'foreign' for r in foreign) / len(foreign),
            'ambiguity_retained': sum(r['actual_outcome'] in ('manual', 'excluded') for r in ambiguous),
            'ambiguous_cases': len(ambiguous),
            'ambiguity_wrongly_automated': sum(r['actual_outcome'] in ('english', 'foreign') for r in ambiguous),
            'confusion': {truth: dict(Counter(r['actual_outcome'] for r in outputs if r['expected_outcome'] == truth)) for truth in ('english', 'foreign', 'manual')},
            'review_reasons': dict(Counter(r['reason'] for r in manual)), 'outputs': outputs}


def run():
    # Preserve every historical result and the exact pre-labelled corpus.
    cases = json.loads((ROOT / 'labelled_cases.json').read_text())
    assert cases == build_cases()
    baseline = json.loads((ROOT / 'results_after_refinement.json').read_text())['scenarios']['current_90']
    current = evaluate(cases)
    report = {'policy': CLASSIFICATION_POLICY, 'production_build': GOOGLE_BUILD,
              'confidence_policy': 'Advisory only; valid supported Google language codes drive eligibility',
              'live_calls': 0, 'before_v3': baseline, 'google_direct_v4': current,
              'saved_only': evaluate([r for r in cases if r['response_origin'] == 'saved_live_google']),
              'synthetic_only': evaluate([r for r in cases if r['response_origin'] == 'synthetic'])}
    (ROOT / 'results_google_direct.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in current.items() if k not in ('outputs', 'review_reasons', 'confusion')}, indent=2))
    return report


if __name__ == '__main__':
    run()
