import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class CompanionHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_len)
        try:
            data = json.loads(post_data)
        except:
            self.send_response(400)
            self.end_headers()
            return
        if self.server.callback:
            self.server.callback(data)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format, *args):
        pass  # 屏蔽日志

class CompanionServer:
    def __init__(self, callback):
        self.callback = callback
        self.server = None
        self.thread = None

    def start(self):
        if self.server:
            return
        self.server = HTTPServer(('127.0.0.1', 10045), CompanionHandler)
        self.server.callback = self.callback
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server = None
            self.thread = None