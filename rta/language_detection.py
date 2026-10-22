"""Conservative offline evidence policy; detector probabilities alone do not identify names."""
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import sys
import unicodedata

VERSION = 'field-aware-business-v2'
# Captured on import: a running server can compare its loaded build with disk.
# Include this in persistent keys so a rule edit invalidates detection without
# depending on a developer remembering to bump VERSION.
RULES_FINGERPRINT = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def runtime_info():
    disk = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {'policy': VERSION, 'loaded_build': RULES_FINGERPRINT, 'disk_build': disk,
            'restart_required': disk != RULES_FINGERPRINT, 'module_path': str(Path(__file__).resolve()),
            'process_id': os.getpid(), 'python_executable': sys.executable}


ENGLISH = 'Confident English — No Translation Needed'
FOREIGN = 'Confident Non-English — Translation Candidate'
AMBIGUOUS = 'Unknown/Ambiguous — Manual Language Review'
EXCLUDED = 'Excluded field — Translation Disabled'
FIELD_KINDS = ('account_name', 'classification', 'description', 'free_text', 'identifier')
DEFAULT_BUSINESS_VOCABULARY = tuple(sorted('holdings health labs systems data studio enterprise commercial healthcare services solutions group company corporation limited inc ltd llc gmbh plc'.split()))
# Context words support a phrase, not a language assignment to an isolated brand.
ENGLISH_WORDS = set('''harbor health cedar labs pioneer data orchard systems bluebird studio summit holdings
enterprise commercial healthcare financial services for mexican businesses corporation
aster lantern analytics violet moon workshops crystal river silver morning amber logistics azure
research golden meadow cobalt supply pine comet design unmatched copper kite observatory
north star blue support business international bank of mexico the and technology software global
paper cloud factory products gardens energy trading small community agricultural new'''.split())
# Shared/borrowed words such as data, studio and commercial deliberately provide
# no foreign-language evidence. Accent marks on a proper noun alone are insufficient.
CUES = {
    'fr': set('''les la le des du de aux pour une un et société sociétés banque banques ateliers atelier
        fabrique fabrication nuages bleus lune violette étoiles papier logistique verger ambré
        services santé familles jardins rivière produits agricoles petites entreprises proposons
        toutes veuillez contacter notre équipe obtenir informations française français financiers'''.split()),
    'es': set('''los las el la del de para una un y servicios financieros empresas mexicanas banco
        río cristal investigación puerto azul fábrica nubes azules salud comunitaria compañía
        productos agrícolas jardines sol soluciones pequeñas ofrecemos comerciantes comerciales'''.split()),
    'de': set('''der die das dem den am im für und mit von werkstätten silbernen morgen systeme
        goldenen wiese deutsche deutschen gesellschaft erneuerbare energien technische technischen
        lösungen unternehmen handel landwirtschaftlichen produkten gesundheit entwickeln kleine'''.split()),
}
# Function words count only alongside language-specific vocabulary.
FUNCTION_WORDS = set('les la le des du de aux pour une un et los las el del para y der die das dem den am im für und mit von'.split())


def tokens(text):
    return re.findall(r'[^\W\d_]+', unicodedata.normalize('NFC', text).casefold())


def vocabulary(values=None):
    values = DEFAULT_BUSINESS_VOCABULARY if values is None else values
    return tuple(sorted({word for value in values for word in tokens(value)}))


def field_kind(field, mapping=None, dataset=None):
    label = re.sub(r'[_-]+', ' ', field).casefold()
    if re.search(r'\b(segment|classification|category|tier|industry|status|type|class|sector|vertical|region|market|level|band|grade|rating)\b', label):
        return 'classification'
    if re.search(r'\b(description|summary|overview|biography)\b', label):
        return 'description'
    if re.search(r'\b(id|identifier|code|number|uuid)\b', label) and not re.search(r'\bname\b', label):
        return 'identifier'
    if field == (mapping or {}).get(f'{dataset}_id') or re.search(r'account|company|name|entity|organi[sz]ation|customer|client', label):
        return 'account_name'
    return 'free_text'


@lru_cache(maxsize=20000)
def raw_detection(text):
    try:
        from langdetect import DetectorFactory, detect_langs
        from langdetect.lang_detect_exception import LangDetectException
        DetectorFactory.seed = 0
        try:
            scores = detect_langs(text[:10000])
        except LangDetectException:
            scores = []
        return (scores[0].lang.split('-')[0], round(scores[0].prob, 4)) if scores else ('und', 0.0)
    except ImportError:
        return 'und', 0.0


