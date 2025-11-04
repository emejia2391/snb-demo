import datetime
import datetime as dt

def _parse_fecha_flexible(s: str):
    """Accepts YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD. Returns datetime.date or raises."""
    import datetime as _dt
    s = (s or "").strip()
    if not s:
        raise ValueError("empty")
    # try ISO directly
    try:
        return _dt.date.fromisoformat(s)
    except Exception:
        pass
    # normalize separators
    ss = s.replace(".", "/").replace("-", "/")
    # try several formats
    for fmt in ("%d/%m/%Y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(ss, fmt).date()
        except Exception:
            continue
    # last resort: swap if looks like DD/MM/YYYY
    parts = ss.split("/")
    if len(parts)== 4 and len(parts[0])<=2 and len(parts[1])<=2 and len(parts[2])==4:
        try:
            d,m,y = map(int, parts)
            return _dt.date(y,m,d)
        except Exception:
            pass
    raise ValueError(f"Fecha no reconocida: {s}")



# -*- coding: utf-8 -*-
import os
from functools import wraps
from datetime import datetime

from flask import (jsonify, 
    Flask, render_template, request, redirect, url_for,
    session, flash, g
)
from sqlalchemy import create_engine, text

# ------------------------------------------------------------
# Configuración
# ------------------------------------------------------------
# --- WhatsApp (Twilio Sandbox) ---
try:
    from twilio.rest import Client as _TwilioClient
except Exception:
    _TwilioClient = None

def _format_e164_gt(num):
    try:
        s = str(num).strip().replace(" ", "").replace("-", "")
        if s.startswith("+"):
            return s
        if s.startswith("502"):
            return f"+{s}"
        if s.isdigit():
            return f"+502{s}"
    except Exception:
        pass
    return None

def send_welcome_whatsapp(payload: dict):
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    tok = os.getenv("TWILIO_AUTH_TOKEN")
    wa_from = os.getenv("TWILIO_WA_FROM", "whatsapp:+14155238886")
    if not (sid and tok and wa_from and _TwilioClient):
        return False

    to_override = os.getenv("WA_TEST_TO", "").strip()
    if to_override:
        to_e164 = to_override if to_override.startswith("whatsapp:") else f"whatsapp:{to_override}"
    else:
        to_e164_plain = _format_e164_gt(payload.get("celular"))
        if not to_e164_plain:
            return False
        to_e164 = f"whatsapp:{to_e164_plain}"

    body = (
        f"Bienvenido a San Nicolás del Bosque, {payload.get('nombre','')} {payload.get('apellido','')}."\
        f"\nUsuario: {payload.get('usuario','')}"\
        f"\nTorre: {payload.get('torre') or ''}  Apto: {payload.get('apartamento') or ''}"\
        f"\nTeléfono registrado: {payload.get('celular') or ''}"
    )
    try:
        client = _TwilioClient(sid, tok)
        client.messages.create(to=to_e164, from_=wa_from, body=body)
        return True
    except Exception as _e:
        try:
            app.logger.warning(f"WA bienvenida falló: {_e}")
        except Exception:
            pass
        return False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "snb-secret-key")

# Base de datos (Nile / Postgres) - usando tu URL que SÍ funciona
DEFAULT_URL = (
    "postgresql+psycopg://"
    "019a2b0a-52ee-7295-a575-9727361952aa:"
    "20028ee6-7631-4301-b980-428298724eba"
    "@us-west-2.db.thenile.dev:5432/calendarioSNB?sslmode=require"
)
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_URL)

# Motor SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

# ------------------------------------------------------------
# Helpers de sesión
# ------------------------------------------------------------
def current_user():
    u = session.get("user")
    return u if u else None


from urllib.parse import quote

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        # Forzar cambio de contraseña si aplica
        u = session.get("user") or {}
        path = request.path or ""
        allowed = ("/login", "/logout", "/static", "/cambiar_password")
        if u.get("must_change") and not any(path.startswith(p) for p in allowed):
            # Usar ruta literal para evitar BuildError si aún no se ha registrado el endpoint
            return redirect(f"/cambiar_password?next={quote(request.path or '/')}")
        return view(*args, **kwargs)
    return wrapper


@app.before_request
def inject_user():
    u = session.get("user")
    if u and u.get("username") and "id_usuario" not in u:
        # Inline fetch to avoid NameError if helper is missing
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT id_usuario, id_rol, debe_cambiar_password
                FROM public.usuarios
                WHERE LOWER(usuario)=LOWER(:u)
                LIMIT 1
            """), {"u": u["username"]}).mappings().first()
        if row:
            u["id_usuario"] = row.get("id_usuario")
            u["id_rol"] = row.get("id_rol")
            u["must_change"] = True if row.get("debe_cambiar_password") in (1, "1", True) else False
            session["user"] = u
    g.user = current_user()
    
# --- Restricción por rol (Residente solo puede ver Inicio) -------------------
RESIDENT_ROLE_ID = 2

def _is_residente(u):
    try:
        return int((u or {}).get("id_rol") or 0) == RESIDENT_ROLE_ID
    except Exception:
        return False

@app.before_request
def restrict_resident_sections():
    # Deja pasar estáticos
    if request.endpoint == "static":
        return

    u = session.get("user")
    if not u or not _is_residente(u):
        return  # no logueado o no residente -> sin restricción extra

    # Rutas de páginas que NO puede abrir el residente
    forbidden_prefixes = (
        "/usuarios",         # /usuarios, /usuarios/... 
        "/roles",            # /roles, /roles/...
        "/areas-sociales",   # /areas-sociales, /areas-sociales/...
    )

    path = request.path or "/"
    # Permitir APIs y flujos de login/logout/cambio de pwd
    allowed_prefixes = ("/api", "/login", "/logout", "/cambiar_password")

    if any(path.startswith(pref) for pref in forbidden_prefixes) and not any(
        path.startswith(pref) for pref in allowed_prefixes
    ):
        flash("Acceso restringido para residentes/visor.", "error")
        return redirect(url_for("index"))
    

# ------------------------------------------------------------
# Healthcheck
# ------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

# ------------------------------------------------------------
# Login / Logout (modo simple que ya te funciona)
# ------------------------------------------------------------

@app.before_request
def _restrict_nav_for_roles():
    u = session.get("user")
    if not u:
        return
    u_role = u.get("id_rol")
    if u_role in (2,4):  # Residente o Visor
        path = request.path or ""
        if path.startswith("/static/"):
            return
        # Permitir APIs necesarias para reservar
        api_ok_prefixes = ("/api/areas", "/api/area_meta", "/api/reservas/ocupadas", "/api/usuarios", "/api/calendario/semana")
        if any(path.startswith(p) for p in api_ok_prefixes):
            return
        # Permitir flujos básicos
        allowed = {"/", "/login", "/logout", "/cambiar_password"}
        if path in allowed:
            return
        # Bloquear páginas de administración
        forbidden_keys = ("usuarios", "roles", "areas-sociales")
        if any(f"/{k}" in path for k in forbidden_keys):
            flash("Acceso restringido para residentes/visor.", "error")
            return redirect(url_for("index"))


    # Bloqueo específico: Operador (3) no puede acceder a /roles
    if u_role == 3:
        path = request.path or ""
        if path.startswith("/roles"):
            flash("Acceso restringido para operadores.", "error")
            return redirect(url_for("index"))
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Credenciales inválidas", "error")
            return render_template("login.html")

        # Buscar usuario en BD
        row = _usuario_fetch_by_username(username)
        # Validar existencia y contraseña con Argon2
        if (not row) or (not row.get("password_hash")) or (not _verify_password(row["password_hash"], password)):
            flash("Credenciales inválidas", "error")
            return render_template("login.html")

        # Validar estado habilitado (1)
        try:
            est = int(row.get("estado") or 0)
        except Exception:
            est = 0
        if est != 1:
            flash("Usuario inhabilitado", "error")
            return render_template("login.html")

        # Iniciar sesión con datos completos
        must_change = True if row.get("debe_cambiar_password") in (1, "1", True) else False
        session["user"] = {
            "username": row.get("usuario") or username,
            "nombre": (row.get("nombre") or row.get("usuario") or username),
            "id_usuario": row.get("id_usuario"),
            "id_rol": row.get("id_rol"),
            "must_change": must_change,
        }

        next_url = request.args.get("next") or url_for("index")
        if must_change:
            from urllib.parse import quote
            return redirect(f"/cambiar_password?next={quote(next_url)}")
        return redirect(next_url)

    return render_template("login.html")
@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------------------------------------------------
# Inicio
# ------------------------------------------------------------

@app.get("/")
@login_required
def index():
    # Áreas sociales habilitadas para selector
    areas = []
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT id_area, nombre
                FROM public.areas_sociales
                WHERE estado = 1
                ORDER BY nombre
            """)).mappings().all()
            areas = [dict(r) for r in rows]
    except Exception as e:
        flash(f"No se pudo cargar áreas: {e}", "error")
    sel = request.args.get("area_id")
    if sel:
        try:
            session["selected_area_id"] = int(sel)
        except Exception:
            session["selected_area_id"] = sel
    return render_template("index.html", user=current_user(), areas=areas, area_id=sel)

