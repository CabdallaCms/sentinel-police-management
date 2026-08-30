#!/usr/bin/env python3
"""Sentinel backend foundation.
Development-only API using Python standard library + SQLite.
Replace SQLite and demo authentication before operational deployment.
"""
import hashlib, json, os, secrets, sqlite3, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('SENTINEL_DB', os.path.join(ROOT, 'sentinel.db'))
TOKENS = {}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def init_db():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
      display_name TEXT NOT NULL, role TEXT NOT NULL,
      branch TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS persons(
      id INTEGER PRIMARY KEY, person_id TEXT UNIQUE NOT NULL,
      full_name TEXT NOT NULL, national_id TEXT UNIQUE NOT NULL,
      date_of_birth TEXT, phone TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS airport_passengers(
      id INTEGER PRIMARY KEY, record_id TEXT UNIQUE NOT NULL,
      person_id INTEGER NOT NULL REFERENCES persons(id), movement TEXT NOT NULL,
      travel_date TEXT NOT NULL, flight_number TEXT NOT NULL,
      route TEXT NOT NULL, notes TEXT, created_by INTEGER REFERENCES users(id),
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS clearance_applications(
      id INTEGER PRIMARY KEY, application_id TEXT UNIQUE NOT NULL,
      person_id INTEGER NOT NULL REFERENCES persons(id), purpose TEXT NOT NULL,
      guardian_name TEXT, guardian_relationship TEXT, legal_document_ref TEXT,
      notes TEXT, status TEXT NOT NULL DEFAULT 'Pending Review',
      certificate_number TEXT, created_by INTEGER REFERENCES users(id),
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS audit_events(
      id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
      action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT,
      details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ''')
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        c.execute('INSERT INTO users(username,display_name,role,branch,password_hash) VALUES(?,?,?,?,?)',
                  ('admin','Officer A. Hassan','Administrator','Central HQ', password_hash('ChangeMe123!')))
    if c.execute('SELECT COUNT(*) FROM persons').fetchone()[0] == 0:
        c.execute('INSERT INTO persons(person_id,full_name,national_id,date_of_birth,phone) VALUES(?,?,?,?,?)',
                  ('P-0001','Ayaan Cabdi Xasan','10012345','1997-04-18','+252 63 555 0199'))
        c.execute('INSERT INTO persons(person_id,full_name,national_id,date_of_birth,phone) VALUES(?,?,?,?,?)',
                  ('P-0002','Maxamed Nuur Cali','10067890','1989-11-02','+252 63 555 0188'))
        pid = c.execute("SELECT id FROM persons WHERE person_id='P-0001'").fetchone()[0]
        c.execute('INSERT INTO airport_passengers(record_id,person_id,movement,travel_date,flight_number,route) VALUES(?,?,?,?,?,?)',
                  ('AR-1001',pid,'Arrival','2026-07-18','HL-118','Berbera / Hargeisa'))
    c.commit(); c.close()

def password_hash(value): return hashlib.sha256(value.encode()).hexdigest()
def body(handler):
    try: return json.loads(handler.rfile.read(int(handler.headers.get('Content-Length','0')) or 0) or b'{}')
    except Exception: raise ValueError('Request body must be valid JSON')
def rowdict(row): return dict(row) if row else None

def require_auth(handler):
    token = handler.headers.get('Authorization','').replace('Bearer ','')
    user_id = TOKENS.get(token)
    if not user_id: raise PermissionError('Authentication required')
    c=db(); user=rowdict(c.execute('SELECT id,username,display_name,role,branch FROM users WHERE id=? AND active=1',(user_id,)).fetchone()); c.close()
    return user

def audit(c,user,action,entity,entity_id,details=''):
    c.execute('INSERT INTO audit_events(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',(user['id'],action,entity,entity_id,details))

class API(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print('%s - %s' % (self.address_string(), fmt % args))
    def send_json(self,status,data):
        out=json.dumps(data,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(out))); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.end_headers(); self.wfile.write(out)
    def do_OPTIONS(self): self.send_json(204,{})
    def do_GET(self):
        # Serve the browser application from the backend so the UI can use same-origin API calls.
        p=urlparse(self.path)
        if p.path in ('/','/index.html'):
            try:
                with open(os.path.join(os.path.dirname(ROOT), 'index.html'), 'rb') as f: data=f.read()
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
            except OSError: self.send_json(404, {'error':'Frontend not found'}); return
        try:
            user=require_auth(self); c=db()
            if p.path=='/api/health': result={'status':'ok','service':'sentinel-backend','database':'sqlite-development'}
            elif p.path=='/api/me': result=user
            elif p.path=='/api/persons':
                q=parse_qs(p.query).get('q',[''])[0].strip(); like=f'%{q}%'
                rows=c.execute('SELECT * FROM persons WHERE full_name LIKE ? OR person_id LIKE ? OR national_id LIKE ? OR phone LIKE ? ORDER BY id DESC',(like,like,like,like)).fetchall(); result={'items':[rowdict(r) for r in rows]}
            elif p.path=='/api/airport-records':
                rows=c.execute('''SELECT a.record_id,a.movement,a.travel_date,a.flight_number,a.route,a.notes,p.person_id,p.full_name,p.national_id FROM airport_passengers a JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall(); result={'items':[rowdict(r) for r in rows]}
            elif p.path=='/api/clearance-applications':
                rows=c.execute('''SELECT a.*,p.person_id,p.full_name,p.national_id FROM clearance_applications a JOIN persons p ON p.id=a.person_id ORDER BY a.id DESC''').fetchall(); result={'items':[rowdict(r) for r in rows]}
            else: self.send_json(404,{'error':'Not found'}); return
            c.close(); self.send_json(200,result)
        except PermissionError as e: self.send_json(401,{'error':str(e)})
        except Exception as e: self.send_json(500,{'error':str(e)})
    def do_POST(self):
        try:
            p=urlparse(self.path)
            if p.path=='/api/login':
                data=body(self); c=db(); u=c.execute('SELECT * FROM users WHERE username=? AND password_hash=? AND active=1',(data.get('username'),password_hash(data.get('password','')))).fetchone(); c.close()
                if not u: self.send_json(401,{'error':'Invalid username or password'}); return
                token=secrets.token_urlsafe(32); TOKENS[token]=u['id']; self.send_json(200,{'token':token,'user':{'id':u['id'],'username':u['username'],'display_name':u['display_name'],'role':u['role'],'branch':u['branch']}}); return
            user=require_auth(self); data=body(self); c=db()
            if p.path=='/api/persons':
                for key in ('full_name','national_id'):
                    if not data.get(key): raise ValueError(f'{key} is required')
                existing=c.execute('SELECT * FROM persons WHERE national_id=?',(data['national_id'],)).fetchone()
                if existing: self.send_json(409,{'error':'A person with this National ID already exists','person':rowdict(existing)}); c.close(); return
                person_id='P-'+str(int(time.time()*1000))[-8:]
                c.execute('INSERT INTO persons(person_id,full_name,national_id,date_of_birth,phone) VALUES(?,?,?,?,?)',(person_id,data['full_name'],data['national_id'],data.get('date_of_birth',''),data.get('phone',''))); audit(c,user,'CREATE','person',person_id); c.commit(); result={'person':rowdict(c.execute('SELECT * FROM persons WHERE person_id=?',(person_id,)).fetchone())}
            elif p.path=='/api/airport-records':
                pid=c.execute('SELECT id FROM persons WHERE person_id=?',(data.get('person_id'),)).fetchone();
                if not pid: raise ValueError('person_id must refer to a central person')
                rid='AR-'+str(int(time.time()*1000))[-8:]; c.execute('INSERT INTO airport_passengers(record_id,person_id,movement,travel_date,flight_number,route,notes,created_by) VALUES(?,?,?,?,?,?,?,?)',(rid,pid['id'],data['movement'],data['travel_date'],data['flight_number'],data['route'],data.get('notes',''),user['id'])); audit(c,user,'CREATE','airport_record',rid); c.commit(); result={'record_id':rid}
            elif p.path=='/api/clearance-applications':
                pid=c.execute('SELECT id FROM persons WHERE person_id=?',(data.get('person_id'),)).fetchone();
                if not pid: raise ValueError('person_id must refer to a central person')
                aid='FP-'+str(int(time.time()*1000))[-8:]; c.execute('INSERT INTO clearance_applications(application_id,person_id,purpose,guardian_name,guardian_relationship,legal_document_ref,notes,created_by) VALUES(?,?,?,?,?,?,?,?)',(aid,pid['id'],data['purpose'],data.get('guardian_name',''),data.get('guardian_relationship',''),data.get('legal_document_ref',''),data.get('notes',''),user['id'])); audit(c,user,'CREATE','clearance_application',aid); c.commit(); result={'application_id':aid}
            elif p.path.startswith('/api/clearance-applications/') and p.path.endswith('/approve'):
                aid=p.path.split('/')[3]; cert='CL-'+str(int(time.time()*1000))[-8:]; c.execute("UPDATE clearance_applications SET status='Approved',certificate_number=?,reviewed_at=CURRENT_TIMESTAMP WHERE application_id=?",(cert,aid)); audit(c,user,'APPROVE','clearance_application',aid,cert); c.commit(); result={'application_id':aid,'certificate_number':cert,'status':'Approved'}
            else: self.send_json(404,{'error':'Not found'}); c.close(); return
            c.close(); self.send_json(201,result)
        except PermissionError as e: self.send_json(401,{'error':str(e)})
        except ValueError as e: self.send_json(400,{'error':str(e)})
        except sqlite3.IntegrityError as e: self.send_json(409,{'error':'Database constraint failed','details':str(e)})
        except Exception as e: self.send_json(500,{'error':str(e)})

if __name__=='__main__':
    init_db(); port=int(os.environ.get('PORT','8001')); print(f'Sentinel backend listening on 0.0.0.0:{port}'); ThreadingHTTPServer(('0.0.0.0',port),API).serve_forever()
