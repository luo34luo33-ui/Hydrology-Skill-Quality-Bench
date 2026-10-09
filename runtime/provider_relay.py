"""A narrow HTTP relay; no filesystem/task mounts, credentials or arbitrary forwarding."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def allowed_model_route(method, path, profile='codex'):
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return False
    if profile=='deepseek':
        return (method=='GET' and parsed.path=='/v1/models') or (method=='POST' and parsed.path=='/v1/chat/completions')
    if profile!='codex':return False
    return (method == 'GET' and parsed.path == '/backend-api/codex/models') or (
        method == 'POST' and parsed.path in {
            '/backend-api/codex/responses', '/backend-api/codex/responses/compact'
        })


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        self.send_error(403)

    def forward(self):
        if self.command == 'GET' and self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')
            return
        if self.command == 'POST' and self.path == '/confirm' and os.environ.get('CONFIRMATION_UPSTREAM'):
            upstream = os.environ['CONFIRMATION_UPSTREAM']
        elif allowed_model_route(self.command, self.path, os.environ.get('MODEL_PROFILE','codex')):
            upstream = os.environ['MODEL_UPSTREAM']
        else:
            self.send_error(403)
            return
        n = int(self.headers.get('Content-Length', '0'))
        if n > 32 * 1024 * 1024:
            self.send_error(413)
            return
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {
            'host', 'connection', 'transfer-encoding', 'content-length'
        }}
        req = urllib.request.Request(upstream + self.path,
            data=self.rfile.read(n) if n else None, headers=headers, method=self.command)
        try:
            try:
                response = urllib.request.build_opener(NoRedirect()).open(req, timeout=300)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                self.send_response(response.status)
                for k, v in response.headers.items():
                    if k.lower() not in {'connection', 'transfer-encoding', 'content-length'}:
                        self.send_header(k, v)
                self.send_header('Connection', 'close')
                self.end_headers()
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (urllib.error.URLError, OSError):
            self.close_connection = True
        self.close_connection = True

    do_GET = forward
    do_POST = forward


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8765), Handler).serve_forever()