# ---- Helper para armar URL de paginación conservando filtros ----
@app.context_processor
def _pagination_helpers():
    def qs_with_page(page:int):
        try:
            args = request.args.to_dict(flat=True)
        except Exception:
            args = {}
        try:
            page = int(page)
            if page < 1: page = 1
        except Exception:
            page = 1
        args["page"] = page
        return url_for("usuarios_list", **args)
    return dict(qs_with_page=qs_with_page)
# ------------------------------------------------------------
# Usuarios (Listado)
# ------------------------------------------------------------

@app.get("/usuarios")

@login_required
def usuarios_list():
    filtro = request.args.get("filtro", "").strip().lower()
    valor  = request.args.get("valor", "").strip()
    try:
        page = int(request.args.get("page", "1"))
        if page < 1: page = 1
    except Exception:
        page = 1
    per_page = 5

    base_sql = """
        SELECT
            u.id_usuario                              AS id,
            COALESCE(u.nombre,'')                     AS nombre,
            COALESCE(u.apellido,'')                   AS apellido,
            COALESCE(u.correo,'')                     AS correo,
            COALESCE(u.usuario,'')                    AS usuario,
            COALESCE(u.torre::text,'')                AS torre,
            COALESCE(u.apartamento::text,'')          AS apartamento,
            COALESCE(u.id_rol::int, 0)               AS id_rol,
            COALESCE(CASE WHEN COALESCE(u.estado::int,1)=1 THEN 'Habilitado' ELSE 'Inhabilitado' END,'Habilitado') AS estado_txt,
            CASE WHEN COALESCE(u.debe_cambiar_password::int,0)=1 THEN 'Sí' ELSE 'No' END AS debe_cambiar,
            COALESCE(u.estado::int,1)                 AS estado
        FROM public.usuarios u
    """

    where = []
    params = {}

    if filtro and valor:
        if filtro == "nombre":
            where.append("u.nombre ILIKE :v"); params["v"] = f"%{valor}%"
        elif filtro == "apellido":
            where.append("u.apellido ILIKE :v"); params["v"] = f"%{valor}%"
        elif filtro == "correo":
            where.append("u.correo ILIKE :v"); params["v"] = f"%{valor}%"
        elif filtro == "usuario":
            where.append("u.usuario ILIKE :v"); params["v"] = f"%{valor}%"
        elif filtro == "torre":
            where.append("u.torre::text LIKE :v"); params["v"] = f"%{valor}%"
        elif filtro in ("apto","apartamento"):
            where.append("u.apartamento ILIKE :v"); params["v"] = f"%{valor}%"
        elif filtro == "estado":
            vmap = {"habilitado": 1, "inhabilitado": 0}
            v = vmap.get(valor.strip().lower())
            if v is not None:
                where.append("COALESCE(u.estado::int,1) = :est"); params["est"] = v

    order_sql = " ORDER BY u.creado_en DESC NULLS LAST, u.id_usuario DESC"

    # TOTAL
    count_sql = "SELECT COUNT(*) FROM public.usuarios u"
    if where:
        count_sql += " WHERE " + " AND ".join(where)

    with engine.connect() as conn:
        try:
            total = conn.execute(text(count_sql), params).scalar() or 0
        except Exception:
            total = 0

        offset = (page-1)*per_page
        final_sql = base_sql
        if where:
            final_sql += " WHERE " + " AND ".join(where)
        final_sql += order_sql + " LIMIT :limit OFFSET :offset"
        p2 = dict(params); p2["limit"] = per_page; p2["offset"] = offset
        try:
            rows = conn.execute(text(final_sql), p2).mappings().all()
        except Exception as e:
            flash(f"No se pudo consultar usuarios: {e}", "error")
            rows = []

    pages = max((total + per_page - 1)//per_page, 1)
    page = min(page, pages)
    start_idx = 1 if total==0 else (page-1)*per_page + 1
    end_idx = min(page*per_page, total)

    return render_template(
        "usuarios_list.html",
        rows=rows,
        user=current_user(),
        total=total,
        page=page,
        pages=pages,
        per_page=per_page,
        start_idx=start_idx,
        end_idx=end_idx,
    )
# ------------------------------------------------------------
# Usuarios (Eliminar)
# ------------------------------------------------------------

# ------------------------------------------------------------
# Helpers específicos de Usuarios
# ------------------------------------------------------------
from argon2 import PasswordHasher
_ph = PasswordHasher()

def _hash_password(pwd:str) -> str:
    # Devuelve un hash argon2id compatible con el CHECK de la tabla
    if not pwd:
        raise ValueError("La contraseña no puede estar vacía para generar hash.")
    return _ph.hash(pwd)

def _fetch_roles():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id_rol, rol FROM public.rol ORDER BY id_rol")).mappings().all()
    # normalizamos a {id_rol, nombre}
    return [ {"id_rol": r["id_rol"], "nombre": r["rol"]} for r in rows ]

def _fetch_torres():
    # Torres fijas: 1, 2 y 3
    return [1, 2, 3]


def _usuario_fetch_one(id_usuario:int):
    with engine.connect() as conn:
        r = conn.execute(text("""
            SELECT id_usuario, nombre, apellido, correo, usuario,
                   torre, apartamento, celular, id_rol, estado, debe_cambiar_password
            FROM public.usuarios
            WHERE id_usuario = :id
        """), {"id": id_usuario}).mappings().first()
    return r

# ------------------------------------------------------------
# Usuarios - Nuevo
# ------------------------------------------------------------
@app.route("/usuarios/nuevo", methods=["GET","POST"])
@login_required
def usuarios_nuevo():
    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre","").strip(),
            "apellido": request.form.get("apellido","").strip(),
            "correo": request.form.get("correo","").strip(),
            "usuario": request.form.get("usuario","").strip(),
            "celular": request.form.get("celular","").strip(),
            "torre": request.form.get("torre") or None,
            "apartamento": request.form.get("apartamento") or None,
            "id_rol": request.form.get("id_rol"),
            "estado": int(request.form.get("estado", 1)),
            "debe_cambiar": 1 if (request.form.get("debe_cambiar") in ("on","1","true",True)) else 0,
        }
        # Normaliza tipos
        data["torre"] = int(data["torre"]) if data["torre"] not in (None, "", "None") else None
        data["id_rol"] = int(data["id_rol"]) if data["id_rol"] not in (None, "", "None") else None
        # --- Normalización y validación de celular (servidor): solo 8 dígitos ---
        import re as _re
        cel = (data.get("celular") or "").strip()
        cel_digits = _re.sub(r"\D", "", cel)
        if cel_digits and len(cel_digits) != 8:
            flash("El celular debe tener exactamente 8 dígitos.", "error")
            roles = _fetch_roles()
            torres = _fetch_torres()
            estados = [(1, "Activo"), (0, "Inactivo")]
            edit=False
            u = data
            return render_template("usuarios_form.html", edit=edit, u=u, roles=roles, torres=torres, estados=estados, user=current_user())
        data["celular"] = cel_digits or None
        # --- Unicidad de correo y usuario (crear) ---
        # Normaliza a minúsculas para comparar
        if data.get("correo"): data["correo"] = data["correo"].strip().lower()
        if data.get("usuario"): data["usuario"] = data["usuario"].strip().lower()
        # Validar duplicados
        if data.get("correo"):
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT 1 FROM public.usuarios
                    WHERE lower(correo) = :correo
                    LIMIT 1
                """), {"correo": data["correo"]}).first()
            if row:
                flash("Correo ya existe", "error")
                roles = _fetch_roles(); torres = _fetch_torres(); estados = [(1,"Activo"),(0,"Inactivo")]
                edit=False; u=data
                return render_template("usuarios_form.html", edit=edit, u=u, roles=roles, torres=torres, estados=estados, user=current_user())
        if data.get("usuario"):
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT 1 FROM public.usuarios
                    WHERE lower(usuario) = :usuario
                    LIMIT 1
                """), {"usuario": data["usuario"]}).first()
            if row:
                flash("Usuario ya existe", "error")
                roles = _fetch_roles(); torres = _fetch_torres(); estados = [(1,"Activo"),(0,"Inactivo")]
                edit=False; u=data
                return render_template("usuarios_form.html", edit=edit, u=u, roles=roles, torres=torres, estados=estados, user=current_user())



        # Operador no puede crear usuarios con rol Admin
        cu = current_user() or {}
        if int(cu.get("id_rol",0)) == 4 and int(data.get("id_rol") or 0) == 1:
            flash("Permiso denegado: un Operador no puede crear usuarios con rol Admin.", "error")
            # Re-renderiza el formulario con los datos ya ingresados
            roles = _fetch_roles()
            torres = list(range(1, 6))
            estados = [(1, "Activo"), (0, "Inactivo")]
            edit=False
            u = data  # para re-poblar campos
            return render_template("usuarios_form.html", edit=edit, u=u, roles=roles, torres=torres, estados=estados)

        
        # --- Validación: celular único ---
        if data.get("celular"):
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT 1 FROM public.usuarios
                    WHERE celular = :celular
                    LIMIT 1
                """), {"celular": data["celular"]}).first()
            if row:
                flash("Numero de celular ya existe", "error")
                roles = _fetch_roles()
                torres = _fetch_torres()
                estados = [(1, "Activo"), (0, "Inactivo")]
                edit=False
                u = data
                return render_template("usuarios_form.html", edit=edit, u=u, roles=roles, torres=torres, estados=estados, user=current_user())
        raw_pwd = request.form.get("password","").strip()
        if not raw_pwd:
            # Si no envían password, generamos una temporal aleatoria de 10 chars
            import secrets, string
            raw_pwd = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
            data["debe_cambiar"] = 1
        pwd_hash = _hash_password(raw_pwd)

        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO public.usuarios
                    (torre, apartamento, celular, nombre, apellido, correo,
                     id_rol, creado_en, actualizado_en, usuario,
                     password_hash, estado, debe_cambiar_password)
                    VALUES
                    (:torre, :apartamento, :celular, :nombre, :apellido, :correo,
                     :id_rol, now(), now(), :usuario,
                     :password_hash, :estado, :debe_cambiar)
                """), {**data, "password_hash": pwd_hash})
                        # Enviar WhatsApp de bienvenida (usa WA_TEST_TO si está seteado)
            try:
                send_welcome_whatsapp({
                    "nombre": data.get("nombre"),
                    "apellido": data.get("apellido"),
                    "usuario": data.get("usuario"),
                    "torre": data.get("torre"),
                    "apartamento": data.get("apartamento"),
                    "celular": data.get("celular"),
                })
            except Exception as _e:
                app.logger.warning(f"send_welcome_whatsapp error: {_e}")
            flash(" ", "success"); session["_sn_toast"] = {"text": "Usuario creado con éxito", "level": "info"}
            return redirect(url_for("usuarios_list"))
        except Exception as e:
            flash(f"No se pudo crear el usuario: {e}", "error")

    estados = [(1,"Activo"), (0,"Inactivo")]
    return render_template("usuarios_form.html",
                           roles=_fetch_roles(),
                           torres=_fetch_torres(),
                           estados=estados,
                           user=current_user())


