"""Autenticación real basada en sesiones de Flask y contraseñas con hash.

Reemplaza el esquema temporal basado en `X-User-Id` manteniendo la misma
interfaz (`require_host` y `require_player` dejan al usuario en `g.user`),
para que las rutas de `/api/games` funcionen sin cambios.
"""

from functools import wraps

from flask import g, session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import db
from app.errors import ApiError
from app.models import ROLES, User

SESSION_USER_ID = "user_id"
MIN_LARGO_PASSWORD = 6
MAX_LARGO_PASSWORD = 128
MAX_LARGO_USERNAME = 80

# Ningún hash real empieza con "!": bloquea inicio de sesión con hashes temporales.
_SIN_PASSWORD = "!temporal-sin-password"


def normalizar_username(username):
    """Limpia y valida el nombre de usuario."""
    if not isinstance(username, str):
        raise ApiError(400, "Ingresa un nombre de usuario.")
    limpio = username.strip()
    if not limpio:
        raise ApiError(400, "Ingresa un nombre de usuario.")
    if len(limpio) > MAX_LARGO_USERNAME:
        raise ApiError(
            400,
            f"El nombre de usuario no puede tener más de {MAX_LARGO_USERNAME} caracteres.",
        )
    return limpio


def validar_password(password):
    """Valida que la contraseña cumpla la longitud permitida."""
    if not isinstance(password, str) or not password:
        raise ApiError(400, "Ingresa una contraseña.")
    if len(password) < MIN_LARGO_PASSWORD:
        raise ApiError(
            400, f"La contraseña debe tener al menos {MIN_LARGO_PASSWORD} caracteres."
        )
    if len(password) > MAX_LARGO_PASSWORD:
        raise ApiError(
            400,
            f"La contraseña no puede tener más de {MAX_LARGO_PASSWORD} caracteres.",
        )
    return password


def validar_rol(role):
    """Valida que el rol pertenezca a los roles permitidos."""
    if not isinstance(role, str) or role not in ROLES:
        raise ApiError(
            400, f"Rol inválido: {role!r}. Válidos: {', '.join(ROLES)}."
        )
    return role


def registrar_usuario(username, password, role="jugador"):
    """Crea un usuario nuevo con contraseña hasheada y lo guarda en la base."""
    nombre = normalizar_username(username)
    clave = validar_password(password)
    rol = validar_rol(role)

    if db.session.query(User).filter_by(username=nombre).one_or_none() is not None:
        raise ApiError(409, "Ese nombre de usuario ya está registrado.")

    usuario = User(
        username=nombre,
        password_hash=generate_password_hash(clave),
        role=rol,
    )
    try:
        with db.session.begin_nested():
            db.session.add(usuario)
    except IntegrityError as exc:
        raise ApiError(409, "Ese nombre de usuario ya está registrado.") from exc

    db.session.commit()
    return usuario


def autenticar_usuario(username, password):
    """Verifica credenciales y devuelve el usuario si son válidas."""
    nombre = normalizar_username(username)
    if not isinstance(password, str) or not password:
        raise ApiError(400, "Ingresa tu contraseña.")

    usuario = db.session.query(User).filter_by(username=nombre).one_or_none()
    if (
        usuario is None
        or usuario.password_hash.startswith("!")
        or not check_password_hash(usuario.password_hash, password)
    ):
        raise ApiError(401, "Usuario o contraseña incorrectos.")

    return usuario


def iniciar_sesion(usuario):
    """Guarda el usuario autenticado en la sesión (limpiando datos previos)."""
    session.clear()
    session[SESSION_USER_ID] = usuario.id
    session["username"] = usuario.username
    session["role"] = usuario.role


def cerrar_sesion():
    """Elimina la sesión actual."""
    session.clear()


def usuario_actual():
    """Devuelve el usuario autenticado en la sesión actual, o None."""
    user_id = session.get(SESSION_USER_ID)
    if type(user_id) is not int:
        return None
    usuario = db.session.get(User, user_id)
    if usuario is None:
        session.clear()
        return None
    return usuario


def usuario_json(usuario):
    """Representación pública segura del usuario (sin exponer password_hash)."""
    return {
        "id": usuario.id,
        "username": usuario.username,
        "role": usuario.role,
    }


def require_login(vista):
    """Exige cualquier usuario autenticado en sesión y lo deja en `g.user`."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = usuario_actual()
        if usuario is None:
            raise ApiError(401, "Debes iniciar sesión para continuar.")
        g.user = usuario
        return vista(*args, **kwargs)

    return envoltura


def require_host(vista):
    """Rutas del profesor. Exige sesión autenticada con rol `profesor`."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = usuario_actual()
        if usuario is None:
            raise ApiError(401, "Debes iniciar sesión para continuar.")
        if usuario.role != "profesor":
            raise ApiError(403, "Solo un profesor puede hacer esto.")
        g.user = usuario
        return vista(*args, **kwargs)

    return envoltura


def require_player(vista):
    """Rutas del jugador. Exige sesión autenticada."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = usuario_actual()
        if usuario is None:
            raise ApiError(401, "Debes iniciar sesión para continuar.")
        g.user = usuario
        return vista(*args, **kwargs)

    return envoltura
