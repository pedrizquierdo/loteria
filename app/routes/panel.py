"""Rutas web y acciones en vivo del panel del profesor (`/panel/*`)."""

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.db import db
from app.errors import ApiError
from app.models import DIFICULTADES_VALIDAS, FIGURAS, MODOS, User
from app.panel import (
    ETIQUETAS_DIFICULTAD,
    ETIQUETAS_FIGURA,
    ETIQUETAS_MODO,
    actualizar_ajustes_panel,
    buscar_partida_panel,
    estado_panel,
    exigir_anfitrion_por_nombre,
    iniciar_partida_panel,
    listar_partidas_profesor,
    siguiente_carta_panel,
    sincronizar_y_obtener_estado,
)

bp = Blueprint("panel", __name__, url_prefix="/panel")


def _quiere_json():
    if request.is_json:
        return True
    mejor = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return (
        mejor == "application/json"
        and request.accept_mimetypes["application/json"]
        > request.accept_mimetypes["text/html"]
    )


def _usuario_sesion():
    """Obtiene el nombre de usuario de la sesión (compatible con login real y salas)."""
    user_id = session.get("user_id")
    if type(user_id) is int:
        usuario = db.session.get(User, user_id)
        if usuario is not None:
            return usuario.username
    username = session.get("username")
    return username.strip() if isinstance(username, str) and username.strip() else None


def _opciones_panel():
    return {
        "figuras": [(k, ETIQUETAS_FIGURA[k]) for k in FIGURAS],
        "modos": [(k, ETIQUETAS_MODO[k]) for k in MODOS],
        "dificultades": [(k, ETIQUETAS_DIFICULTAD[k]) for k in DIFICULTADES_VALIDAS],
    }


def _datos_peticion():
    if request.is_json:
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            raise ApiError(400, "El cuerpo debe ser un objeto JSON.")
        return datos
    return request.form.to_dict()


@bp.get("/")
def acceso():
    usuario = _usuario_sesion()
    codigo_inicial = "".join((request.args.get("code") or "").split()).upper()
    partidas = listar_partidas_profesor(usuario)
    return render_template(
        "panel/acceso.html",
        valores={"code": codigo_inicial, "username": usuario or ""},
        partidas=partidas,
        error=None,
    )


@bp.post("/acceder")
def acceder():
    codigo = request.form.get("code") or ""
    username_sesion = _usuario_sesion()
    username_form = (request.form.get("username") or "").strip()
    # Si ya hay sesión autenticada con user_id, prioriza esa identidad.
    username = username_sesion if session.get("user_id") else (username_form or username_sesion or "")

    try:
        partida = buscar_partida_panel(codigo)
        exigir_anfitrion_por_nombre(partida, username)
    except ApiError as err:
        return (
            render_template(
                "panel/acceso.html",
                valores={"code": "".join(codigo.split()).upper(), "username": username},
                partidas=listar_partidas_profesor(username_sesion),
                error=err.message,
            ),
            err.status,
        )

    session["username"] = partida.host.username
    session["role"] = partida.host.role
    return redirect(url_for("panel.control", code=partida.code))


@bp.get("/<code>")
def control(code):
    usuario = _usuario_sesion()
    try:
        partida = buscar_partida_panel(code)
    except ApiError as err:
        return (
            render_template(
                "panel/no_encontrada.html",
                titulo="Partida no encontrada",
                error=err.message,
            ),
            err.status,
        )

    if not usuario:
        return redirect(url_for("panel.acceso", code=partida.code))

    if partida.host.username != usuario:
        return (
            render_template(
                "panel/no_encontrada.html",
                titulo="Acceso restringido",
                error="Solo el profesor que creó esta partida puede abrir su panel de control.",
            ),
            403,
        )

    datos = sincronizar_y_obtener_estado(partida.code, usuario)
    return render_template(
        "panel/control.html",
        panel=datos,
        error=None,
        **_opciones_panel(),
    )


@bp.get("/<code>/estado")
def estado(code):
    usuario = _usuario_sesion()
    try:
        datos = sincronizar_y_obtener_estado(code, usuario)
    except ApiError as err:
        return jsonify({"error": err.message}), err.status
    return jsonify(datos)


@bp.post("/<code>/iniciar")
def iniciar(code):
    usuario = _usuario_sesion()
    try:
        datos = iniciar_partida_panel(code, usuario)
    except ApiError as err:
        db.session.rollback()
        if _quiere_json():
            return jsonify({"error": err.message}), err.status
        return _responder_error_html(code, usuario, err)

    if _quiere_json():
        return jsonify(datos)
    return redirect(url_for("panel.control", code=datos["code"]))


@bp.post("/<code>/siguiente-carta")
def siguiente_carta(code):
    usuario = _usuario_sesion()
    try:
        datos = siguiente_carta_panel(code, usuario)
    except ApiError as err:
        db.session.rollback()
        if _quiere_json():
            return jsonify({"error": err.message}), err.status
        return _responder_error_html(code, usuario, err)

    if _quiere_json():
        return jsonify(datos)
    return redirect(url_for("panel.control", code=datos["code"]))


@bp.post("/<code>/ajustes")
def ajustes(code):
    usuario = _usuario_sesion()
    try:
        cambios = _datos_peticion()
        datos = actualizar_ajustes_panel(code, usuario, cambios)
    except ApiError as err:
        db.session.rollback()
        if _quiere_json():
            return jsonify({"error": err.message}), err.status
        return _responder_error_html(code, usuario, err)

    if _quiere_json():
        return jsonify(datos)
    return redirect(url_for("panel.control", code=datos["code"]))


def _responder_error_html(code, usuario, err):
    if err.status in (401, 403, 404):
        return (
            render_template(
                "panel/no_encontrada.html",
                titulo="No se pudo completar la acción",
                error=err.message,
            ),
            err.status,
        )
    partida = buscar_partida_panel(code)
    return (
        render_template(
            "panel/control.html",
            panel=estado_panel(partida),
            error=err.message,
            **_opciones_panel(),
        ),
        err.status,
    )