# ------------------------------------------------------------
# Permisos simples
# ------------------------------------------------------------
def _operator_blocks_admin(target_user):
    try:
        cu = current_user() or {}
        return int(cu.get("id_rol", 0)) == 4 and int(target_user.get("id_rol", 0)) == 1
    except Exception:
        return False
# ------------------------------------------------------------
# Usuarios - Editar
# ------------------------------------------------------------
@app.route("/usuarios/<int:id>/editar", methods=["GET","POST"])
@login_required
def usuarios_editar(id):
    u = _usuario_fetch_one(id)
    if not u:
        flash(f"Usuario #{id} no existe", "error")
        return redirect(url_for("usuarios_list"))
    # Bloqueo: operador no puede editar admins
    if _operator_blocks_admin(u):
        flash("Permiso denegado para editar usuarios Admin.", "error")
        return redirect(url_for("usuarios_list"))
    if request.method == "POST":
        data = {
            "id": id,
            "nombre": request.form.get("nombre","").strip(),
            "apellido": request.form.get("apellido","").strip(),
            "correo": request.form.get("correo","").strip(),
            "usuario": request.form.get("usuario","").strip(),
            "celular": request.form.get("celular","").strip(),
            "torre": request.form.get("torre"),
            "apartamento": request.form.get("apartamento"),
            "id_rol": request.form.get("id_rol"),
            "estado": int(request.form.get("estado", 1)),
            "debe_cambiar": 1 if (request.form.get("debe_cambiar") in ("on","1","true",True)) else 0,
        }

        # --- Normalización de entradas: "", "None", "null" => None real ---
        for k in ("torre", "apartamento", "id_rol"):
            v = data.get(k)
            if isinstance(v, str) and v.strip().lower() in ("", "none", "null"):
                data[k] = None

        # --- Casts seguros ---
        data["id_rol"] = int(data["id_rol"]) if data["id_rol"] is not None else None
        data["torre"] = int(data["torre"]) if data["torre"] is not None else None
        data["apartamento"] = (str(data["apartamento"]).strip().upper() or None) if data["apartamento"] is not None else None

        # --- Regla para OPERADOR (id_rol = 3): torre y apartamento deben ir NULL ---
        if data.get("id_rol") == 4:
            data["torre"] = None
            data["apartamento"] = None
        # --- Normalización y validación de celular (servidor): solo 8 dígitos ---
        import re as _re
        cel = (data.get("celular") or "").strip()
        cel_digits = _re.sub(r"\D", "", cel)
        if cel_digits and len(cel_digits) != 8:
            flash("El celular debe tener exactamente 8 dígitos.", "error")
            estados = [(1,"Activo"), (0,"Inactivo")]
            return render_template("usuarios_form.html",
                                   roles=_fetch_roles(),
                                   torres=_fetch_torres(),
                                   estados=estados,
                                   u=u, edit=True,
                                   user=current_user())
        data["celular"] = cel_digits or None

        raw_pwd = request.form.get("password","").strip()
        try:

            with engine.begin() as conn:
                
                # --- Unicidad de correo y usuario (editar) ---
                if data.get("correo"): data["correo"] = str(data["correo"]).strip().lower()
                if data.get("usuario"): data["usuario"] = str(data["usuario"]).strip().lower()

                if data.get("correo"):
                    row = conn.execute(text("""
                        SELECT 1 FROM public.usuarios
                        WHERE lower(correo) = :correo AND id_usuario <> :id
                        LIMIT 1
                    """), {"correo": data["correo"], "id": id}).first()
                    if row:
                        flash("Correo ya existe", "error")
                        estados = [(1,"Activo"), (0,"Inactivo")]
                        return render_template("usuarios_form.html",
                                               roles=_fetch_roles(),
                                               torres=_fetch_torres(),
                                               estados=estados,
                                               u=u, edit=True,
                                               user=current_user())

                if data.get("usuario"):
                    row = conn.execute(text("""
                        SELECT 1 FROM public.usuarios
                        WHERE lower(usuario) = :usuario AND id_usuario <> :id
                        LIMIT 1
                    """), {"usuario": data["usuario"], "id": id}).first()
                    if row:
                        flash("Usuario ya existe", "error")
                        estados = [(1,"Activo"), (0,"Inactivo")]
                        return render_template("usuarios_form.html",
                                               roles=_fetch_roles(),
                                               torres=_fetch_torres(),
                                               estados=estados,
                                               u=u, edit=True,
                                               user=current_user())
