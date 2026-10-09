"""Host-only fixed provider forwarding. Never records credentials or request content."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from runtime.provider_relay import allowed_model_route
from harness.resource_usage import ResponseUsage


class ProviderGateway:
    def __init__(self,cli,cfg,audit,sink,rounds):
        self.cli=cli;self.cfg=cfg;self.audit=Path(audit);self.sink=sink;self.round_limit=rounds
        self.lock=threading.Lock();self.events=[];self.decision_requests=0;self.budget_denied=False
        self.profile='codex' if cli=='codex' else 'deepseek'
        if cli=='codex':
            d=json.loads(Path(cfg['auth_source']).read_text(encoding='utf-8'))['tokens']
            self.headers={'Authorization':'Bearer '+d['access_token'],'ChatGPT-Account-Id':d['account_id']}
        else:
            from harness.secret_store import read_secret
            self.headers={'Authorization':'Bearer '+read_secret(cfg['credential_store'])}

    def record(self,method,path,status,settings=None):
        e={'method':method,'path':urlsplit(path).path,'status':status,'time_ns':time.monotonic_ns()}
        if settings:e['model_controls']=settings
        with self.lock:
            self.events.append(e)
            with self.audit.open('a',encoding='utf-8') as f:f.write(json.dumps(e)+'\n')

    def start(self):
        gateway=self
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_CONNECT(self):self.send_error(403)
            def forward(self):
                if not allowed_model_route(self.command,self.path,gateway.profile):
                    gateway.record(self.command,self.path,403);self.send_error(403);return
                n=int(self.headers.get('Content-Length','0'))
                if not 0<=n<=32*1024*1024:self.send_error(413);return
                body=self.rfile.read(n) if n else None;settings=None;inference=False;identity=None
                if body:
                    try:d=json.loads(body)
                    except ValueError:self.send_error(400);return
                    expected=gateway.cfg['model'].split('/',1)[-1]
                    if d.get('model')!=expected:
                        gateway.record(self.command,self.path,403);self.send_error(403,'Frozen model required');return
                    inference=urlsplit(self.path).path in {'/backend-api/codex/responses','/v1/chat/completions'}
                    if inference:
                        with gateway.lock:
                            if gateway.decision_requests>=gateway.round_limit:
                                gateway.budget_denied=True;self.send_error(429,'Decision budget exhausted');return
                            gateway.decision_requests+=1;identity=gateway.decision_requests
                        gateway.sink({'kind':'model_decision_request','id':str(identity)})
                    if gateway.cli=='opencode':
                        d['reasoning_effort']=gateway.cfg['effort'];d['thinking']={'type':'enabled'}
                    # Qwen keeps its original provider-default settings, recorded explicitly.
                    settings={'model':d.get('model'),'reasoning_effort':d.get('reasoning_effort'),
                        'thinking':d.get('thinking'),'reasoning':d.get('reasoning')}
                    body=json.dumps(d,ensure_ascii=False).encode('utf-8')
                headers={k:v for k,v in self.headers.items() if k.lower() not in
                    {'host','connection','transfer-encoding','content-length','authorization','accept-encoding','upgrade'}}
                headers.update(gateway.headers);headers['Accept-Encoding']='identity'
                origin='https://chatgpt.com' if gateway.cli=='codex' else 'https://api.deepseek.com'
                request=urllib.request.Request(origin+self.path,data=body,headers=headers,method=self.command)
                tracker=None
                try:
                    try:r=urllib.request.build_opener(NoRedirect()).open(request,timeout=120)
                    except urllib.error.HTTPError as error:r=error
                    with r:
                        gateway.record(self.command,self.path,r.status,settings)
                        if inference and r.status==200:tracker=ResponseUsage(body or b'')
                        self.send_response(r.status)
                        for k,v in r.headers.items():
                            if k.lower() not in {'connection','transfer-encoding','content-length','content-encoding'}:self.send_header(k,v)
                        self.send_header('Connection','close');self.end_headers()
                        while chunk:=r.read1(65536):
                            if tracker:tracker.feed(chunk)
                            self.wfile.write(chunk);self.wfile.flush()
                except (urllib.error.URLError,OSError):
                    gateway.record(self.command,self.path,502,settings)
                finally:
                    if tracker:
                        event={'kind':'model_usage','request_id':identity,'time_ns':time.monotonic_ns(),
                            'token_usage':tracker.finish()}
                        with gateway.lock:
                            gateway.events.append(event)
                            with gateway.audit.open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
                self.close_connection=True
            do_GET=forward
            do_POST=forward
        self.server=ThreadingHTTPServer(('0.0.0.0',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        return self.server.server_port

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)


def create_gateway(cli,cfg,audit,sink,rounds):return ProviderGateway(cli,cfg,audit,sink,rounds)
