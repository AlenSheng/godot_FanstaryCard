"""Loopback-only HTTP fixture for the Godot network boundary; no database or production access."""
import json, time, hashlib, base64
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from collections import Counter
SCHEMA = json.loads((Path(__file__).parents[1] / 'data/http_schema.json').read_text(encoding='utf-8-sig'))['messages']
counts = Counter()
attempts = []
websocket_safe = False

def varint(v):
    v &= (1 << 64) - 1
    out = bytearray()
    while v > 127:
        out.append((v & 127) | 128); v >>= 7
    out.append(v)
    return bytes(out)

def encode(message, data):
    out = b''
    for tag, f in SCHEMA[message].items():
        if f['name'] not in data or data[f['name']] is None: continue
        values = data[f['name']] if f['repeated'] else [data[f['name']]]
        for value in values:
            if f['type'] in ('int32','int64','uint32','bool'):
                out += varint(int(tag) << 3) + varint(value)
            else:
                body = value.encode() if f['type'] == 'string' else encode(f['type'], value)
                out += varint((int(tag)<<3)|2) + varint(len(body)) + body
    return out

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def send(self, code, message=None, data=None, raw=None, media='application/protobuf', extra=None):
        body = raw if raw is not None else encode(message, data) if message else b''
        self.send_response(code)
        self.send_header('Content-Type', media)
        self.send_header('Content-Length',str(len(body)))
        for k,v in (extra or {}).items(): self.send_header(k,str(v))
        self.end_headers()
        try: self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError): pass
    def do_GET(self):
        global websocket_safe
        uri = urlsplit(self.path); q=parse_qs(uri.query); path=uri.path.rstrip('/')
        counts[self.path] += 1
        if path == '/api/v1/client-info':
            self.send(200, raw=json.dumps({'counts':counts,'retryStable':len(attempts)==2 and attempts[0]==attempts[1], 'websocketSafe':websocket_safe}).encode(),media='application/json'); return
        if path == '/ws/v1/session':
            websocket_safe = q.get('ticket') == ['fixture-ticket'] and 'access_token' not in q
            key = self.headers['Sec-WebSocket-Key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
            self.send_response(101)
            self.send_header('Upgrade','websocket')
            self.send_header('Connection','Upgrade')
            self.send_header('Sec-WebSocket-Accept',base64.b64encode(hashlib.sha1(key.encode()).digest()).decode())
            self.end_headers()
            time.sleep(.1)
            self.wfile.write(b'\x88\x02\x03\xe8')
            self.close_connection = True
            return
        if path == '/api/v1/players/me':
            if 'flight' in q:
                version = counts[self.path]
                time.sleep(.3)
                self.send(200,'PlayerProfileResponse',{'user_id':'fixture-user','display_name':'fixture','version':version}); return
            if 'late' in q:
                time.sleep(.4); self.send(401,'HttpError',{'status':401,'detail':'expired'}); return
            self.send(200,'PlayerProfileResponse',{'user_id':'fixture-user','display_name':'fixture','version':9223372036854775807}); return
        if path == '/api/v1/bootstrap':
            self.send(200,'BootstrapResponse',{'player':{'user_id':'fixture-user'},'wallet':{'gold':9223372036854775807},'market':[{'listing_id':'first'}],'mail':{'items':[{'id':'first'}],'unread_count':3}},extra={'X-Market-Next-Offset':1,'X-Mail-Next-Offset':1}); return
        if path == '/api/v1/market':
            offset=int(q.get('offset',['0'])[0]); extra={'X-Market-Next-Offset':1} if offset==0 else {}
            if 'loop' in q: extra={'X-Market-Next-Offset':-1}
            items = [{'listing_id':'first' if offset==0 else 'second'}]
            if 'many' in q: items = [{'listing_id':str(i)} for i in range(4096)]
            self.send(200,'MarketListResponse',{'items':items},extra=extra); return
        if path == '/api/v1/mail':
            self.send(200,'MailListResponse',{'items':[{'id':'second'}],'unread_count':3}); return
        if path == '/api/v1/cards':
            if 'large' in q:
                self.send(200,'CardListResponse',{'items':[{'card_id':'card-'+str(i),'current_effect':{'draw_charge':'1.25'}} for i in range(4096)]}); return
            self.send(200,raw=b'<html>bad proxy</html>',media='text/html'); return
        self.send(404,'HttpError',{'status':404})
    def do_POST(self):
        uri=urlsplit(self.path); path=uri.path; counts[self.path]+=1
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        assert self.headers.get('Content-Type') == 'application/protobuf'
        assert self.headers.get('Accept') == 'application/protobuf'
        if path == '/api/v1/auth/local':
            assert b'fixture' in body
            self.send(200,'LocalSignInResponse',{'access_token':'fixture-bearer','expires_at':'2099-01-01T00:00:00Z','player':{'user_id':'fixture-user'}}); return
        if path == '/api/v1/realtime/ticket':
            assert self.headers.get('Authorization') == 'Bearer fixture-bearer'
            self.send(200,'RealtimeTicketResponse',{'ticket':'fixture-ticket','expires_at':'2099-01-01T00:00:00Z'}); return
        if path == '/api/v1/shop/purchases':
            if uri.query == 'malformed=1': self.send(200,raw=b'\x00'); return
            attempts.append((body,self.headers.get('Idempotency-Key')))
            if len(attempts)==1: self.send(429,'HttpError',{'status':429,'detail':'slow','retry_after_seconds':1},extra={'Retry-After':1}); return
            self.send(200,'ShopPurchaseResponse',{'product_id':'p','gold_after':9223372036854775807}); return
        if path == '/api/v1/mail/read-all': self.send(204); return
        self.send(404,'HttpError',{'status':404})

if __name__ == '__main__':
    print('Loopback protobuf fixture ready on 127.0.0.1:38971',flush=True)
    ThreadingHTTPServer(('127.0.0.1',38971),Handler).serve_forever()