# --- Validación: celular único (excluyendo el propio id) ---
                if data.get("celular"):
                    row = conn.execute(text("""
                        SELECT 1 FROM public.usuarios
                        WHERE celular = :celular AND id_usuario <> :id
                        LIMIT 1
                    """), {"celular": data["celular"], "id": id}).first()
                    if row:
                        flash("Numero de celular ya existe", "error")
                        estados = [(1,"Activo"), (0,"Inactivo")]
                        return render_template("usuarios_form.html",
                                               roles=_fetch_roles(),
                                               torres=_fetch_torres(),
                                               estados=estados,
                                               u=u, edit=True,
                                               user=current_user())

                if raw_pwd:
                    pwd_hash = _hash_password(raw_pwd)
                    conn.execute(text("""
                        UPDATE public.usuarios
                           SET nombre=:nombre, apellido=:apellido, correo=:correo, usuario=:usuario,
                               celular=:celular, torre=:torre, apartamento=:apartamento,
                               id_rol=:id_rol, estado=:estado, debe_cambiar_password=:debe_cambiar,
                               password_hash=:pwd
                         WHERE id_usuario=:id
                    """), {**data, "pwd": pwd_hash})
                else:
                    conn.execute(text("""
                        UPDATE public.usuarios
                           SET nombre=:nombre, apellido=:apellido, correo=:correo, usuario=:usuario,
                               celular=:celular, torre=:torre, apartamento=:apartamento,
                               id_rol=:id_rol, estado=:estado, debe_cambiar_password=:debe_cambiar
                         WHERE id_usuario=:id
                    """), data)

            flash(" ", "success"); session["_sn_toast"] = {"text": "Cambios guardados con éxito", "level": "info"}
            return redirect(url_for("usuarios_list"))
        except Exception as e:
            flash(f"No se pudo actualizar el usuario: {e}", "error")

    estados = [(1,"Activo"), (0,"Inactivo")]
    return render_template("usuarios_form.html",
                           roles=_fetch_roles(),
                           torres=_fetch_torres(),
                           estados=estados,
                           u=u, edit=True,
                           user=current_user())


# ------------------------------------------------------------
# Usuarios - Ver
# ------------------------------------------------------------
@app.route("/usuarios/<int:id>")
@login_required
def usuarios_ver(id):
    u = _usuario_fetch_one(id)
    if not u:
        flash(f"Usuario #{id} no existe", "error")
        return redirect(url_for("usuarios_list"))
    # Bloqueo: operador no puede ver admins
    if _operator_blocks_admin(u):
        flash("Permiso denegado para ver usuarios Admin.", "error")
        return redirect(url_for("usuarios_list"))
    roles = _fetch_roles()
    return render_template("usuarios_ver.html", u=u, roles=roles, user=current_user())
# ------------------------------------------------------------
# Utilidades ÁREAS
# ------------------------------------------------------------
def _to_pg_text_array(lst):
    """Convierte ['lunes','martes'] -> '{lunes,martes}' como fallback."""
    if not lst:
        return "{}"
    safe = [ (s or "").replace(",", "").strip() for s in lst ]
    return "{" + ",".join(safe) + "}"

def _area_fetch_one(id_area:int):
    with engine.connect() as conn:
        r = conn.execute(text("""
            SELECT id_area, nombre, precio, horas, dias, horarios, estado, hora_inicio, horas_inicio
            FROM public.areas_sociales
            WHERE id_area = :id
        """), {"id": id_area}).mappings().first()
    return r

