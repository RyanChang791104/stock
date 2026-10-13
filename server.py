#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
High Performance Multithreaded HTTP Server with Gzip & ETag / 304 Support
Taiwan Stock Market Real-Time Application
"""

import os
import sys
import gzip
import time
import socket
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8090

# 支援 Gzip 壓縮的檔案類型
COMPRESSIBLE_EXTS = {'.json', '.js', '.css', '.html', '.svg', '.txt', '.xml'}

class HighSpeedHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def log_message(self, format, *args):
        # 僅在非 200/304 或遇到錯誤時記錄，避免每秒 poll 灌爆終端與 I/O
        if len(args) > 1 and str(args[1]) not in ('200', '304'):
            sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def end_headers(self):
        # 預設支援 CORS 與即時性 Headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self):
        # 移除 URL 參數 (例如 ?t=172888...)
        clean_path = self.path.split('?')[0]
        if clean_path == '/':
            clean_path = '/index.html'

        file_path = os.path.normpath(os.path.join(BASE_DIR, clean_path.lstrip('/')))

        # 安全防護：禁止跨出根目錄
        if not file_path.startswith(BASE_DIR):
            self.send_error(HTTPStatus.FORBIDDEN, "Access denied")
            return

        if not os.path.isfile(file_path):
            super().do_GET()
            return

        try:
            stat = os.stat(file_path)
            file_mtime = int(stat.st_mtime)
            file_size = stat.st_size
            etag = f'"{file_mtime}-{file_size}"'

            # 檢查 If-None-Match，若檔案未更新直接回覆 304 Not Modified
            if_none_match = self.headers.get('If-None-Match')
            if if_none_match and if_none_match.strip() == etag:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                return

            ext = os.path.splitext(file_path)[1].lower()
            accept_encoding = self.headers.get('Accept-Encoding', '')
            use_gzip = ('gzip' in accept_encoding) and (ext in COMPRESSIBLE_EXTS) and (file_size > 256)

            with open(file_path, 'rb') as f:
                content = f.read()

            self.send_response(HTTPStatus.OK)
            self.send_header('ETag', etag)
            self.send_header('Last-Modified', self.date_time_string(file_mtime))

            # 即時資料檔案嚴格禁止硬快取，其他靜態檔案允許短期快取
            if clean_path.endswith('.json'):
                self.send_header('Cache-Control', 'no-cache, must-revalidate')
            else:
                self.send_header('Cache-Control', 'public, max-age=60')

            content_type = self.guess_type(file_path)
            self.send_header('Content-Type', content_type)

            if use_gzip:
                compressed = gzip.compress(content, compresslevel=5)
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(compressed)))
                self.end_headers()
                self.wfile.write(compressed)
            else:
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Error reading file: {e}")

class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def run():
    server_address = ('0.0.0.0', PORT)
    httpd = ReusableThreadingHTTPServer(server_address, HighSpeedHTTPRequestHandler)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚡ 高速多線程 Gzip HTTP 伺服器已啟動: http://0.0.0.0:{PORT}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
