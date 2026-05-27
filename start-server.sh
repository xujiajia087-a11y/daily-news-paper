#!/bin/bash
cd /Users/xujiajia/Documents/skill/daily-news-paper/site
echo "=== JiaJia Daily Server ==="
echo "URL: http://127.0.0.1:8080"
echo ""
python3 -c "
import http.server, socketserver, os
PORT = 8080
DIR = os.getcwd()
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=DIR, **kw)
with socketserver.TCPServer(('127.0.0.1', PORT), H) as srv:
    print(f'Serving on http://127.0.0.1:{PORT}')
    srv.serve_forever()
"