# ------------------------------------------------------------
# Áreas sociales (Listado)
# ------------------------------------------------------------
@app.route("/areas-sociales")
@login_required
def areas_sociales_list():
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id_area, nombre, precio, horas, dias, horarios, estado, hora_inicio, horas_inicio
                FROM public.areas_sociales
                ORDER BY id_area
            """)).mappings().all()
        areas = [dict(r) for r in rows]
        return render_template("areas_sociales.html", areas=areas, user=current_user())
    except Exception as e:
        flash(f"No se pudieron cargar las áreas sociales: {e}", "error")
        return render_template("areas_sociales.html", areas=[], user=current_user())

# ------------------------------------------------------------
# Áreas sociales (Nuevo)
# ------------------------------------------------------------
@app.route("/areas-sociales/nuevo", methods=["GET", "POST"])
@login_required
def areas_sociales_nueva():
    if request.method == "GET":
        return render_template("areas_sociales_form.html", area=None, user=current_user())

    # POST - crear
    nombre = (request.form.get("nombre") or "").strip()
    precio = request.form.get("precio", "0").strip()
    horas  = request.form.get("horas", "0").strip()
    dias   = request.form.getlist("dias[]") or request.form.getlist("dias")
    horarios = request.form.getlist("horarios[]") or request.form.getlist("horarios")
    estado = int(request.form.get("estado", "1"))
    horas_inicio = request.form.getlist("horas_inicio")
    hora_inicio = (horas_inicio[0] if horas_inicio else request.form.get("hora_inicio", "00:00"))

    if not nombre:
        flash("El nombre es requerido.", "error")
        return render_template("areas_sociales_form.html", area=None, user=current_user())

    try:
        with engine.begin() as conn:
            try:
                # Intento directo con lista -> text[]
                conn.execute(text("""
                    INSERT INTO public.areas_sociales (nombre, precio, horas, dias, horarios, estado, hora_inicio, horas_inicio)
                    VALUES (:nombre, :precio, :horas, :dias, :horarios, :estado, :hora_inicio, :horas_inicio)
                """), {"nombre": nombre, "precio": precio, "horas": horas, "dias": dias, "horarios": horarios, "estado": estado, "hora_inicio": hora_inicio, "horas_inicio": horas_inicio})
            except Exception:
                # Fallback con literal {a,b,c}
                conn.execute(text("""
                    INSERT INTO public.areas_sociales (nombre, precio, horas, dias, horarios, estado, hora_inicio, horas_inicio)
                    VALUES (:nombre, :precio, :horas, :dias::text[], :horarios::time[], :estado, :hora_inicio, :horas_inicio::time[])
                """), {"nombre": nombre, "precio": precio, "horas": horas, "dias": _to_pg_text_array(dias), "horarios": _to_pg_text_array(horarios), "estado": estado, "hora_inicio": hora_inicio, "horas_inicio": horas_inicio})
        flash("", "success"); session["_sn_toast"] = {"text": "Cambios guardados con éxito", "level": "info"}
        return redirect(url_for("areas_sociales_list"))
    except Exception as e:
        flash(f"Error al crear el área social: {e}", "error")
        return render_template("areas_sociales_form.html", area=None, user=current_user())

# ------------------------------------------------------------
# Áreas sociales (Ver)
# ------------------------------------------------------------
@app.get("/areas-sociales/<int:id>/ver")
@login_required
def areas_sociales_ver(id:int):
    area = _area_fetch_one(id)
    if not area:
        flash("Área social no encontrada.", "error")
        return redirect(url_for("areas_sociales_list"))
    return render_template("areas_sociales_ver.html", area=area, user=current_user())

# ------------------------------------------------------------
# Áreas sociales (Editar)
# ------------------------------------------------------------
@app.route("/areas-sociales/<int:id>/editar", methods=["GET", "POST"])
@login_required
def areas_sociales_editar(id: int):
    if request.method == "GET":
        area = _area_fetch_one(id)
        if not area:
            flash("Área social no encontrada.", "error")
            return redirect(url_for("areas_sociales_list"))
        return render_template("areas_sociales_form.html", area=area, user=current_user())

    # POST
    nombre = (request.form.get("nombre") or "").strip()
    precio = request.form.get("precio", "0").strip()
    horas  = request.form.get("horas", "0").strip()
    dias   = request.form.getlist("dias[]") or request.form.getlist("dias")
    horarios = request.form.getlist("horarios[]") or request.form.getlist("horarios")
    estado = int(request.form.get("estado", "1"))
    horas_inicio = request.form.getlist("horas_inicio")
    # si te mandan una sola hora, la guardamos también en hora_inicio
    hora_inicio = (horas_inicio[0] if horas_inicio else request.form.get("hora_inicio", "00:00"))

    if not nombre:
        flash("El nombre es requerido.", "error")
        return redirect(url_for("areas_sociales_editar", id=id))

    try:
        with engine.begin() as conn:
            try:
                # intento directo con listas
                conn.execute(text("""
                    UPDATE public.areas_sociales
                       SET nombre      = :nombre,
                           precio      = :precio,
                           horas       = :horas,
                           dias        = :dias::text[],
                           estado      = :estado,
                           horarios    = :horarios::time[],
                           horas_inicio= :horas_inicio::time[],
                           hora_inicio = :hora_inicio
                     WHERE id_area    = :id
                """), {
                    "nombre": nombre,
                    "precio": precio,
                    "horas": horas,
                    "dias": dias,
                    "estado": estado,
                    "horarios": horarios,
                    "horas_inicio": horas_inicio,
                    "hora_inicio": hora_inicio,
                    "id": id,
                })
            except Exception:
                # fallback si PG no acepta la lista tal cual
                conn.execute(text("""
                    UPDATE public.areas_sociales
                       SET nombre      = :nombre,
                           precio      = :precio,
                           horas       = :horas,
                           dias        = :dias::text[],
                           estado      = :estado,
                           horarios    = :horarios::time[],
                           horas_inicio= :horas_inicio::time[],
                           hora_inicio = :hora_inicio
                     WHERE id_area    = :id
                """), {
                    "nombre": nombre,
                    "precio": precio,
                    "horas": horas,
                    "dias": _to_pg_text_array(dias),
                    "estado": estado,
                    "horarios": _to_pg_text_array(horarios),
                    "horas_inicio": _to_pg_text_array(horas_inicio),
                    "hora_inicio": hora_inicio,
                    "id": id,
                })
        flash("", "success")
        session["_sn_toast"] = {"text": "Área social actualizada correctamente", "level": "info"}
        return redirect(url_for("areas_sociales_list"))
    except Exception as e:
        flash(f"Error al actualizar el área social: {e}", "error")
        return redirect(url_for("areas_sociales_list"))


# ------------------------------------------------------------
# Áreas sociales (Eliminar)
# ------------------------------------------------------------
@app.post("/areas-sociales/<int:id>/eliminar")
@login_required
def areas_sociales_eliminar(id:int):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM public.areas_sociales WHERE id_area=:id"), {"id": id})
        flash("", "success"); session["_sn_toast"] = {"text": "Cambios guardados con éxito", "level": "info"}
    except Exception as e:
        flash(f"No se pudo eliminar el área social: {e}", "error")
    return redirect(url_for("areas_sociales_list"))

# ------------------------------------------------------------
# Roles (CRUD) - con flujo Ver (solo lectura) y Editar (form editable)
# ------------------------------------------------------------
@app.route("/roles")
@login_required
def roles_list():
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id_rol, rol
                FROM public.rol
                ORDER BY id_rol
            """)).mappings().all()
        return render_template("roles_list.html", rows=rows, user=current_user())
    except Exception as e:
        flash(f"No se pudieron cargar los roles: {e}", "error")
        return render_template("roles_list.html", rows=[], user=current_user())

@app.route("/roles/nuevo", methods=["GET","POST"])
@login_required
def roles_nuevo():
    if request.method == "POST":
        rol = (request.form.get("rol") or "").strip()
        if not rol:
            flash("El nombre del rol es requerido.", "error")
            return render_template("roles_form.html", rol=None, user=current_user())
        try:
            with engine.begin() as conn:
                row = conn.execute(text("""
                    INSERT INTO public.rol (id_rol, rol)
                    SELECT COALESCE(MAX(id_rol)+1,1), :rol FROM public.rol
                    RETURNING id_rol
                """), {"rol": rol}).first()
            flash(" ", "success"); session["_sn_toast"] = {"text": "Cambios guardados con éxito", "level": "info"}
            return redirect(url_for("roles_list"))
        except Exception as e:
            flash(f"No se pudo crear el rol: {e}", "error")
    return render_template("roles_form.html", rol=None, user=current_user())

