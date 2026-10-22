"""Synthetic Google-response routing comparison, never a real Google benchmark.

Response languages/confidences are fabricated from hand labels solely to verify
adapter and policy behavior without network access. Do not cite these figures as
Google detection accuracy. Local figures run the real retained offline policy.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from rta.google_detection import GoogleDetectionProvider, interpret, preflight, GOOGLE_POLICY
from tests.fixtures.language_detection.evaluate import evaluate

ROOT = Path(__file__).resolve().parent


def compare():
    cases = json.loads((ROOT / 'labelled_cases.json').read_text())
    client = Mock()
    outputs = []
    for case in cases:
        code = case['language'] or 'und'
        client.detect_language.return_value = SimpleNamespace(languages=[
            SimpleNamespace(language_code=code, confidence=0.99 if code != 'und' else 0.4)])
        raw = None
        if not preflight(case['text'], case['field_kind']):
            raw = GoogleDetectionProvider(consent=True, client=client).detect(case['text'])
        outputs.append({**case, 'prediction': interpret(case['text'], case['field_kind'], raw=raw)})
    positives = [r for r in outputs if r['prediction']['status'] == 'Translation Needed']
    true = [r for r in positives if r['label'] == 'foreign']
    return {'measurement': 'Synthetic Google response routing only; actual Google accuracy is NOT measured.',
            'response_origin': 'Fabricated directly from manual labels, not captured Google API results.',
            'live_api_calls': 0, 'cases': len(cases), 'policy': GOOGLE_POLICY,
            'real_offline_policy': evaluate()['current'],
            'mock_google_routing': {'foreign_candidates': len(positives), 'true_positives': len(true),
                'false_positives': len(positives) - len(true), 'precision': len(true) / len(positives),
                'recall': len(true) / sum(r['label'] == 'foreign' for r in outputs),
                'foreign_manual_review': [r['text'] for r in outputs if r['label'] == 'foreign' and r['prediction']['status'] != 'Translation Needed']},
            'predictions': outputs}


if __name__ == '__main__':
    result = compare()
    (ROOT / 'google_mock_evaluation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'predictions'}, indent=2, ensure_ascii=False))
