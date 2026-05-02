#!/usr/bin/env python3
"""Tiny localhost HTTP helper for the Nowify kiosk.

Exposes POST /shutdown on 127.0.0.1:8787. The Nowify frontend calls it
(fire-and-forget, no-cors) when the art-mode idle timeout expires.

Bound to loopback — no auth needed, unreachable from the network.
"""
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = '127.0.0.1'
PORT = 8787


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == '/shutdown':
            self.send_response(200)
            self._cors()
            self.end_headers()
            self.wfile.write(b'shutting down\n')
            try:
                subprocess.Popen(['/sbin/shutdown', '-h', 'now'])
            except FileNotFoundError:
                subprocess.Popen(['shutdown', '-h', 'now'])
        elif self.path == '/reboot':
            self.send_response(200)
            self._cors()
            self.end_headers()
            self.wfile.write(b'rebooting\n')
            try:
                subprocess.Popen(['/sbin/shutdown', '-r', 'now'])
            except FileNotFoundError:
                subprocess.Popen(['shutdown', '-r', 'now'])
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()

    def log_message(self, *_args):
        return


if __name__ == '__main__':
    HTTPServer((HOST, PORT), Handler).serve_forever()
