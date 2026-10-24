"""Bounded company-name equivalences; never rewrite uploaded strings or field values."""
import re
import unicodedata

LEGAL = {'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation',
         'plc', 'co', 'company', 'gmbh', 'sa'}
TERMS = {'pharma': 'pharmaceuticals', 'telecom': 'telecommunications', 'edu': 'education'}
PLURALS = {'studios': 'studio', 'foods': 'food', 'supplies': 'supply',
           'exports': 'export', 'devices': 'device', 'services': 'service'}


def tokens(name, german=False):
    text = unicodedata.normalize('NFKC', str(name or '')).casefold()
    if german:
        for a, b in [('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue')]:
            text = text.replace(a, b)
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return re.findall(r'\w+', text)


def name_keys(name, *, german_variants=True):
    """Ordered increasingly lossy equivalences, with no arbitrary stemming/token deletion."""
    output = []
    for german in ((False, True) if german_variants else (False,)):
        parts = tokens(name, german)
        if not parts:
            continue
        output.append(('Diacritics' if not german else 'German transliteration', ''.join(parts)))
        while len(parts) > 1 and parts[-1] in LEGAL:
            parts.pop()
        output.append(('Legal suffix', ''.join(parts)))
        parts = [TERMS.get(t, t) for t in parts]
        output.append(('Business abbreviation', ''.join(parts)))
        parts = [PLURALS.get(t, t) for t in parts]
        output.append(('Singular/plural', ''.join(parts)))
    return list(dict.fromkeys(output))


def ranking_variant(name):
    """Cyrillic romanization is ranking evidence only, never an accepted translation."""
    text = str(name or '').casefold()
    alphabet = dict(zip('абвгдеёзийклмнопрстуфхыэ',
                        ['a','b','v','g','d','e','e','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','y','e']))
    alphabet.update({'ж':'zh', 'ц':'ts', 'ч':'ch', 'ш':'sh', 'щ':'shch', 'ъ':'', 'ь':'', 'ю':'yu', 'я':'ya'})
    if not any(c in alphabet for c in text):
        return ''
    parts = re.findall(r'\w+', text)
    if parts and parts[0] == 'ооо':
        parts = parts[1:]
    return ' '.join(''.join(alphabet.get(c, c) for c in word) for word in parts)


def equivalence_method(left, right):
    """Report transformations needed on either side, rather than only the query."""
    order = ['Diacritics', 'Legal suffix', 'Business abbreviation', 'Singular/plural', 'German transliteration']
    shared = [max(order.index(a), order.index(b)) for a, x in name_keys(left, german_variants=False)
              for b, y in name_keys(right, german_variants=False) if x == y]
    if shared:
        return order[min(shared)]
    return 'German transliteration' if {k for _, k in name_keys(left)} & {k for _, k in name_keys(right)} else ''
