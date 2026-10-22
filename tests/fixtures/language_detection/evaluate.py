"""Compare frozen v1 outputs with current field-aware policy on manually labelled data."""
from collections import Counter
import json
from pathlib import Path

from rta.language_detection import detect_text, VERSION

ROOT = Path(__file__).resolve().parent


def evaluate():
    cases = json.loads((ROOT / 'labelled_cases.json').read_text())
    baseline = json.loads((ROOT / 'baseline_v1.json').read_text())
    assert [{k: v for k, v in r.items() if k != 'prediction'} for r in baseline] == cases
    current = [{**row, 'prediction': detect_text(row['text'], row['field_kind'])} for row in cases]
    def summarize(rows):
        positives = [r for r in rows if r['prediction']['status'] == 'Translation Needed']
        true = [r for r in positives if r['label'] == 'foreign']
        foreign = [r for r in rows if r['label'] == 'foreign']
        return {
            'cases': len(rows), 'labels': dict(Counter(r['label'] for r in rows)),
            'foreign_candidates': len(positives), 'true_positives': len(true),
            'false_positives': len(positives) - len(true), 'false_negatives': len(foreign) - len(true),
            'precision': len(true) / len(positives) if positives else 0,
            'recall': len(true) / len(foreign),
            'correct_foreign_language_codes': sum(r['prediction']['language'] == r['language'] for r in true),
            'english_confident': sum(r['label'] == 'english' and r['prediction']['language'] == 'en' and r['prediction']['status'] == 'Not Required' for r in rows),
            'english_manual_review': sum(r['label'] == 'english' and r['prediction']['status'] == 'Uncertain' for r in rows),
            'false_positive_texts': [r['text'] for r in positives if r['label'] != 'foreign'],
            'missed_foreign_texts': [r['text'] for r in foreign if r['prediction']['status'] != 'Translation Needed'],
            'ambiguous_texts': [r['text'] for r in rows if r['prediction']['status'] == 'Uncertain'],
            'foreign_by_language': dict(Counter(r['language'] for r in true)),
        }
    return {'policy': VERSION, 'baseline': summarize(baseline), 'current': summarize(current),
            'reported_cases': [{**r, 'before': baseline[i]['prediction']} for i, r in enumerate(current) if r['group'] == 'reported'],
            'predictions': current}


if __name__ == '__main__':
    result = evaluate()
    (ROOT / 'evaluation.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: result[key] for key in ('policy', 'baseline', 'current')}, indent=2, ensure_ascii=False))
