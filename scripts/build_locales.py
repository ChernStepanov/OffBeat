"""Generate checked-in interface catalogues using configured Groq, never at page load.
Resume keeps completed batches. Numeric placeholders and source identifiers are protected.
"""
import concurrent.futures
import json
import os
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from api.copilot import key
MODEL=os.environ.get("OFFBEAT_TRANSLATION_MODEL", "openai/gpt-oss-120b")
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
    pending=[(k,v) for k,v in source.items() if k not in done]
    for pos in range(0,len(pending),30):
        batch=dict(pending[pos:pos+30])
        prompt=f'''Translate this Earth-observation interface into {LANGUAGES[code]}. Return ONLY a JSON object with exactly the same keys. Preserve every {{number}} placeholder exactly (reordering allowed). Preserve NASA, NISAR, SAR, HH, HV, GUNW, GNSS, OPERA, Sentinel-1, Sentinel-2, WorldCover, ERA5, source IDs, URLs and physical units. Use precise scientific terminology and natural concise UI wording. Never strengthen uncertainty: candidate is not confirmed event, relative LOS is not vertical displacement or subsidence velocity. Retain all limitations and negations. Do not add explanations. All string values must be translated, including short labels.\n'''+json.dumps(batch,ensure_ascii=False)
        for attempt in range(24):
            req=Request('https://api.groq.com/openai/v1/chat/completions',data=json.dumps({'model':MODEL,'messages':[{'role':'user','content':prompt}],'response_format':{'type':'json_object'},'reasoning_effort':'low','max_completion_tokens':4500,'temperature':.1}).encode(),headers={'Authorization':'Bearer '+key(),'Content-Type':'application/json','User-Agent':'OffBeat/1.0'})
            try:
                with urlopen(req,timeout=55) as r: raw=json.load(r)
                result=json.loads(raw['choices'][0]['message']['content'])
                assert set(result)==set(batch),'Missing translation keys'
                for k,v in result.items():
                    assert isinstance(v,str) and v.strip(),'Empty translation'
                    assert sorted(re.findall(r'\{\d+\}',v))==sorted(re.findall(r'\{\d+\}',batch[k])),'Placeholder changed'
                done.update(result);path.write_text(json.dumps(done,ensure_ascii=False,indent=2)+'\n');print(code,len(done),'/',len(source),flush=True);break
            except (HTTPError,TimeoutError,AssertionError,ValueError,KeyError) as e:
                print(code,'retry',attempt+1,type(e).__name__,str(e)[:100] if not isinstance(e,HTTPError) else e.code,flush=True)
                if attempt==23 or isinstance(e,HTTPError) and e.code not in (429,500,502,503,504):raise
                time.sleep(25)
    overrides=json.loads((ROOT/'locales/reviewed-overrides.json').read_text())
    for source_text,translations in overrides.items():
        identifier=next((k for k,v in source.items() if v==source_text),None)
        if identifier and code in translations: done[identifier]=translations[code]
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        list(pool.map(build,LANGUAGES))
