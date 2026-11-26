"""Rutas web y API JSON de registro, inicio y cierre de sesión."""

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from app.auth import (
    autenticar_usuario,
    cerrar_sesion,
    iniciar_sesion,
    registrar_usuario,
    usuario_actual,
    usuario_json,
)
from app.db import db
from app.errors import ApiError, respuesta_de_error

bp = Blueprint("auth", __name__)
bp.register_error_handler(ApiError, respuesta_de_error)


def _json_body():
    if not request.get_data():
        return {}
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ApiError(400, "El cuerpo debe ser un objeto JSON.")
    return datos


def _destino_seguro(destino):
    """Permite redirigir solo a rutas internas relativas (evita open redirect)."""
    if (
        isinstance(destino, str)
        and destino.startswith("/")
        and not destino.startswith("//")
        and "\\" not in destino
    ):
        return destino
    return url_for("auth.cuenta")


# ---------- API JSON (/api/auth/*) ----------


@bp.post("/api/auth/register")
def api_register():
    datos = _json_body()
    usuario = registrar_usuario(
        username=datos.get("username"),
        password=datos.get("password"),
        role=datos.get("role", "jugador"),
    )
    iniciar_sesion(usuario)
    return jsonify({"user": usuario_json(usuario)}), 201


@bp.post("/api/auth/login")
def api_login():
    datos = _json_body()
    usuario = autenticar_usuario(
        username=datos.get("username"),
        password=datos.get("password"),
    )
    iniciar_sesion(usuario)
    return jsonify({"user": usuario_json(usuario)})


@bp.post("/api/auth/logout")
def api_logout():
    cerrar_sesion()
    return jsonify({"ok": True})


@bp.get("/api/auth/me")
def api_me():
    usuario = usuario_actual()
    if usuario is None:
        raise ApiError(401, "No hay sesión activa.")
    return jsonify({"authenticated": True, "user": usuario_json(usuario)})


# ---------- Pantallas web (/auth/*) ----------


@bp.route("/auth/registro", methods=["GET", "POST"])
def registro():
    siguiente = request.args.get("next") or request.form.get("next") or ""
    if request.method == "GET":
        if usuario_actual() is not None:
            return redirect(_destino_seguro(siguiente))
        return render_template(
            "auth/registro.html",
            valores={"username": "", "role": "jugador", "next": siguiente},
            error=None,
        )

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    role = request.form.get("role", "jugador")
    valores = {"username": username, "role": role, "next": siguiente}

    if password != confirm:
        return (
            render_template(
                "auth/registro.html",
                valores=valores,
                error="Las contraseñas no coinciden.",
            ),
            400,
        )

    try:
        usuario = registrar_usuario(username=username, password=password, role=role)
    except ApiError as err:
        db.session.rollback()
        return (
            render_template(
                "auth/registro.html",
                valores=valores,
                error=err.message,
            ),
            err.status,
        )

    iniciar_sesion(usuario)
    return redirect(_destino_seguro(siguiente))


@bp.route("/auth/login", methods=["GET", "POST"])
def login():
    siguiente = request.args.get("next") or request.form.get("next") or ""
    if request.method == "GET":
        if usuario_actual() is not None:
            return redirect(_destino_seguro(siguiente))
        return render_template(
            "auth/login.html",
            valores={"username": "", "next": siguiente},
            error=None,
        )

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    valores = {"username": username, "next": siguiente}

    try:
        usuario = autenticar_usuario(username=username, password=password)
    except ApiError as err:
        return (
            render_template(
                "auth/login.html",
                valores=valores,
                error=err.message,
            ),
            err.status,
        )

    iniciar_sesion(usuario)
    return redirect(_destino_seguro(siguiente))


@bp.post("/auth/logout")
def logout():
    cerrar_sesion()
    return redirect(url_for("auth.login"))


@bp.get("/auth/cuenta")
def cuenta():
    usuario = usuario_actual()
    if usuario is None:
        return redirect(url_for("auth.login"))
    return render_template("auth/cuenta.html", usuario=usuario)
