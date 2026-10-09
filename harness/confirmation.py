"""Host-owned deterministic user-answer broker; no model or hidden-context hints."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time

def normalize(value):
    return str(value).strip().casefold().replace(' ', '').replace('-', '_')


class AuditTrail:
    """Execution-only log. No answer table, credentials or HTTP service."""
    token = None
    def __init__(self, audit_path):
        self.audit_path=Path(audit_path); self.events=[]; self.lock=threading.Lock()
    def record(self, event):
        with self.lock:
            event={**event,'sequence':len(self.events),'time_ns':time.monotonic_ns()}
            self.events.append(event); self.audit_path.parent.mkdir(parents=True,exist_ok=True)
            with self.audit_path.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
        return event

class ConfirmationBroker:
    def __init__(self, reference, audit_path):
        self.reference=reference; self.audit_path=Path(audit_path)
        self.token=secrets.token_urlsafe(32); self.events=[]; self.lock=threading.Lock()
        self.before_answer=None
        self.budget_exhausted=None
        self.aliases={}
        for item in reference.get('confirmations',[]):
            for alias in [item['key'],*item.get('aliases',[])]:
                key=normalize(alias)
                if key in self.aliases and self.aliases[key]['key']!=item['key']:raise ValueError('ambiguous confirmation alias')
                self.aliases[key]=item

    def record(self,event):
        with self.lock:
            event={**event,'sequence':len(self.events),'time_ns':time.monotonic_ns()}
            self.events.append(event); self.audit_path.parent.mkdir(parents=True,exist_ok=True)
            with self.audit_path.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
        return event

    def answer(self,request):
        if self.budget_exhausted and self.budget_exhausted():
            self.record({'kind':'confirmation_rejected_budget'})
            return {'error':'Tool budget exhausted; no confirmation answer supplied.'}
        self.record({'kind':'confirmation_request','request':request})
        response=self._answer(request)
        self.record({'kind':'confirmation_response','response':response})
        return response

    def _answer(self,request):
        if not isinstance(request,dict) or not str(request.get('subject','')).strip() or not str(request.get('question','')).strip():
            return {'error':'Provide subject, a specific question, and fields (a list of field names).'}
        fields=request.get('fields')
        if not isinstance(fields,list) or not fields or len(fields)>20 or not all(isinstance(x,str) for x in fields):
            return {'error':'fields must be a non-empty list of specific field names (maximum 20).'}
        answers=[]
        for field in fields:
            item=self.aliases.get(normalize(field))
            if item and normalize(request['subject']) in {normalize(x) for x in ['data','scenario','场景',item['subject'],*item.get('subject_aliases',[])]}:
                if self.before_answer:self.before_answer(item)
                e=self.record({'kind':'confirmation','key':item['key'],'subject':request['subject'],'question':request['question'],'answer':item['answer']})
                answers.append({'field':field,'answer':item['answer'],'receipt':e['sequence']})
            else:answers.append({'field':field,'error':'Unrecognized subject/field; use canonical subject data or scenario for the supplied inputs and specify a field. No answer supplied.'})
        return {'answers':answers}

    def start(self):
        broker=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.headers.get('Authorization')!='Bearer '+broker.token:self.send_error(403);return
                length=int(self.headers.get('Content-Length','0'))
                if length<1 or length>65536:self.send_error(400);return
                try:request=json.loads(self.rfile.read(length))
                except (ValueError,UnicodeDecodeError):self.send_error(400);return
                if self.path!='/confirm':self.send_error(404);return
                payload=json.dumps(broker.answer(request),ensure_ascii=False).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        self.server=ThreadingHTTPServer(('0.0.0.0',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        return self.server.server_port

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)

