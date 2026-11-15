"""Build and validate local interface catalogues without network or model dependencies.
Existing translated entries are retained; missing translations require explicit review.
"""
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LANGUAGES={'ru':'Russian','fr':'French','de':'German','it':'Italian','es':'Spanish','pt':'Portuguese','ja':'Japanese','ar':'Arabic'}
NUM=re.compile(r'\d{4}-\d{2}-\d{2}|[-+]?\d+(?:[.,]\d+)?')
PUNCT={'\u2013':'-','\u2014':'-','\u2212':'-','\u00b7':',','\u2264':'<=','\u2265':'>=','\u00b1':'+/-','\u00d7':'x','\u00b2':'2','\u2026':'...','\u00a9':'(c)','\u00b0':' deg','\u00b5':'u','\u03c3':'sd','\u0394':'d','\u2192':'->','\u2190':'<-','\u2248':'~','\u2032':"'",'\u2033':'"','\u00ab':'"','\u00bb':'"','\u25b6':'>','\u25a0':''}
def canonical(text):
    text=re.sub(r'[\s\u00a0]*\u00b7[\s\u00a0]*',', ',text.strip())
    return ''.join(PUNCT.get(c,c) for c in text)
def template(text):
    text=canonical(text)
    n=iter(range(1000));return NUM.sub(lambda m:'{'+str(next(n))+'}',text)
def build(code):
    source=json.loads((ROOT/'locales/en.json').read_text());path=ROOT/f'locales/{code}.json'
    done=json.loads(path.read_text()) if path.exists() else {}
    missing=[k for k in source if k not in done]
    if missing: raise ValueError(f'{code}: {len(missing)} translations missing; add reviewed translations to the local catalogue before building')
    overrides=json.loads((ROOT/'locales/reviewed-overrides.json').read_text())
    for source_text,translations in overrides.items():
        identifier=next((k for k,v in source.items() if v==source_text),None)
        if identifier and code in translations: done[identifier]=translations[code]
    done={k:done[k] for k in source}
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(done,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)
    return code
if __name__=='__main__':
    pairs=json.loads((ROOT/'locales/source-pairs.json').read_text())
    en={f'k{i}':template(s) for i,s in enumerate(pairs)}
    previous=json.loads((ROOT/'locales/en.json').read_text()) if (ROOT/'locales/en.json').exists() else {}
    changed={k for k in previous if k in en and canonical(previous[k])!=en[k]}
    if changed:
        for code in LANGUAGES:
            path=ROOT/f'locales/{code}.json'
            if path.exists():
                old=json.loads(path.read_text());old={k:v for k,v in old.items() if k not in changed};path.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    ru={}
    for i,(en_text,ru_text) in enumerate(pairs.items()):
        if not ru_text.strip(): continue
        en_text=canonical(en_text);ru_text=canonical(ru_text)
        src=NUM.findall(en_text); used=set(); correct=[True]
        def replace(m):
            choices=[j for j,n in enumerate(src) if j not in used and n==m.group()]
            if not choices: correct[0]=False;return m.group()
            j=choices[0];used.add(j);return '{'+str(j)+'}'
        translated=NUM.sub(replace,ru_text)
        if correct[0] and len(used)==len(src): ru[f'k{i}']=translated
    old_ru=json.loads((ROOT/'locales/ru.json').read_text()) if (ROOT/'locales/ru.json').exists() else {}
    for k,v in old_ru.items():
        if k not in ru and k in en and sorted(re.findall(r'\{\d+\}',v))==sorted(re.findall(r'\{\d+\}',en[k])): ru[k]=v
    for code,data in [('en',en),('ru',ru)]: (ROOT/f'locales/{code}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    for code in LANGUAGES: build(code)
