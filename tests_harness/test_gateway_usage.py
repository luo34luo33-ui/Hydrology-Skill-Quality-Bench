import http.client
import json
import urllib.request

from harness.provider_gateway import ProviderGateway


def test_gateway_accounts_stream_usage_without_persisting_content(tmp_path,monkeypatch):
    monkeypatch.setattr('harness.secret_store.read_secret',lambda _:'private-credential')
    class Response:
        status=200
        headers={'Content-Type':'text/event-stream'}
        def __enter__(self):
            self.parts=iter([
                b'data: {"choices":[{"delta":{"content":"private-response"}}]}\n\n',
                b'data: {"choices":[],"usage":{"prompt_tokens":100,"completion_tokens":20,"prompt_cache_hit_tokens":80}}\n\n',
                b'data: [DONE]\n\n'])
            return self
        def __exit__(self,*args):pass
        def read1(self,n):return next(self.parts,b'')
    class Opener:
        def open(self,request,timeout):return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
    audit=tmp_path/'audit.jsonl'
    gateway=ProviderGateway('qwen',{'model':'deepseek-flash','credential_store':'unused'},audit,lambda _:None,1)
    port=gateway.start()
    try:
        client=http.client.HTTPConnection('127.0.0.1',port)
        client.request('POST','/v1/chat/completions',json.dumps({'model':'deepseek-flash','messages':[{'content':'private-prompt'}]}))
        response=client.getresponse();assert response.status==200;response.read();client.close()
    finally:gateway.close()
    usage=[e['token_usage'] for e in gateway.events if e.get('kind')=='model_usage']
    assert len(usage)==1
    assert usage[0]['total_tokens']==120
    assert usage[0]['measurement']=='reported'
    assert usage[0]['cached_input_tokens']==80
    text=audit.read_text()
    assert all(secret not in text for secret in ['private-credential','private-response','private-prompt'])