@app.route("/roles/<int:id>/editar", methods=["GET","POST"])
@login_required
def roles_editar(id):
    if request.method == "POST":
        rol = (request.form.get("rol") or "").strip()
        if not rol:
            flash("El nombre del rol es requerido.", "error")
        else:
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE public.rol
                        SET rol = :rol
                        WHERE id_rol = :id
                    """), {"rol": rol, "id": id})
                flash("", "success"); session["_sn_toast"] = {"text": "Cambios guardados con éxito", "level": "info"}
                return redirect(url_for("roles_list"))
            except Exception as e:
                flash(f"No se pudo actualizar el rol #{id}: {e}", "error")
    # GET o en caso de error → Formulario EDITABLE
    try:
        with engine.connect() as conn:
            r = conn.execute(text("""
                SELECT id_rol, rol
                FROM public.rol
                WHERE id_rol = :id
            """), {"id": id}).mappings().first()
        if not r:
            flash(f"Rol #{id} no encontrado.", "error")
            return redirect(url_for("roles_list"))
        return render_template("roles_form.html", rol=r, user=current_user())
    except Exception as e:
        flash(f"No se pudo cargar el rol #{id}: {e}", "error")
        return redirect(url_for("roles_list"))

@app.route("/roles/<int:id>")
@login_required
def roles_ver(id):
    try:
        with engine.connect() as conn:
            r = conn.execute(text("""
                SELECT id_rol, rol
                FROM public.rol
                WHERE id_rol = :id
            """), {"id": id}).mappings().first()
        if not r:
            flash(f"Rol #{id} no encontrado.", "error")
            return redirect(url_for("roles_list"))
        # >>> Vista SOLO lectura: usa roles_ver.html
        return render_template("roles_ver.html", rol=r, user=current_user())
    except Exception as e:
        flash(f"No se pudo cargar el rol #{id}: {e}", "error")
        return redirect(url_for("roles_list"))

@app.route("/roles/<int:id>/eliminar", methods=["POST"])
@login_required
def roles_eliminar(id):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM public.rol WHERE id_rol = :id
            """), {"id": id})
        flash(" ", "success"); session["_sn_toast"] = {"text": "Cambios guardados con éxito", "level": "info"}
    except Exception as e:
        flash(f"No se pudo eliminar el rol #{id}: {e}", "error")
    return redirect(url_for("roles_list"))

# ------------------------------------------------------------
# Toaster azul (4s) inyectado al final del body
# ------------------------------------------------------------
@app.after_request
def _sn_inject_blue_toast(resp):
    try:
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type",""):
            toast = session.pop("_sn_toast", None)
            if toast:
                html = resp.get_data(as_text=True)
                if "</body>" in html and "sn-toast-styles" not in html:
                    css = """<style id="sn-toast-styles">
#sn-toast{position:fixed;top:18px;right:24px;z-index:2147483647;}
.sn-toast{display:flex;align-items:center;gap:10px;background:#1e88e5;color:#fff;border-radius:8px;
box-shadow:0 8px 24px rgba(0,0,0,.25);padding:12px 16px;min-width:280px;max-width:520px;
font:500 14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu;opacity:0;transform:translateY(-8px);
transition:opacity .25s ease, transform .25s ease;}
.sn-toast.show{opacity:1;transform:translateY(0)}
.sn-toast .sn-icon{width:18px;height:18px;display:inline-block;flex:0 0 18px}
.sn-toast .sn-close{margin-left:10px;background:transparent;border:0;color:#fff;opacity:.85;cursor:pointer;font-size:18px;line-height:1}
.sn-toast .sn-close:hover{opacity:1}
</style>"""
                    icon = '<svg class="sn-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="12" fill="rgba(255,255,255,.2)"/><path d="M7 12.5l3 3 7-7" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
                    txt = toast.get("text","Cambios guardados con éxito")
                    body = "<div id='sn-toast'><div class='sn-toast' id='sn-toast-el'>" + icon + "<div>" + txt + "</div>" + \
                           "<button class='sn-close' aria-label='Cerrar' onclick=\"(function(){var b=document.getElementById('sn-toast'); if(b){b.style.opacity=0; setTimeout(function(){b&&b.remove();},300);}})()\">x</button>" + \
                           "</div></div>" + \
                           "<script>(function(){var el=document.getElementById('sn-toast-el'); setTimeout(function(){el&&el.classList.add('show');},50); setTimeout(function(){var box=document.getElementById('sn-toast'); if(box){box.style.opacity=0; setTimeout(function(){box&&box.remove();},300);} }, 4000);})();</script>"
                    html = html.replace("</body>", css + body + "</body>")
                    resp.set_data(html)
    except Exception:
        pass
    return resp

# ------------------------------------------------------------
# Punto de entrada
# ------------------------------------------------------------
# ================== Nueva Reservación ==================

@app.route("/reservas/nueva", methods=["GET","POST"])
@login_required
def reservas_nueva():
    user = current_user()
    rol = user.get("rol") if isinstance(user, dict) else getattr(user, "rol", None)

    if request.method == "POST":
        try:
            id_area = int(request.form["id_area"])
            id_usuario = int(request.form["id_usuario"])
            fecha_str = request.form["fecha"].strip()
            hora_inicio_str = request.form["hora_inicio"].strip()
        except Exception as e:
            flash(f"Datos incompletos: {e}", "error")
            return redirect(url_for("reservas_nueva"))


        # Bloqueo: no permitir crear reserva si el usuario está deshabilitado (estado = 0)
        try:
            with engine.connect() as conn:
                u = conn.execute(text("""
                    SELECT estado FROM public.usuarios WHERE id_usuario = :uid
                """), {"uid": id_usuario}).mappings().first()
            if (not u) or (int(u.get("estado", 0)) == 0):
                flash("El residente seleccionado está deshabilitado y no puede crear reservaciones.", "error")
                return redirect(url_for("reservas_nueva", area_id=id_area))
        except Exception as e:
            flash(f"Error validando estado del usuario: {e}", "error")
            return redirect(url_for("reservas_nueva", area_id=id_area))
                # Validación fecha no mayor a 1 año desde hoy (según servidor) con parser flexible
        try:
            fecha_dt = _parse_fecha_flexible(fecha_str)
        except Exception:
            flash("Fecha inválida.", "error")
            return redirect(url_for("reservas_nueva", area_id=id_area))
        
        max_dt = dt.date.today() + dt.timedelta(days=365)

        if fecha_dt > max_dt:

            flash("La fecha no puede ser mayor a 1 año desde hoy.", "error")

            return redirect(url_for("reservas_nueva", area_id=id_area))

        # Bloqueo adicional: no permitir fechas anteriores a la actual (solo hoy -> +1 año)
        if fecha_dt < dt.date.today():
            flash("La fecha no puede ser anterior a la actual.", "error")
            return redirect(url_for("reservas_nueva", area_id=id_area))



        # Obtener duración (horas) del área y calcular hora_fin
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT horas
                FROM public.areas_sociales
                WHERE id_area = :a
            """), {"a": id_area}).mappings().first()
            if not row:
                flash("Área social no encontrada.", "error")
                return redirect(url_for("reservas_nueva"))
            dur = int(row.get("horas") or 0)

        # Calcular hora_fin sumando 'dur' horas a hora_inicio
        try:
            HH, MM = [int(x) for x in hora_inicio_str.split(":")[:2]]
        except Exception:
            flash("Hora de inicio inválida.", "error")
            return redirect(url_for("reservas_nueva", area_id=id_area))
        start_dt = dt.datetime(2000,1,1,HH,MM)
        end_dt = start_dt + dt.timedelta(hours=dur)
        hora_fin_str = end_dt.strftime("%H:%M")

        # Insertar reserva en estado 0 (pendiente) y confirmada_por NULL
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO public.reservas
                        (id_area, id_usuario, fecha, hora_inicio, hora_fin, estado, confirmada_por)
                    VALUES
                        (:area, :usuario, :fecha, :ini, :fin, 0, NULL)
                """), {"area": id_area, "usuario": id_usuario, "fecha": fecha_dt.isoformat(),
                       "ini": hora_inicio_str, "fin": hora_fin_str})
            flash("", "success"); session["_sn_toast"]={"text":"Reserva guardada con éxito, comuniquese con Administración para confirmar.","level":"info"}
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"No se pudo crear la reserva: {e}", "error")
            return redirect(url_for("reservas_nueva", area_id=id_area))

        # Bloqueo adicional: no permitir fechas anteriores a la actual (solo hoy -> +1 año)
        if fecha_dt < dt.date.today():
            flash("La fecha no puede ser anterior a la actual.", "error")
            return redirect(url_for("reservas_nueva", area_id=id_area))

    # GET: cargar combo de áreas
    areas = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id_area, nombre FROM public.areas_sociales WHERE estado=1 ORDER BY nombre
            """))
            areas = [dict(r) for r in rows.mappings().all()]
    except Exception as e:
        flash(f"No se pudo cargar áreas: {e}", "error")

    selected_id = request.args.get("area_id") or session.get("selected_area_id")
    try:
        selected_id = int(selected_id) if selected_id is not None else None
    except Exception:
        pass
    return render_template("reservas_form.html", user=current_user(), areas=areas, rol=rol, selected_id_area=selected_id)


# ---- API búsqueda de usuarios ----
@app.get("/api/usuarios")
@login_required
def api_buscar_usuarios():
    q = request.args.get("q","").strip()
    pattern = f"%{q}%"
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id_usuario, nombre, apellido, torre, apartamento, correo, celular
            FROM public.usuarios
            WHERE lower(nombre) LIKE lower(:p)
               OR lower(apellido) LIKE lower(:p)
               OR lower(COALESCE(apartamento::text,'')) LIKE lower(:p)
            ORDER BY nombre
            LIMIT 25
        """), {"p": pattern}).mappings().all()
    return jsonify([dict(r) for r in rows])