def detect_text(text, field_kind='free_text', business_vocabulary=None, classification_enabled=False, *, refresh=False):
    arguments = (text, field_kind, vocabulary(business_vocabulary), classification_enabled)
    return dict(_detect.__wrapped__(*arguments, refresh=True) if refresh else _detect(*arguments))


@lru_cache(maxsize=20000)
def _detect(text, kind, business_words, classification_enabled, refresh=False):
    def result(language, confidence, status, outcome, reason, raw='und', raw_confidence=0.0):
        return {'language': language, 'confidence': confidence, 'status': status,
                'detection_outcome': outcome, 'reason': reason, 'detector_language': raw,
                'detector_confidence': raw_confidence}
    if kind == 'identifier' or (kind == 'classification' and not classification_enabled):
        return result('und', 0.0, 'Excluded', EXCLUDED, 'Field excluded from translation; enable classification fields explicitly if needed.')
    if not text.strip() or not any(c.isalpha() for c in text) or re.match(r'^(https?://|www\.|[^\s]+@)', text, re.I):
        return result('und', 0.0, 'Not Required', EXCLUDED, 'Blank or nonlinguistic value.')
    if re.fullmatch(r'[A-Z0-9_./:-]*\d[A-Z0-9_./:-]*', text, re.I) or re.fullmatch(r'[A-Z]{2,6}', text) or re.fullmatch(r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}', text, re.I):
        return result('und', 0.0, 'Not Required', EXCLUDED, 'Identifier or code.')
    words = set(tokens(text))
    scripts = set()
    for c in text:
        if c.isalpha():
            name = unicodedata.name(c, '')
            for script in ('LATIN', 'CYRILLIC', 'ARABIC', 'HANGUL', 'HIRAGANA', 'KATAKANA', 'CJK', 'GREEK', 'HEBREW', 'THAI', 'DEVANAGARI'):
                if script in name:
                    scripts.add(script)
    mixed = len(scripts) > 1 and not scripts <= {'CJK', 'HIRAGANA', 'KATAKANA'}
    language, confidence = raw_detection.__wrapped__(text) if refresh else raw_detection(text)
    def unknown(reason):
        return result('und', 0.0, 'Uncertain', AMBIGUOUS, reason, language, confidence)
    if mixed:
        return unknown('Mixed scripts: confirm the language manually.')
    if scripts and 'LATIN' not in scripts and language not in ('und', 'en') and confidence >= 0.90:
        return result(language, confidence, 'Translation Needed', FOREIGN, 'Non-Latin script and detector agree.', language, confidence)
    neutral = set(DEFAULT_BUSINESS_VOCABULARY) | set(business_words)
    evidence = {code: words & (terms - neutral) for code, terms in CUES.items()}
    supported = [code for code, hits in evidence.items()
                 if len(hits) >= 2 and hits - FUNCTION_WORDS and
                 (hits - FUNCTION_WORDS - set.union(*(CUES[other] for other in CUES if other != code)))]
    # A language-specific phrase must agree with the detector. A high score for a
    # proper name or borrowed English business vocabulary is never enough.
    if language in supported and confidence >= 0.90:
        return result(language, confidence, 'Translation Needed', FOREIGN, 'Detector agrees with multiple language cues.', language, confidence)
    if any(evidence.values()) and any(hits - FUNCTION_WORDS for hits in evidence.values()):
        return unknown('Language evidence is incomplete or conflicting; confirm manually.')
    # At least two known English context words, including a non-business word.
    # Isolated labels/proper nouns and combinations such as Data Studio abstain.
    if len(words) >= 2 and words <= ENGLISH_WORDS and words - neutral:
        return result('en', 0.95, 'Not Required', ENGLISH, 'English phrase/context evidence; business terms alone are insufficient.', language, confidence)
    minimum_words = 5 if kind == 'free_text' else 4
    if kind in ('description', 'free_text') and len(tokens(text)) >= minimum_words and sum(c.isalpha() for c in text) >= 20 and confidence >= 0.95:
        return result(language, confidence, 'Not Required' if language == 'en' else 'Translation Needed',
                      ENGLISH if language == 'en' else FOREIGN, 'Sufficient prose context for language detection.', language, confidence) if language != 'und' else unknown('Language unavailable.')
    return unknown('Short business name, proper noun or insufficient language evidence; confirm manually.')
