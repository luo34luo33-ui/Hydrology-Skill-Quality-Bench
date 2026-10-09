import http.client
import json
from pathlib import Path
import urllib.request
import pytest
from harness.provider_gateway import ProviderGateway
from harness.isolated_runtime import candidate_argv

class Response:
    status=200
    headers={}
    def __enter__(self):self.done=False;return self
    def __exit__(self,*args):pass
    def read1(self,n):
        if self.done:return b''
        self.done=True;return b'ok'

def test_gateway_freezes_model_and_budget_without_secret_logs(tmp_path,monkeypatch):
    monkeypatch.setattr('harness.secret_store.read_secret',lambda _: 'fake-private-auth')
    sent=[]
    class Opener:
        def open(self,request,timeout):sent.append(request);return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    gateway=ProviderGateway('opencode',{'model':'deepseek/deepseek-flash','effort':'high','credential_store':'unused'},tmp_path/'audit',lambda _:None,1)
    port=gateway.start()
    def post(model):
        client=http.client.HTTPConnection('127.0.0.1',port)
        client.request('POST','/v1/chat/completions',json.dumps({'model':model,'messages':[]}))
        response=client.getresponse();status=response.status;response.read();client.close();return status
    try:
        assert post('other-model')==403
        assert post('deepseek-flash')==200
        assert post('deepseek-flash')==429
        assert gateway.decision_requests==1 and gateway.budget_denied
        assert sent[0].full_url=='https://api.deepseek.com/v1/chat/completions'
        assert json.loads(sent[0].data)['reasoning_effort']=='high'
        assert 'fake-private-auth' not in (tmp_path/'audit').read_text()
    finally:gateway.close()

def test_candidate_never_mounts_host_secret_or_host_gateway(tmp_path):
    lock={'clis':{'qwen':{'model':'deepseek-v4-pro','effort':'provider-default','credential_store':'HOST_SECRET'}},'skills_dir':str(tmp_path/'skills'),'image_digest':'sha256:test'}
    plain=candidate_argv(lock,'qwen','no-skills',tmp_path/'work',tmp_path/'public',tmp_path/'config','internal','candidate','session-token','same prompt')
    skilled=candidate_argv(lock,'qwen','with-skills',tmp_path/'work',tmp_path/'public',tmp_path/'config','internal','candidate','session-token','same prompt')
    assert 'HOST_SECRET' not in str(plain) and '--add-host' not in plain
    assert '/home/agent/.agents/skills' not in str(plain)
    assert '/home/agent/.agents/skills' in str(skilled)

def test_dpapi_roundtrip(tmp_path):
    import os
    if os.name!='nt':pytest.skip('Windows only')
    from harness.secret_store import transform,read_secret
    path=tmp_path/'encrypted';path.write_bytes(transform(b'fake-private-auth',True))
    assert b'fake-private-auth' not in path.read_bytes()
    assert read_secret(path)=='fake-private-auth'