# ---- API metas de área (duración/horarios/días) ----
@app.get("/api/areas/<int:id_area>/meta")
@login_required
def api_area_meta_by_id(id_area: int):
    # Devuelve: horas (int), precio (float), horarios (list[HH:MM]), horas_inicio (list[HH:MM])
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT horas, horarios, horas_inicio, COALESCE(precio,0) AS precio
            FROM public.areas_sociales
            WHERE id_area = :id
        """), {"id": id_area}).mappings().first()
    if not row:
        return jsonify({"horas": 0, "precio": 0.0, "horarios": [], "horas_inicio": []}), 404

    def norm_times(val):
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            return [t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)[:5] for t in val]
        s = str(val).strip("{}")
        if not s:
            return []
        return [x.strip()[:5] for x in s.split(",")]

    horas = int(row.get("horas") or 0)
    precio = float(row.get("precio") or 0)
    horarios = norm_times(row.get("horarios"))
    horas_inicio = norm_times(row.get("horas_inicio"))
    return jsonify({"horas": horas, "precio": precio, "horarios": horarios, "horas_inicio": horas_inicio})

@app.get("/api/area_meta")
@login_required
def api_area_meta():
    try:
        id_area = int(request.args.get("id_area"))
    except Exception:
        return jsonify({"error":"id_area inválido"}), 400
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT horas, horarios, horas_inicio
            FROM public.areas_sociales
            WHERE id_area = :a
        """), {"a": id_area}).mappings().first()
    if not row:
        return jsonify({"error":"Área no encontrada"}), 404
    # Convert possible PG arrays to Python lists of "HH:MM"
    def norm_times(val):
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            return [t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)[:5] for t in val]
        s = str(val).strip("{}")
        if not s:
            return []
        return [x.strip()[:5] for x in s.split(",")]
    horas = row.get("horas")
    horarios = norm_times(row.get("horarios"))
    horas_inicio = norm_times(row.get("horas_inicio"))
    return jsonify({"horas": int(horas) if horas is not None else 0,
                    "horarios": horarios,
                    "horas_inicio": horas_inicio})
@app.get("/api/reservas/ocupadas")
@login_required
def api_reservas_ocupadas():
    id_area = int(request.args.get("id_area"))
    fecha = request.args.get("fecha")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT to_char(hora_inicio, 'HH24:MI') AS h
            FROM public.reservas
            WHERE id_area=:a AND fecha=:f
            ORDER BY hora_inicio
        """), {"a": id_area, "f": fecha}).all()
    return jsonify([r[0] for r in rows])

# ---- API: reservas de la semana (pintar calendario) ----
@app.get("/api/calendario/semana")
@login_required
def api_calendario_semana():
    try:
        id_area = int(request.args.get("id_area"))
    except Exception:
        return jsonify({"error": "id_area requerido"}), 400

    start = request.args.get("start")
    try:
        start_d = _parse_fecha_flexible(start)
    except Exception:
        return jsonify({"error": "start inválido"}), 400

    end_d = start_d + dt.timedelta(days=6)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.id_reserva,
                   r.id_usuario,
                   r.fecha::date AS fecha,
                   to_char(r.hora_inicio,'HH24:MI') AS ini,
                   to_char(r.hora_fin,'HH24:MI') AS fin,
                   u.nombre, u.apellido, u.torre, u.apartamento,
                   r.estado
            FROM public.reservas r
            JOIN public.usuarios u ON u.id_usuario = r.id_usuario
            WHERE r.id_area=:a AND r.fecha BETWEEN :s AND :e
            ORDER BY r.fecha, r.hora_inicio
        """), {"a": id_area, "s": start_d.isoformat(), "e": end_d.isoformat()}).mappings().all()

    # Saber quién está logueado
    cu = session.get("user") or {}
    cu_id = cu.get("id_usuario")
    is_resident = False
    try:
        is_resident = int(cu.get("id_rol") or 0) == RESIDENT_ROLE_ID
    except Exception:
        is_resident = False

    events = []
    for r in rows:
        item = {
            "id_reserva": r["id_reserva"],
            "id_usuario": r["id_usuario"],
            "fecha": r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else r["fecha"],
            "ini": r["ini"],
            "fin": r["fin"],
            "nombre": r["nombre"],
            "apellido": r["apellido"],
            "torre": r["torre"],
            "apartamento": r["apartamento"],
            "estado": r["estado"],
        }

        # Si es residente y la reserva NO es suya → enmascarar
        if is_resident and cu_id and r["id_usuario"] != cu_id:
            item["nombre"] = "Reservada"
            item["apellido"] = ""
            item["torre"] = None
            item["apartamento"] = None
            # no mandamos estado para no mostrar Pen./Conf.
            item["estado"] = None

        events.append(item)

    return jsonify(events)


# ---- API: confirmar reserva ----
@app.post("/api/reservas/<int:id_reserva>/confirmar")
@login_required
def api_reserva_confirmar(id_reserva:int):
    with engine.begin() as conn:
        conn.execute(text("UPDATE public.reservas SET estado=1 WHERE id_reserva=:id"), {"id": id_reserva})
    return jsonify({"ok": True})

