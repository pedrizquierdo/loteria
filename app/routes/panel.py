"""Rutas web y acciones en vivo del panel del profesor (`/panel/*`).

Todas las rutas exigen autenticación real por sesión (`usuario_actual()` en
`app/auth.py`, basado en `session["user_id"]`) y verifican `partida.host_id`.
"""

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from app.auth import usuario_actual
from app.db import db
from app.errors import ApiError
from app.models import DIFICULTADES_VALIDAS, FIGURAS, MODOS
from app.panel import (
    ETIQUETAS_DIFICULTAD,
    ETIQUETAS_FIGURA,
    ETIQUETAS_MODO,
    actualizar_ajustes_panel,
    buscar_partida_panel,
    estado_panel,
    exigir_anfitrion,
    exigir_profesor,
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
    usuario = usuario_actual()
    if usuario is None:
        destino = request.full_path.rstrip("?")
        return redirect(url_for("auth.login", next=destino))
    if usuario.role != "profesor":
        return (
            render_template(
                "panel/no_encontrada.html",
                titulo="Acceso restringido",
                error="Solo un profesor con sesión iniciada puede usar el panel de control.",
            ),
            403,
        )

    codigo_inicial = "".join((request.args.get("code") or "").split()).upper()
    partidas = listar_partidas_profesor(usuario)
    return render_template(
        "panel/acceso.html",
        usuario=usuario,
        valores={"code": codigo_inicial},
        partidas=partidas,
        error=None,
    )


@bp.post("/acceder")
def acceder():
    usuario = usuario_actual()
    codigo = request.form.get("code") or ""

    try:
        exigir_profesor(usuario)
        partida = buscar_partida_panel(codigo)
        exigir_anfitrion(partida, usuario)
    except ApiError as err:
        if _quiere_json():
            return jsonify({"error": err.message}), err.status
        if err.status in (401, 403) and (usuario is None or usuario.role != "profesor"):
            return (
                render_template(
                    "panel/no_encontrada.html",
                    titulo="Acceso restringido",
                    error=err.message,
                ),
                err.status,
            )
        return (
            render_template(
                "panel/acceso.html",
                usuario=usuario,
                valores={"code": "".join(codigo.split()).upper()},
                partidas=listar_partidas_profesor(usuario),
                error=err.message,
            ),
            err.status,
        )

    return redirect(url_for("panel.control", code=partida.code))


@bp.get("/<code>")
def control(code):
    usuario = usuario_actual()
    codigo_limpio = "".join(code.split()).upper()
    if usuario is None:
        return redirect(
            url_for("auth.login", next=url_for("panel.control", code=codigo_limpio))
        )

    try:
        exigir_profesor(usuario)
        partida = buscar_partida_panel(codigo_limpio)
        exigir_anfitrion(partida, usuario)
    except ApiError as err:
        titulo = "Acceso restringido" if err.status == 403 else "Partida no encontrada"
        return (
            render_template(
                "panel/no_encontrada.html",
                titulo=titulo,
                error=err.message,
            ),
            err.status,
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
    usuario = usuario_actual()
    try:
        datos = sincronizar_y_obtener_estado(code, usuario)
    except ApiError as err:
        return jsonify({"error": err.message}), err.status
    return jsonify(datos)


@bp.post("/<code>/iniciar")
def iniciar(code):
    usuario = usuario_actual()
    try:
        datos = iniciar_partida_panel(code, usuario)
    except ApiError as err:
        db.session.rollback()
        if _quiere_json():
            return jsonify({"error": err.message}), err.status
        return _responder_error_html(code, err)

    if _quiere_json():
        return jsonify(datos)
    return redirect(url_for("panel.control", code=datos["code"]))


@bp.post("/<code>/siguiente-carta")
def siguiente_carta(code):
    usuario = usuario_actual()
    try:
        datos = siguiente_carta_panel(code, usuario)
    except ApiError as err:
        db.session.rollback()
        if _quiere_json():
            return jsonify({"error": err.message}), err.status
        return _responder_error_html(code, err)

    if _quiere_json():
        return jsonify(datos)
    return redirect(url_for("panel.control", code=datos["code"]))


@bp.post("/<code>/ajustes")
def ajustes(code):
    usuario = usuario_actual()
    try:
        cambios = _datos_peticion()
        datos = actualizar_ajustes_panel(code, usuario, cambios)
    except ApiError as err:
        db.session.rollback()
        if _quiere_json():
            return jsonify({"error": err.message}), err.status
        return _responder_error_html(code, err)

    if _quiere_json():
        return jsonify(datos)
    return redirect(url_for("panel.control", code=datos["code"]))


def _responder_error_html(code, err):
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
