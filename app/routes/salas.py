"""Rutas web y estado en vivo para crear sala con código y unirse desde celular."""

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.auth import SESSION_USER_ID, usuario_actual
from app.db import db
from app.models import DIFICULTADES_VALIDAS, FIGURAS, MODOS
from app.salas import (
    DESCRIPCIONES_FIGURA,
    ETIQUETAS_DIFICULTAD,
    ETIQUETAS_FIGURA,
    ETIQUETAS_MODO,
    SalaError,
    buscar_sala,
    crear_sala,
    obtener_tablero_jugador,
    resumen_sala,
    unirse_a_sala,
)

bp = Blueprint("salas", __name__, url_prefix="/salas")


@bp.get("/")
def inicio():
    """Portal de salas con accesos para profesor (crear) y alumno (unirse)."""
    return render_template("salas/inicio.html")


def _opciones_creacion():
    return {
        "figuras": [
            (clave, ETIQUETAS_FIGURA[clave], DESCRIPCIONES_FIGURA[clave])
            for clave in FIGURAS
        ],
        "modos": [(clave, ETIQUETAS_MODO[clave]) for clave in MODOS],
        "dificultades": [
            (clave, ETIQUETAS_DIFICULTAD[clave]) for clave in DIFICULTADES_VALIDAS
        ],
    }


def _username_en_sesion():
    usuario = usuario_actual()
    if usuario is not None:
        return usuario.username
    return session.get("username")


def _guardar_identidad_sala(usuario, usuario_sesion):
    """Actualiza la sesión de sala sin mezclar un `user_id` de otra cuenta."""
    if usuario_sesion is None or usuario_sesion.id != usuario.id:
        session.pop(SESSION_USER_ID, None)
    session["username"] = usuario.username
    session["role"] = usuario.role


@bp.route("/crear", methods=["GET", "POST"])
def crear():
    """Pantalla del profesor para crear una nueva sala con código."""
    usuario_sesion = usuario_actual()
    if request.method == "GET":
        if usuario_sesion is not None and usuario_sesion.role == "profesor":
            username_inicial = usuario_sesion.username
        elif session.get("role") == "profesor":
            username_inicial = session.get("username", "")
        else:
            username_inicial = ""
        valores = {
            "username": username_inicial,
            "figure": "fila",
            "mode": "manual",
            "difficulty": "normal",
        }
        return render_template(
            "salas/crear.html",
            valores=valores,
            error=None,
            requiere_login=False,
            **_opciones_creacion(),
        )

    valores = {
        "username": (request.form.get("username") or "").strip(),
        "figure": request.form.get("figure", "fila"),
        "mode": request.form.get("mode", "manual"),
        "difficulty": request.form.get("difficulty", "normal"),
    }
    try:
        partida, profesor = crear_sala(
            nombre_profesor=valores["username"],
            figure=valores["figure"],
            difficulty=valores["difficulty"],
            mode=valores["mode"],
            usuario_autenticado=usuario_sesion,
        )
    except SalaError as err:
        db.session.rollback()
        return (
            render_template(
                "salas/crear.html",
                valores=valores,
                error=err.message,
                requiere_login=err.status == 401,
                **_opciones_creacion(),
            ),
            err.status,
        )

    _guardar_identidad_sala(profesor, usuario_sesion)
    return redirect(url_for("salas.ver_sala", code=partida.code))


@bp.route("/unirse", methods=["GET", "POST"])
def unirse():
    """Pantalla mobile-first para que un alumno se una a una sala por código."""
    usuario_sesion = usuario_actual()
    if request.method == "GET":
        codigo_inicial = "".join((request.args.get("code") or "").split()).upper()
        if usuario_sesion is not None:
            nombre_inicial = usuario_sesion.username
        elif session.get("role") == "jugador":
            nombre_inicial = session.get("username", "")
        else:
            nombre_inicial = ""
        sala_preview = None
        aviso = None
        if codigo_inicial:
            try:
                partida = buscar_sala(codigo_inicial)
                sala_preview = resumen_sala(partida)
                if partida.status == "terminada":
                    aviso = (
                        "Esta partida ya terminó. Solo los alumnos que ya tenían "
                        "tablero pueden entrar a consultarlo."
                    )
            except SalaError as err:
                aviso = err.message

        return render_template(
            "salas/unirse.html",
            valores={"code": codigo_inicial, "username": nombre_inicial},
            sala_preview=sala_preview,
            error=aviso,
            requiere_login=False,
        )

    codigo_crudo = request.form.get("code") or ""
    nombre_crudo = request.form.get("username") or ""
    try:
        partida, _tablero, jugador, _creado = unirse_a_sala(
            codigo_crudo, nombre_crudo, usuario_autenticado=usuario_sesion
        )
    except SalaError as err:
        db.session.rollback()
        return (
            render_template(
                "salas/unirse.html",
                valores={
                    "code": "".join(codigo_crudo.split()).upper(),
                    "username": nombre_crudo.strip(),
                },
                sala_preview=None,
                error=err.message,
                requiere_login=err.status == 401,
            ),
            err.status,
        )

    _guardar_identidad_sala(jugador, usuario_sesion)
    return redirect(url_for("salas.vista_jugador", code=partida.code))


@bp.get("/<code>/unirse")
def unirse_con_codigo(code):
    """Atajo de enlace directo que prellena el código en la pantalla de unión."""
    codigo_limpio = "".join(code.split()).upper()
    return redirect(url_for("salas.unirse", code=codigo_limpio))


@bp.get("/<code>")
def ver_sala(code):
    """Vista de sala: muestra el lobby del profesor o redirige al flujo de alumno."""
    try:
        partida = buscar_sala(code)
    except SalaError as err:
        return (
            render_template(
                "salas/no_encontrada.html",
                codigo="".join(code.split()).upper(),
                error=err.message,
            ),
            err.status,
        )

    usuario_actual_nombre = _username_en_sesion()
    if usuario_actual_nombre and usuario_actual_nombre == partida.host.username:
        enlace_unirse = url_for("salas.unirse", code=partida.code, _external=True)
        return render_template(
            "salas/profesor.html",
            sala=resumen_sala(partida),
            enlace_unirse=enlace_unirse,
        )

    if (
        usuario_actual_nombre
        and obtener_tablero_jugador(partida, usuario_actual_nombre) is not None
    ):
        return redirect(url_for("salas.vista_jugador", code=partida.code))

    return redirect(url_for("salas.unirse", code=partida.code))


@bp.get("/<code>/jugador")
def vista_jugador(code):
    """Sala de espera y tablero asignado al alumno en su celular."""
    try:
        partida = buscar_sala(code)
    except SalaError as err:
        return (
            render_template(
                "salas/no_encontrada.html",
                codigo="".join(code.split()).upper(),
                error=err.message,
            ),
            err.status,
        )

    usuario_actual_nombre = _username_en_sesion()
    tablero = obtener_tablero_jugador(partida, usuario_actual_nombre)
    if tablero is None:
        return redirect(url_for("salas.unirse", code=partida.code))

    return render_template(
        "salas/jugador.html",
        sala=resumen_sala(partida),
        jugador=usuario_actual_nombre,
        tablero=tablero,
    )


@bp.get("/<code>/estado")
def estado_sala(code):
    """JSON ligero para actualizar jugadores conectados y estado de la sala."""
    try:
        partida = buscar_sala(code)
    except SalaError as err:
        return jsonify({"error": err.message}), err.status

    return jsonify(resumen_sala(partida))