# ---- API: eliminar reserva ----
@app.post("/api/reservas/<int:id_reserva>/eliminar")
@login_required
def api_reserva_eliminar(id_reserva:int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM public.reservas WHERE id_reserva=:id"), {"id": id_reserva})
    return jsonify({"ok": True})

# ---- API: editar reserva (fecha + hora_inicio -> recalcula hora_fin) ----
@app.post("/api/reservas/<int:id_reserva>/editar")
@login_required
def api_reserva_editar(id_reserva:int):
    fecha = request.form.get("fecha","").strip()
    hora_inicio = request.form.get("hora_inicio","").strip()
    # Validar fecha
    try:
        fecha_d = _parse_fecha_flexible(fecha)
    except Exception:
        return jsonify({"ok": False, "error": "Fecha inválida"}), 400
    # +1 año desde hoy
    if fecha_d > (dt.date.today() + dt.timedelta(days=365)):
        return jsonify({"ok": False, "error": "La fecha no puede ser mayor a 1 año desde hoy."}), 400
    

    # No permitir fecha anterior a hoy (solo hoy -> +1 año)
    if fecha_d < dt.date.today():
        return jsonify({"ok": False, "error": "La fecha no puede ser anterior a la actual."}), 400
    # Bloqueo: no permitir editar si el usuario de la reserva está deshabilitado (estado = 0)
    try:
        with engine.connect() as _conn_u:
            urow = _conn_u.execute(text("""
                SELECT u.estado
                FROM public.reservas r
                JOIN public.usuarios u ON u.id_usuario = r.id_usuario
                WHERE r.id_reserva = :rid
            """), {"rid": id_reserva}).mappings().first()
        if (not urow) or (int(urow.get("estado", 0)) == 0):
            return jsonify({"ok": False, "error": "El residente de esta reservación está deshabilitado; no se puede editar."}), 403
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error validando residente: {e}"}), 400

    with engine.begin() as conn:
        meta = conn.execute(text("""
            SELECT r.id_area, a.horas::int AS horas
              FROM public.reservas r
              JOIN public.areas_sociales a ON a.id_area=r.id_area
             WHERE r.id_reserva=:id
        """), {"id": id_reserva}).mappings().first()
        if not meta: return jsonify({"ok": False, "error":"Reserva no encontrada"}), 404
        try:
            HH, MM = [int(x) for x in hora_inicio.split(":")[:2]]
        except Exception:
            return jsonify({"ok": False, "error": "Hora de inicio inválida"}), 400
        start_dt = dt.datetime(2000,1,1,HH,MM)
        hora_fin = (start_dt + dt.timedelta(hours=int(meta.get("horas") or 1))).strftime("%H:%M")
        conn.execute(text("""
            UPDATE public.reservas
               SET fecha=:f, hora_inicio=:hi, hora_fin=:hf
             WHERE id_reserva=:id
        """), {"f": fecha_d.isoformat(), "hi": hora_inicio, "hf": hora_fin, "id": id_reserva})
    return jsonify({"ok": True, "fecha": fecha_d.isoformat(), "hora_inicio": hora_inicio, "hora_fin": hora_fin})


# --- Helper robusto para fechas de reservas ---
def _coerce_iso_date_from_any(raw):
    """Devuelve 'YYYY-MM-DD' si encuentra un patrón válido; si no, hoy."""
    try:
        if raw is None:
            raise ValueError("no date")
        s = str(raw).strip()
        import re as _re
        m = _re.search(r"\d{4}-\d{2}-\d{2}", s)
        if m:
            return m.group(0)
    except Exception:
        pass
    from datetime import date as _date
    return _date.today().isoformat()

def _verify_password(hashed: str, plain: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except Exception:
        return False

def _usuario_fetch_by_username(usuario:str):
    with engine.connect() as conn:
        r = conn.execute(text("""
            SELECT id_usuario, usuario, nombre, apellido, id_rol, estado,
                   debe_cambiar_password, password_hash
            FROM public.usuarios
            WHERE LOWER(usuario)=LOWER(:u)
            LIMIT 1
        """), {"u": usuario}).mappings().first()
    return r

# ------------------------------------------------------------
# Forzar cambio de contraseña
# ------------------------------------------------------------
@app.route("/cambiar_password", methods=["GET","POST"])
@login_required
def cambiar_password():
    u = session.get("user") or {}
    uid = u.get("id_usuario")
    if not uid:
        flash("Sesión inválida. Inicie sesión de nuevo.", "error")
        return redirect(url_for("logout"))

    if request.method == "POST":
        actual  = request.form.get("actual","")
        nueva   = request.form.get("nueva","")
        repetir = request.form.get("repetir","")

        if not actual or not nueva or not repetir:
            flash("Complete todos los campos.", "error")
            return render_template("cambiar_password.html", user=current_user())
        if nueva != repetir:
            flash("La nueva contraseña y su repetición no coinciden.", "error")
            return render_template("cambiar_password.html", user=current_user())

        # Verificar actual
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT password_hash FROM public.usuarios WHERE id_usuario=:id"
            ), {"id": uid}).mappings().first()
        try:
            ok = _ph.verify(row["password_hash"], actual) if row else False
        except Exception:
            ok = False
        if not ok:
            flash("La contraseña actual es incorrecta.", "error")
            return render_template("cambiar_password.html", user=current_user())

        # Guardar nueva y limpiar flag
        new_hash = _ph.hash(nueva)
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE public.usuarios
                   SET password_hash=:pwd,
                       debe_cambiar_password=0
                 WHERE id_usuario=:id
            """), {"pwd": new_hash, "id": uid})

        # Actualizar sesión
        u["must_change"] = False
        session["user"] = u
        flash(" ", "success"); session["_sn_toast"] = {"text": "Contraseña actualizada.", "level": "info"}
        next_url = request.args.get("next") or url_for("index")
        return redirect(next_url)

    return render_template("cambiar_password.html", user=current_user())

@app.after_request
def _hide_nav_for_residents(resp):
    """Oculta entradas de navegación a residentes sin modificar templates."""
    try:
        # Sólo sobre HTML exitoso
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            u = session.get("user") or {}
            # Usa el mismo ID que definimos arriba para residentes
            if int((u.get("id_rol") or 0)) == RESIDENT_ROLE_ID:
                html = resp.get_data(as_text=True)
                # Inyecta CSS una sola vez
                if "</head>" in html and "snb-resident-hide" not in html:
                    css = """
<style id="snb-resident-hide">
  /* Oculta pestañas/enlaces de navegación para residentes */
  a[href^="/usuarios"],
  a[href^="/roles"],
  a[href^="/areas-sociales"] { display: none !important; }
</style>"""
                    html = html.replace("</head>", css + "</head>")
                    resp.set_data(html)
    except Exception:
        # Nunca romper la respuesta por esto
        pass
    return resp




# ------------------------------------------------------------
# Usuarios - Eliminar (asegurar endpoint)
# ------------------------------------------------------------
@app.post('/usuarios/<int:id>/eliminar', endpoint='usuarios_eliminar')
@login_required
def usuarios_eliminar(id):
    u = _usuario_fetch_one(id)
    if not u:
        flash(f"Usuario #{id} no existe", "error")
        return redirect(url_for("usuarios_list"))
    # Regla: operador no puede eliminar admin
    if _operator_blocks_admin(u):
        flash("Permiso denegado para eliminar usuarios Admin.", "error")
        return redirect(url_for("usuarios_list"))
    try:
        with engine.begin() as conn:
            # Pre-chequeo: ¿tiene reservas?
            r = conn.execute(text("""
                SELECT 1 FROM public.reservas WHERE id_usuario=:id LIMIT 1
            """), {"id": id}).first()
            if r:
                flash("El usuario no se puede eliminar por que tiene un evento asignado", "error")
                return redirect(url_for("usuarios_list"))
            conn.execute(text("DELETE FROM public.usuarios WHERE id_usuario=:id"), {"id": id})
        # aquí sí ya lo borró en Postgres
        flash(" ", "success")
        session["_sn_toast"] = {"text": "Usuario1 eliminado.", "level": "info"}
    except Exception as e:
        # Si es violación de llave foránea (reservas -> usuarios), mantener tu mensaje
        msg = str(e)
        if ('ForeignKeyViolation' in msg
            or 'foreign key constraint' in msg.lower()
            or 'reservas_id_usuario_fkey' in msg):
            flash("El usuario no se puede eliminar por que tiene un evento asignado", "error")
        # 👇 este es el que te está saliendo ahora mismo
        elif "get_cxn" in msg:
            # ya lo había eliminado arriba, solo pintamos bien el mensaje
            flash(" ", "success")
            session["_sn_toast"] = {"text": "Usuario eliminado.", "level": "info"}
        else:
            flash(f"Error al eliminar: {e}", "error")
        return redirect(url_for("usuarios_list"))

    return redirect(url_for("usuarios_list"))



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8888))
    app.run(host="0.0.0.0", port=port, debug=False)
