"""Rutas web y estado en vivo para crear sala con código y unirse desde celular."""

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

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


@bp.route("/crear", methods=["GET", "POST"])
def crear():
    """Pantalla del profesor para crear una nueva sala con código."""
    if request.method == "GET":
        username_inicial = (
            session.get("username", "") if session.get("role") == "profesor" else ""
        )
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
        )
    except SalaError as err:
        db.session.rollback()
        return (
            render_template(
                "salas/crear.html",
                valores=valores,
                error=err.message,
                **_opciones_creacion(),
            ),
            err.status,
        )

    session["username"] = profesor.username
    session["role"] = profesor.role
    return redirect(url_for("salas.ver_sala", code=partida.code))


@bp.route("/unirse", methods=["GET", "POST"])
def unirse():
    """Pantalla mobile-first para que un alumno se una a una sala por código."""
    if request.method == "GET":
        codigo_inicial = "".join((request.args.get("code") or "").split()).upper()
        nombre_inicial = (
            session.get("username", "") if session.get("role") == "jugador" else ""
        )
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
        )

    codigo_crudo = request.form.get("code") or ""
    nombre_crudo = request.form.get("username") or ""
    try:
        partida, _tablero, jugador, _creado = unirse_a_sala(codigo_crudo, nombre_crudo)
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
            ),
            err.status,
        )

    session["username"] = jugador.username
    session["role"] = jugador.role
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

    usuario_actual = session.get("username")
    if usuario_actual and usuario_actual == partida.host.username:
        enlace_unirse = url_for("salas.unirse", code=partida.code, _external=True)
        return render_template(
            "salas/profesor.html",
            sala=resumen_sala(partida),
            enlace_unirse=enlace_unirse,
        )

    if usuario_actual and obtener_tablero_jugador(partida, usuario_actual) is not None:
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

    usuario_actual = session.get("username")
    tablero = obtener_tablero_jugador(partida, usuario_actual)
    if tablero is None:
        return redirect(url_for("salas.unirse", code=partida.code))

    return render_template(
        "salas/jugador.html",
        sala=resumen_sala(partida),
        jugador=usuario_actual,
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
