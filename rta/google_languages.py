"""Offline snapshot of Google general/nmt support, checked 2026-10-22.

Source: https://docs.cloud.google.com/translate/docs/languages#nmt
No API calls are needed to validate a response. Unlisted codes require review;
update this snapshot when Google adds NMT languages. Preserve supported variants.
"""
import hashlib
from pathlib import Path

LOADED_BUILD = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

SUPPORTED_LANGUAGES = frozenset('''
ab ace ach af sq alz am ar hy as awa ay az ban bm ba eu btx bts bbc be bem bn
bew bho bik bs br bg bua yue ca ceb ny zh zh-cn zh-tw cv co crh hr cs da din
dv doi dov nl dz en eo et ee fj fil tl fi fr fr-fr fr-ca fy ff gaa gl lg ka de
el gn gu ht cnh ha haw iw he hil hi hmn hu hrx is ig ilo id ga it ja jw jv kn
pam kk km cgg rw ktu gom ko kri ku ckb ky lo ltg la lv lij li ln lt lmo luo lb
mk mai mak mg ms ms-arab ml mt mi mr chm mni-mtei min lus mn my nr new ne nso
no nus oc or om pag pap ps fa pl pt pt-pt pt-br pa pa-arab qu rom ro rn ru sm
sg sa gd sr st crs shn sn scn szl sd si sk sl so es su sw ss sv tg ta tt te tet
th ti ts tn tr tk ak uk ur ug uz vi cy xh yi yo yua zu
'''.split())


def supported_language(code):
    if not isinstance(code, str) or code.lower() not in SUPPORTED_LANGUAGES:
        return None
    value = code.lower()
    if value == 'zh-cn':
        return 'zh'  # Google documents these as equivalent simplified Chinese.
    if '-' in value:
        base, suffix = value.split('-', 1)
        return base + '-' + (suffix.title() if len(suffix) == 4 else suffix.upper())
    return value
