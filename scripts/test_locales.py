"""Catalogue integrity: language coverage and scientific numeric placeholders."""
import json
import re
import unittest
from pathlib import Path
from scripts.build_locales import template
ROOT=Path(__file__).resolve().parents[1]
CODES=('en','ru','fr','de','it','es','pt','ja','ar')

class LocalesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogues={c:json.loads((ROOT/f'locales/{c}.json').read_text()) for c in CODES}
    def test_all_languages_have_every_key(self):
        en=self.catalogues['en']
        for code,d in self.catalogues.items():
            self.assertEqual(set(d),set(en),code)
            self.assertTrue(all(isinstance(v,str) and v.strip() for v in d.values()),code)
    def test_numeric_placeholders_are_never_lost_or_added(self):
        for code,d in self.catalogues.items():
            for k,v in d.items():
                self.assertEqual(sorted(re.findall(r'\{\d+\}',v)),sorted(re.findall(r'\{\d+\}',self.catalogues['en'][k])),f'{code}:{k}')
    def test_source_ids_are_stable(self):
        sources=json.loads((ROOT/'locales/source-pairs.json').read_text())
        self.assertEqual({f'k{i}':template(s) for i,s in enumerate(sources)},self.catalogues['en'])
    def test_reviewed_navigation_is_retained(self):
        overrides=json.loads((ROOT/'locales/reviewed-overrides.json').read_text())
        reverse={v:k for k,v in self.catalogues['en'].items()}
        for source,values in overrides.items():
            for code,text in values.items():self.assertEqual(self.catalogues[code][reverse[source]],text)
    def test_native_script_catalogues_are_not_english_fallbacks(self):
        for code,pattern in [('ja',r'[\u3040-\u30ff\u4e00-\u9fff]'),('ar',r'[\u0600-\u06ff]')]:
            d=self.catalogues[code];self.assertGreater(sum(bool(re.search(pattern,v)) for v in d.values())/len(d),.65,code)
    def test_negative_values_are_placeholder_values_not_duplicate_signs(self):
        text=template('Joint HH/HV \u2264 \u22123 dB flag')
        self.assertEqual(text,'Joint HH/HV <= {0} dB flag')
    def test_chat_model_is_not_changed_by_offline_translation(self):
        from api.copilot import MODEL
        self.assertEqual(MODEL,'openai/gpt-oss-20b')

if __name__=='__main__':unittest.main()
