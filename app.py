"""
CMI-ESUCAR 2025-2028 · Backend Flask + PostgreSQL
"""
import os, uuid, json, base64
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory, redirect, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cmi-esucar-2025")
DATABASE_URL   = os.environ.get("DATABASE_URL", "")
ALLOWED_EXT    = {"pdf","docx","doc","xlsx","xls","pptx","png","jpg","jpeg","zip","txt"}

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL, password TEXT NOT NULL,
                rol TEXT NOT NULL, eje_ids TEXT DEFAULT '[]',
                activo INTEGER DEFAULT 1, creado TEXT DEFAULT (NOW()::text));
            CREATE TABLE IF NOT EXISTS tareas_estado (
                id SERIAL PRIMARY KEY, tarea_key TEXT UNIQUE NOT NULL,
                eje_id TEXT, obj_id TEXT, year INTEGER, mes_idx INTEGER,
                tarea_idx INTEGER, estado TEXT DEFAULT 'pendiente',
                actualizado TEXT DEFAULT (NOW()::text));
            CREATE TABLE IF NOT EXISTS evidencias (
                id SERIAL PRIMARY KEY, tarea_key TEXT, usuario_id INTEGER,
                descripcion TEXT, archivo_orig TEXT DEFAULT '',
                archivo_uuid TEXT DEFAULT '', archivo_data TEXT DEFAULT '',
                archivo_mime TEXT DEFAULT '', enviado_en TEXT DEFAULT (NOW()::text));
            CREATE TABLE IF NOT EXISTS auditoria (
                id SERIAL PRIMARY KEY, tarea_key TEXT, auditor_id INTEGER,
                accion TEXT, observacion TEXT DEFAULT '', fecha TEXT DEFAULT (NOW()::text));
            CREATE TABLE IF NOT EXISTS historial (
                id SERIAL PRIMARY KEY, tarea_key TEXT, usuario_id INTEGER,
                tipo TEXT, detalle TEXT DEFAULT '', fecha TEXT DEFAULT (NOW()::text));
            """)
cur.execute("SELECT id FROM usuarios WHERE username='auditor'")
            if not cur.fetchone():
                cur.executemany(
                    "INSERT INTO usuarios (username,nombre,password,rol,eje_ids) VALUES (%s,%s,%s,%s,%s)",
                    [("auditor","Auditor OAC",generate_password_hash("auditor2025"),"auditor","[]"),
                     ("director","Dirección ESUCAR",generate_password_hash("director2025"),"direccion","[]"),
                     ("resp_e1","Responsable Eje I",generate_password_hash("resp2025"),"responsable",'["E1"]'),
                     ("resp_e2","Responsable Eje II",generate_password_hash("resp2025"),"responsable",'["E2"]'),
                     ("resp_e3","Responsable Eje III",generate_password_hash("resp2025"),"responsable",'["E3"]'),
                     ("resp_e4","Responsable Eje IV",generate_password_hash("resp2025"),"responsable",'["E4"]'),
                     ("resp_e5","Responsable Eje V",generate_password_hash("resp2025"),"responsable",'["E5"]')])
        conn.commit()

try: init_db()
except Exception as e: print(f"DB init: {e}")

def login_required(f):
    @wraps(f)
    def d(*a,**k):
        if "user_id" not in session: return jsonify({"error":"No autenticado"}),401
        return f(*a,**k)
    return d

def rol_required(*roles):
    def dec(f):
        @wraps(f)
        def d(*a,**k):
            if session.get("rol") not in roles: return jsonify({"error":"Sin permisos"}),403
            return f(*a,**k)
        return login_required(d)
    return dec

def current_user():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE id=%s",(session["user_id"],))
            return cur.fetchone()

def allowed_file(fn): return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_EXT
@app.route("/api/login",methods=["POST"])
def login():
    data=request.get_json()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE username=%s AND activo=1",(data.get("username",""),))
            u=cur.fetchone()
    if u and check_password_hash(u["password"],data.get("password","")):
        session.update({"user_id":u["id"],"username":u["username"],"nombre":u["nombre"],"rol":u["rol"],"eje_ids":json.loads(u["eje_ids"])})
        return jsonify({"ok":True,"usuario":{"id":u["id"],"nombre":u["nombre"],"rol":u["rol"],"eje_ids":json.loads(u["eje_ids"])}})
    return jsonify({"ok":False,"error":"Credenciales incorrectas"}),401

@app.route("/api/logout",methods=["POST"])
def logout(): session.clear(); return jsonify({"ok":True})

@app.route("/api/me")
@login_required
def me():
    u=current_user()
    return jsonify({"id":u["id"],"username":u["username"],"nombre":u["nombre"],"rol":u["rol"],"eje_ids":json.loads(u["eje_ids"])})

@app.route("/api/tareas")
@login_required
def get_tareas():
    year=request.args.get("year",2025,type=int)
    u=current_user(); eje_ids=json.loads(u["eje_ids"])
    with get_db() as conn:
        with conn.cursor() as cur:
            if u["rol"]=="responsable" and eje_ids:
                ph=",".join(["%s"]*len(eje_ids))
                cur.execute(f"SELECT * FROM tareas_estado WHERE year=%s AND eje_id IN ({ph})",[year]+eje_ids)
            else:
                cur.execute("SELECT * FROM tareas_estado WHERE year=%s",(year,))
            return jsonify([dict(r) for r in cur.fetchall()])

@app.route("/api/tareas/<path:tarea_key>")
@login_required
def get_tarea(tarea_key):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tareas_estado WHERE tarea_key=%s",(tarea_key,))
            estado=cur.fetchone()
            cur.execute("SELECT e.*,u.nombre AS responsable_nombre FROM evidencias e JOIN usuarios u ON e.usuario_id=u.id WHERE e.tarea_key=%s ORDER BY e.enviado_en DESC",(tarea_key,))
            evs=cur.fetchall()
            cur.execute("SELECT a.*,u.nombre AS auditor_nombre FROM auditoria a JOIN usuarios u ON a.auditor_id=u.id WHERE a.tarea_key=%s ORDER BY a.fecha DESC",(tarea_key,))
            auds=cur.fetchall()
            cur.execute("SELECT h.*,u.nombre AS usr_nombre FROM historial h LEFT JOIN usuarios u ON h.usuario_id=u.id WHERE h.tarea_key=%s ORDER BY h.fecha DESC LIMIT 20",(tarea_key,))
            hist=cur.fetchall()
    return jsonify({"estado":dict(estado) if estado else None,"evidencias":[dict(e) for e in evs],"auditorias":[dict(a) for a in auds],"historial":[dict(h) for h in hist]})
@app.route("/api/evidencia",methods=["POST"])
@rol_required("responsable","auditor")
def subir_evidencia():
    tk=request.form.get("tarea_key",""); desc=request.form.get("descripcion","").strip()
    eje=request.form.get("eje_id",""); obj=request.form.get("obj_id","")
    year=int(request.form.get("year",2025)); mes=int(request.form.get("mes_idx",0)); tidx=int(request.form.get("tarea_idx",0))
    u=current_user()
    if u["rol"]=="responsable":
        ei=json.loads(u["eje_ids"])
        if ei and eje not in ei: return jsonify({"error":"Sin permisos"}),403
    if not desc: return jsonify({"error":"Descripcion obligatoria"}),400
    ao=au=ad=am=""
    if "archivo" in request.files:
        f=request.files["archivo"]
        if f and f.filename and allowed_file(f.filename):
            ao=secure_filename(f.filename); au=str(uuid.uuid4())
            am=f.content_type or ""; ad=base64.b64encode(f.read()).decode()
    now=datetime.now().isoformat(sep=" ",timespec="seconds")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO evidencias (tarea_key,usuario_id,descripcion,archivo_orig,archivo_uuid,archivo_data,archivo_mime,enviado_en) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(tk,u["id"],desc,ao,au,ad,am,now))
            cur.execute("SELECT id FROM tareas_estado WHERE tarea_key=%s",(tk,))
            if cur.fetchone(): cur.execute("UPDATE tareas_estado SET estado='enviada',actualizado=%s WHERE tarea_key=%s",(now,tk))
            else: cur.execute("INSERT INTO tareas_estado (tarea_key,eje_id,obj_id,year,mes_idx,tarea_idx,estado,actualizado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(tk,eje,obj,year,mes,tidx,"enviada",now))
            cur.execute("INSERT INTO historial (tarea_key,usuario_id,tipo,detalle,fecha) VALUES (%s,%s,%s,%s,%s)",(tk,u["id"],"enviada",f"Evidencia de {u['nombre']}. Archivo:{ao or 'ninguno'}",now))
        conn.commit()
    return jsonify({"ok":True,"estado":"enviada"})

@app.route("/api/archivo/<archivo_uuid>")
@login_required
def descargar_archivo(archivo_uuid):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM evidencias WHERE archivo_uuid=%s",(archivo_uuid,))
            ev=cur.fetchone()
    if not ev or not ev["archivo_data"]: return jsonify({"error":"No encontrado"}),404
    return Response(base64.b64decode(ev["archivo_data"]),mimetype=ev["archivo_mime"] or "application/octet-stream",
                    headers={"Content-Disposition":f'attachment; filename="{ev["archivo_orig"]}"'})

@app.route("/api/auditoria",methods=["POST"])
@rol_required("auditor")
def registrar_auditoria():
    data=request.get_json(); tk=data.get("tarea_key",""); accion=data.get("accion",""); obs=data.get("observacion","").strip()
    u=current_user()
    if accion not in ("validada","rechazada"): return jsonify({"error":"Accion invalida"}),400
    if accion=="rechazada" and not obs: return jsonify({"error":"Indique motivo del rechazo"}),400
    now=datetime.now().isoformat(sep=" ",timespec="seconds")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO auditoria (tarea_key,auditor_id,accion,observacion,fecha) VALUES (%s,%s,%s,%s,%s)",(tk,u["id"],accion,obs,now))
            cur.execute("UPDATE tareas_estado SET estado=%s,actualizado=%s WHERE tarea_key=%s",(accion,now,tk))
            cur.execute("INSERT INTO historial (tarea_key,usuario_id,tipo,detalle,fecha) VALUES (%s,%s,%s,%s,%s)",(tk,u["id"],accion,f"Auditor {u['nombre']}: {obs or 'Sin obs.'}",now))
        conn.commit()
    return jsonify({"ok":True,"estado":accion})
@app.route("/api/dashboard")
@login_required
def dashboard():
    year=request.args.get("year",2025,type=int)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT estado,COUNT(*) as total FROM tareas_estado WHERE year=%s GROUP BY estado",(year,))
            resumen=cur.fetchall()
            cur.execute("SELECT eje_id,COUNT(*) as total,SUM(CASE WHEN estado='validada' THEN 1 ELSE 0 END) as validadas,SUM(CASE WHEN estado='enviada' THEN 1 ELSE 0 END) as enviadas,SUM(CASE WHEN estado='rechazada' THEN 1 ELSE 0 END) as rechazadas FROM tareas_estado WHERE year=%s GROUP BY eje_id",(year,))
            por_eje=cur.fetchall()
            cur.execute("SELECT t.*,u.nombre AS resp_nombre,e.descripcion,e.archivo_orig,e.archivo_uuid,e.enviado_en FROM tareas_estado t JOIN evidencias e ON t.tarea_key=e.tarea_key JOIN usuarios u ON e.usuario_id=u.id WHERE t.estado='enviada' AND t.year=%s ORDER BY e.enviado_en ASC",(year,))
            pend=cur.fetchall()
    return jsonify({"resumen":[dict(r) for r in resumen],"por_eje":[dict(r) for r in por_eje],"pendientes_auditoria":[dict(r) for r in pend]})

@app.route("/api/usuarios",methods=["GET"])
@rol_required("auditor","direccion")
def listar_usuarios():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,username,nombre,rol,eje_ids,activo,creado FROM usuarios")
            return jsonify([dict(u) for u in cur.fetchall()])

@app.route("/api/usuarios",methods=["POST"])
@rol_required("auditor")
def crear_usuario():
    data=request.get_json()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO usuarios (username,nombre,password,rol,eje_ids) VALUES (%s,%s,%s,%s,%s)",
                            (data["username"],data["nombre"],generate_password_hash(data["password"]),data["rol"],json.dumps(data.get("eje_ids",[]))))
            conn.commit()
        return jsonify({"ok":True})
    except: return jsonify({"error":"Usuario ya existe"}),409

@app.route("/api/usuarios/<int:uid>/password",methods=["PUT"])
@rol_required("auditor")
def cambiar_password(uid):
    nueva=request.get_json().get("password","")
    if len(nueva)<6: return jsonify({"error":"Minimo 6 caracteres"}),400
    with get_db() as conn:
        with conn.cursor() as cur: cur.execute("UPDATE usuarios SET password=%s WHERE id=%s",(generate_password_hash(nueva),uid))
        conn.commit()
    return jsonify({"ok":True})

@app.route("/")
def index():
    if "user_id" not in session: return redirect("/login")
    return send_from_directory("static","index.html")

@app.route("/login")
def login_page(): return send_from_directory("static","login.html")

@app.route("/static/<path:path>")
def serve_static(path): return send_from_directory("static",path)

@app.route("/health")
def health(): return jsonify({"status":"ok","app":"CMI-ESUCAR","version":"2.0"})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)