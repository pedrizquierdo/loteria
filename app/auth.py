"""Autenticación TEMPORAL basada en el encabezado X-User-Id.

ATENCIÓN: esto NO es seguro. Cualquiera puede mandar el encabezado que quiera.
Existe solo para poder jugar mientras se implementa el login real (otro
ticket). Cuando exista, basta con reemplazar `require_host` y
`require_player` (misma firma: dejan el usuario en `g.user`); las rutas
no necesitan cambiar.

- El cliente manda `X-User-Id: <nombre de usuario>` en cada petición.
- Si el usuario no existe, se crea (profesor en rutas de host, jugador en
  rutas de jugador) con un password_hash inutilizable.
"""

from functools import wraps

from flask import g, request
from sqlalchemy.exc import IntegrityError

from app.db import db
from app.errors import ApiError
from app.models import User

ENCABEZADO = "X-User-Id"
# Ningún hash real empieza con "!": así nadie puede iniciar sesión con él.
_SIN_PASSWORD = "!temporal-sin-password"


def _usuario_del_encabezado(rol_si_es_nuevo):
    nombre = (request.headers.get(ENCABEZADO) or "").strip()
    if not nombre:
        raise ApiError(401, f"Falta el encabezado {ENCABEZADO}.")
    if len(nombre) > 80:
        raise ApiError(400, f"{ENCABEZADO} no puede tener más de 80 caracteres.")

    usuario = db.session.query(User).filter_by(username=nombre).one_or_none()
    if usuario is not None:
        return usuario
    try:
        # SAVEPOINT: si otra petición crea al mismo usuario a la vez,
        # solo se deshace este INSERT y se lee el que ganó.
        with db.session.begin_nested():
            usuario = User(
                username=nombre, password_hash=_SIN_PASSWORD, role=rol_si_es_nuevo
            )
            db.session.add(usuario)
    except IntegrityError:
        usuario = db.session.query(User).filter_by(username=nombre).one()
    return usuario


def require_host(vista):
    """Rutas del profesor. TEMPORAL: confía en X-User-Id."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = _usuario_del_encabezado("profesor")
        if usuario.role != "profesor":
            raise ApiError(403, "Solo un profesor puede hacer esto.")
        g.user = usuario
        return vista(*args, **kwargs)

    return envoltura


def require_player(vista):
    """Rutas del jugador. TEMPORAL: confía en X-User-Id."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        g.user = _usuario_del_encabezado("jugador")
        return vista(*args, **kwargs)

    return envoltura
