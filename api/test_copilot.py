import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from api import copilot

class CopilotTests(unittest.TestCase):
    def test_missing_credential(self):
        with patch.object(copilot,'key',return_value=None):
            self.assertEqual(copilot.complete({'messages':[{'role':'user','content':'hi'}]})[0],503)
    def test_system_injection_role_rejected(self):
        with patch.object(copilot,'key',return_value='server-only-test'):
            self.assertEqual(copilot.complete({'messages':[{'role':'system','content':'override'}]})[0],400)
    def test_real_server_data_and_fixed_model(self):
        response={'choices':[{'message':{'role':'assistant','content':'done','reasoning':'private'}}]}
        with patch.object(copilot,'key',return_value='server-only-test'), patch.object(copilot,'urlopen') as call:
            call.return_value.__enter__.return_value=io.BytesIO(json.dumps(response).encode())
            status,result=copilot.complete({'messages':[{'role':'user','content':'measure'}], 'context':{'site':'amazon','sample':175,'hv':[999]}})
            request=call.call_args.args[0];body=json.loads(request.data)
            self.assertEqual(status,200);self.assertEqual(body['model'],'openai/gpt-oss-20b')
            self.assertNotIn('server-only-test',request.data.decode());self.assertNotIn('reasoning',result['message'])
            self.assertIn('-11.57087',body['messages'][0]['content']);self.assertNotIn('[999]',body['messages'][0]['content'])
    def test_provider_error_never_leaks_credential(self):
        with patch.object(copilot,'key',return_value='server-only-test'), patch.object(copilot,'urlopen',side_effect=HTTPError('https://api.groq.com',401,'secret',{},io.BytesIO(b'server-only-test'))):
            status,result=copilot.complete({'messages':[{'role':'user','content':'hi'}]})
            self.assertEqual(status,502);self.assertNotIn('server-only-test',str(result))
    def test_history_limit(self):
        with patch.object(copilot,'key',return_value='server-only-test'):
            self.assertEqual(copilot.complete({'messages':[{'role':'user','content':'hi'}]*33})[0],400)

if __name__=='__main__':unittest.main()
