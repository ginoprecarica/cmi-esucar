"""
CMI-ESUCAR 2025-2028 · Backend Flask
=====================================
Roles:
  - responsable : sube evidencias por tarea
  - auditor     : valida / rechaza evidencias (Of. Aseg. Calidad)
  - direccion   : solo lectura / dashboard
"""

import os, sqlite3, uuid, json
from datetime import datetime
from functools import wraps
from flask import (Flask, request, jsonify, session,
                   send_from_directory, render_template_string, redirect, url_for)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ── Configuración ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cmi-esucar-2025-cambiar-en-produccion")

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "cmi_esucar.db")
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
MAX_MB      = 20
ALLOWED_EXT = {"pdf","docx","doc","xlsx","xls","pptx","png","jpg","jpeg","zip","txt"}

os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Base de datos ──────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            nombre   TEXT    NOT NULL,
            password TEXT    NOT NULL,
            rol      TEXT    NOT NULL CHECK(rol IN ('responsable','auditor','direccion')),
            eje_ids  TEXT    DEFAULT '[]',
            activo   INTEGER DEFAULT 1,
            creado   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tareas_estado (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tarea_key   TEXT    UNIQUE NOT NULL,
            eje_id      TEXT    NOT NULL,
            obj_id      TEXT    NOT NULL,
            year        INTEGER NOT NULL,
            mes_idx     INTEGER NOT NULL,
            tarea_idx   INTEGER NOT NULL,
            estado      TEXT    NOT NULL DEFAULT 'pendiente',
            actualizado TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS evidencias (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tarea_key    TEXT    NOT NULL,
            usuario_id   INTEGER NOT NULL,
            descripcion  TEXT    NOT NULL,
            archivo_orig TEXT    DEFAULT '',
            archivo_uuid TEXT    DEFAULT '',
            archivo_mime TEXT    DEFAULT '',
            enviado_en   TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS auditoria (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tarea_key    TEXT    NOT NULL,
            auditor_id   INTEGER NOT NULL,
            accion       TEXT    NOT NULL CHECK(accion IN ('validada','rechazada')),
            observacion  TEXT    DEFAULT '',
            fecha        TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY(auditor_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS historial (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tarea_key  TEXT    NOT NULL,
            usuario_id INTEGER,
            tipo       TEXT    NOT NULL,
            detalle    TEXT    DEFAULT '',
            fecha      TEXT    DEFAULT (datetime('now'))
        );
        """)

        # Usuario admin / auditor por defecto
        existing = db.execute("SELECT id FROM usuarios WHERE username='auditor'").fetchone()
        if not existing:
            db.executemany(
                "INSERT INTO usuarios (username,nombre,password,rol,eje_ids) VALUES (?,?,?,?,?)",
                [
                    ("auditor",   "Auditor OAC",          generate_password_hash("auditor2025"),   "auditor",     "[]"),
                    ("director",  "Dirección ESUCAR",     generate_password_hash("director2025"),  "direccion",   "[]"),
                    ("resp_e1",   "Responsable Eje I",    generate_password_hash("resp2025"),      "responsable", '["E1"]'),
                    ("resp_e2",   "Responsable Eje II",   generate_password_hash("resp2025"),      "responsable", '["E2"]'),
                    ("resp_e3",   "Responsable Eje III",  generate_password_hash("resp2025"),      "responsable", '["E3"]'),
                    ("resp_e4",   "Responsable Eje IV",   generate_password_hash("resp2025"),      "responsable", '["E4"]'),
                    ("resp_e5",   "Responsable Eje V",    generate_password_hash("resp2025"),      "responsable", '["E5"]'),
                ]
            )
        db.commit()

init_db()


# ── Helpers auth ───────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated

def rol_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("rol") not in roles:
                return jsonify({"error": "Sin permisos"}), 403
            return f(*args, **kwargs)
        return login_required(decorated)
    return decorator

def current_user():
    if "user_id" not in session:
        return None
    with get_db() as db:
        return db.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXT


# ── Auth endpoints ─────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    with get_db() as db:
        u = db.execute("SELECT * FROM usuarios WHERE username=? AND activo=1",
                       (data.get("username",""),)).fetchone()
    if u and check_password_hash(u["password"], data.get("password","")):
        session["user_id"] = u["id"]
        session["username"] = u["username"]
        session["nombre"]   = u["nombre"]
        session["rol"]      = u["rol"]
        session["eje_ids"]  = json.loads(u["eje_ids"])
        return jsonify({
            "ok": True,
            "usuario": {"id": u["id"], "nombre": u["nombre"],
                        "rol": u["rol"], "eje_ids": json.loads(u["eje_ids"])}
        })
    return jsonify({"ok": False, "error": "Credenciales incorrectas"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    u = current_user()
    return jsonify({
        "id": u["id"], "username": u["username"], "nombre": u["nombre"],
        "rol": u["rol"], "eje_ids": json.loads(u["eje_ids"])
    })


# ── Tareas ─────────────────────────────────────────────────────────────────────
@app.route("/api/tareas", methods=["GET"])
@login_required
def get_tareas():
    year = request.args.get("year", 2025, type=int)
    eje  = request.args.get("eje")
    u    = current_user()
    eje_ids = json.loads(u["eje_ids"])

    with get_db() as db:
        q = "SELECT * FROM tareas_estado WHERE year=?"
        params = [year]
        if u["rol"] == "responsable" and eje_ids:
            placeholders = ",".join("?" * len(eje_ids))
            q += f" AND eje_id IN ({placeholders})"
            params += eje_ids
        if eje:
            q += " AND eje_id=?"
            params.append(eje)
        rows = db.execute(q, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/tareas/<tarea_key>", methods=["GET"])
@login_required
def get_tarea(tarea_key):
    with get_db() as db:
        estado = db.execute(
            "SELECT * FROM tareas_estado WHERE tarea_key=?", (tarea_key,)).fetchone()
        evidencias = db.execute("""
            SELECT e.*, u.nombre AS responsable_nombre
            FROM evidencias e JOIN usuarios u ON e.usuario_id=u.id
            WHERE e.tarea_key=? ORDER BY e.enviado_en DESC
        """, (tarea_key,)).fetchall()
        auditorias = db.execute("""
            SELECT a.*, u.nombre AS auditor_nombre
            FROM auditoria a JOIN usuarios u ON a.auditor_id=u.id
            WHERE a.tarea_key=? ORDER BY a.fecha DESC
        """, (tarea_key,)).fetchall()
        hist = db.execute("""
            SELECT h.*, u.nombre AS usr_nombre
            FROM historial h LEFT JOIN usuarios u ON h.usuario_id=u.id
            WHERE h.tarea_key=? ORDER BY h.fecha DESC LIMIT 20
        """, (tarea_key,)).fetchall()
    return jsonify({
        "estado":     dict(estado) if estado else None,
        "evidencias": [dict(e) for e in evidencias],
        "auditorias": [dict(a) for a in auditorias],
        "historial":  [dict(h) for h in hist]
    })


# ── Subir evidencia ────────────────────────────────────────────────────────────
@app.route("/api/evidencia", methods=["POST"])
@rol_required("responsable", "auditor")
def subir_evidencia():
    tarea_key   = request.form.get("tarea_key", "")
    descripcion = request.form.get("descripcion", "").strip()
    eje_id      = request.form.get("eje_id", "")
    obj_id      = request.form.get("obj_id", "")
    year        = int(request.form.get("year", 2025))
    mes_idx     = int(request.form.get("mes_idx", 0))
    tarea_idx   = int(request.form.get("tarea_idx", 0))
    u           = current_user()

    # Validar que responsable solo suba a sus ejes
    if u["rol"] == "responsable":
        eje_ids = json.loads(u["eje_ids"])
        if eje_ids and eje_id not in eje_ids:
            return jsonify({"error": "Sin permisos para este eje"}), 403

    if not descripcion:
        return jsonify({"error": "La descripción es obligatoria"}), 400

    archivo_orig = archivo_uuid = archivo_mime = ""
    if "archivo" in request.files:
        f = request.files["archivo"]
        if f and f.filename and allowed_file(f.filename):
            ext = f.filename.rsplit(".", 1)[1].lower()
            archivo_uuid = f"{uuid.uuid4().hex}.{ext}"
            archivo_orig = secure_filename(f.filename)
            archivo_mime = f.content_type or ""
            f.save(os.path.join(UPLOAD_DIR, archivo_uuid))

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    with get_db() as db:
        # Guardar evidencia
        db.execute("""
            INSERT INTO evidencias
              (tarea_key,usuario_id,descripcion,archivo_orig,archivo_uuid,archivo_mime,enviado_en)
            VALUES (?,?,?,?,?,?,?)
        """, (tarea_key, u["id"], descripcion, archivo_orig, archivo_uuid, archivo_mime, now))

        # Actualizar / insertar estado
        existing = db.execute(
            "SELECT id FROM tareas_estado WHERE tarea_key=?", (tarea_key,)).fetchone()
        if existing:
            db.execute(
                "UPDATE tareas_estado SET estado='enviada', actualizado=? WHERE tarea_key=?",
                (now, tarea_key))
        else:
            db.execute("""
                INSERT INTO tareas_estado
                  (tarea_key,eje_id,obj_id,year,mes_idx,tarea_idx,estado,actualizado)
                VALUES (?,?,?,?,?,?,?,?)
            """, (tarea_key, eje_id, obj_id, year, mes_idx, tarea_idx, "enviada", now))

        # Historial
        db.execute("""
            INSERT INTO historial (tarea_key,usuario_id,tipo,detalle,fecha)
            VALUES (?,?,'enviada',?,?)
        """, (tarea_key, u["id"],
              f"Evidencia subida por {u['nombre']}. Archivo: {archivo_orig or 'ninguno'}",
              now))
        db.commit()

    return jsonify({"ok": True, "tarea_key": tarea_key, "estado": "enviada"})


# ── Descargar archivo ──────────────────────────────────────────────────────────
@app.route("/api/archivo/<archivo_uuid>")
@login_required
def descargar_archivo(archivo_uuid):
    with get_db() as db:
        ev = db.execute(
            "SELECT * FROM evidencias WHERE archivo_uuid=?", (archivo_uuid,)).fetchone()
    if not ev:
        return jsonify({"error": "Archivo no encontrado"}), 404
    return send_from_directory(
        UPLOAD_DIR, archivo_uuid,
        as_attachment=True,
        download_name=ev["archivo_orig"] or archivo_uuid
    )


# ── Auditoría: validar / rechazar ──────────────────────────────────────────────
@app.route("/api/auditoria", methods=["POST"])
@rol_required("auditor")
def registrar_auditoria():
    data        = request.get_json()
    tarea_key   = data.get("tarea_key", "")
    accion      = data.get("accion", "")     # 'validada' | 'rechazada'
    observacion = data.get("observacion", "").strip()
    u           = current_user()

    if accion not in ("validada", "rechazada"):
        return jsonify({"error": "Acción inválida"}), 400
    if accion == "rechazada" and not observacion:
        return jsonify({"error": "Debe indicar el motivo del rechazo"}), 400

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    with get_db() as db:
        db.execute("""
            INSERT INTO auditoria (tarea_key,auditor_id,accion,observacion,fecha)
            VALUES (?,?,?,?,?)
        """, (tarea_key, u["id"], accion, observacion, now))

        nuevo_estado = "validada" if accion == "validada" else "rechazada"
        db.execute(
            "UPDATE tareas_estado SET estado=?, actualizado=? WHERE tarea_key=?",
            (nuevo_estado, now, tarea_key))

        db.execute("""
            INSERT INTO historial (tarea_key,usuario_id,tipo,detalle,fecha)
            VALUES (?,?,?,?,?)
        """, (tarea_key, u["id"], accion,
              f"Auditor {u['nombre']}: {observacion or 'Sin observaciones'}",
              now))
        db.commit()

    return jsonify({"ok": True, "estado": nuevo_estado})


# ── Dashboard / estadísticas ───────────────────────────────────────────────────
@app.route("/api/dashboard", methods=["GET"])
@login_required
def dashboard():
    year = request.args.get("year", 2025, type=int)
    with get_db() as db:
        resumen = db.execute("""
            SELECT estado, COUNT(*) as total
            FROM tareas_estado WHERE year=?
            GROUP BY estado
        """, (year,)).fetchall()

        por_eje = db.execute("""
            SELECT eje_id,
                   COUNT(*) as total,
                   SUM(CASE WHEN estado='validada'  THEN 1 ELSE 0 END) as validadas,
                   SUM(CASE WHEN estado='enviada'   THEN 1 ELSE 0 END) as enviadas,
                   SUM(CASE WHEN estado='rechazada' THEN 1 ELSE 0 END) as rechazadas,
                   SUM(CASE WHEN estado='pendiente' THEN 1 ELSE 0 END) as pendientes
            FROM tareas_estado WHERE year=?
            GROUP BY eje_id
        """, (year,)).fetchall()

        pendientes_auditoria = db.execute("""
            SELECT t.*, u.nombre AS resp_nombre, e.descripcion, e.archivo_orig,
                   e.archivo_uuid, e.enviado_en
            FROM tareas_estado t
            JOIN evidencias e ON t.tarea_key = e.tarea_key
            JOIN usuarios u ON e.usuario_id = u.id
            WHERE t.estado='enviada' AND t.year=?
            ORDER BY e.enviado_en ASC
        """, (year,)).fetchall()

    return jsonify({
        "resumen":                [dict(r) for r in resumen],
        "por_eje":                [dict(r) for r in por_eje],
        "pendientes_auditoria":   [dict(r) for r in pendientes_auditoria],
    })


# ── Gestión de usuarios (solo auditor/admin) ───────────────────────────────────
@app.route("/api/usuarios", methods=["GET"])
@rol_required("auditor", "direccion")
def listar_usuarios():
    with get_db() as db:
        users = db.execute(
            "SELECT id,username,nombre,rol,eje_ids,activo,creado FROM usuarios"
        ).fetchall()
    return jsonify([dict(u) for u in users])

@app.route("/api/usuarios", methods=["POST"])
@rol_required("auditor")
def crear_usuario():
    data = request.get_json()
    required = ["username", "nombre", "password", "rol"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"Campo requerido: {f}"}), 400
    if data["rol"] not in ("responsable", "auditor", "direccion"):
        return jsonify({"error": "Rol inválido"}), 400

    hashed = generate_password_hash(data["password"])
    eje_ids = json.dumps(data.get("eje_ids", []))
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO usuarios (username,nombre,password,rol,eje_ids) VALUES (?,?,?,?,?)",
                (data["username"], data["nombre"], hashed, data["rol"], eje_ids))
            db.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": "El usuario ya existe"}), 409

@app.route("/api/usuarios/<int:uid>/password", methods=["PUT"])
@rol_required("auditor")
def cambiar_password(uid):
    data = request.get_json()
    nueva = data.get("password", "")
    if len(nueva) < 6:
        return jsonify({"error": "Contraseña mínimo 6 caracteres"}), 400
    with get_db() as db:
        db.execute("UPDATE usuarios SET password=? WHERE id=?",
                   (generate_password_hash(nueva), uid))
        db.commit()
    return jsonify({"ok": True})


# ── Servir el frontend ─────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect("/login")
    return send_from_directory("static", "index.html")

@app.route("/login")
def login_page():
    return send_from_directory("static", "login.html")

@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)


# ── Health check ───────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "CMI-ESUCAR", "version": "2.0"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
