"""API JSON de la partida (SCRUM-14).

Las reglas (mazo, tableros, figuras) viven en app/game/; aquí solo se
guardan y leen datos. El modo automático no usa hilos: cada GET /state
revisa el reloj y saca las cartas que ya tocaban (ver `_sincronizar_auto`).
"""

import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.auth import require_host, require_player
from app.db import db
from app.errors import ApiError, respuesta_de_error
from app.game import DIFICULTADES, barajar_mazo, generar_tablero, validar_victoria
from app.game.constantes import CARTAS
from app.models import (
    DIFICULTADES_VALIDAS,
    FIGURAS,
    MODOS,
    Board,
    BoardCard,
    CalledCard,
    Game,
    Winner,
)

bp = Blueprint("game", __name__, url_prefix="/api/games")
bp.register_error_handler(ApiError, respuesta_de_error)

TOTAL_CARTAS = len(CARTAS)
# Sin 0/O ni 1/I/L para que se pueda dictar y teclear en el celular.
_ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LARGO_CODIGO = 6
_MAX_SEMILLA = 2**31


# ---------- utilidades ----------


def _ahora():
    return datetime.now(timezone.utc)


def _json_body():
    """Cuerpo JSON como dict; sin cuerpo equivale a {}."""
    if not request.get_data():
        return {}
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ApiError(400, "El cuerpo debe ser un objeto JSON.")
    return datos


def _validar_opcion(datos, campo, validos):
    valor = datos[campo]
    if not isinstance(valor, str) or valor not in validos:
        raise ApiError(
            400, f"Valor inválido para {campo}: {valor!r}. Válidos: {', '.join(validos)}."
        )
    return valor


def _buscar_partida(code, bloquear=False):
    """Busca por código (sin importar mayúsculas). `bloquear` toma un
    SELECT ... FOR UPDATE sobre la fila hasta el commit/rollback."""
    consulta = select(Game).where(Game.code == code.upper())
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    partida = db.session.execute(consulta).scalar_one_or_none()
    if partida is None:
        raise ApiError(404, f"No existe la partida {code!r}.")
    return partida


def _exigir_anfitrion(partida):
    if partida.host_id != g.user.id:
        raise ApiError(403, "Solo el profesor que creó la partida puede hacer esto.")


def _exigir_en_juego(partida):
    if partida.status != "en_juego":
        raise ApiError(409, f"La partida no está en juego (estado: {partida.status}).")


def _cantidad_cantadas(partida):
    return db.session.scalar(
        select(func.count()).select_from(CalledCard).where(CalledCard.game_id == partida.id)
    )


def _cantar(partida, cantidad, momento):
    """Guarda las siguientes `cantidad` cartas del mazo. Requiere la fila de
    la partida bloqueada, para que dos peticiones no saquen la misma carta.
    Devuelve las cartas cantadas."""
    ya = _cantidad_cantadas(partida)
    mazo = barajar_mazo(int(partida.seed))
    nuevas = [
        CalledCard(game_id=partida.id, card_id=carta, order=ya + i + 1, called_at=momento)
        for i, carta in enumerate(mazo[ya : ya + cantidad])
    ]
    db.session.add_all(nuevas)
    return nuevas


def _cartas_pendientes_auto(partida, momento):
    """Cuántas cartas tocaría sacar ahora en modo auto (0 si ninguna)."""
    if (
        partida.status != "en_juego"
        or partida.mode != "auto"
        or partida.last_called_at is None
    ):
        return 0
    intervalo = DIFICULTADES[partida.difficulty]
    transcurrido = (momento - partida.last_called_at).total_seconds()
    return max(0, int(transcurrido // intervalo))


def _sincronizar_auto(code):
    """Reloj del modo auto, sin hilos: si ya pasó el intervalo desde la
    última carta, saca las que tocaban (varias si pasó mucho tiempo, sin
    pasarse del mazo). Solo bloquea la fila cuando de verdad hay que cantar,
    para que los ~30 clientes que consultan /state no se estorben."""
    partida = _buscar_partida(code)
    if not _cartas_pendientes_auto(partida, _ahora()):
        return partida

    partida = _buscar_partida(code, bloquear=True)
    momento = _ahora()
    pendientes = _cartas_pendientes_auto(partida, momento)  # releer con el candado
    restantes = TOTAL_CARTAS - _cantidad_cantadas(partida)
    if pendientes and restantes:
        cantidad = min(pendientes, restantes)
        _cantar(partida, cantidad, momento)
        # Avanza en múltiplos exactos del intervalo para no perder el ritmo.
        intervalo = timedelta(seconds=DIFICULTADES[partida.difficulty])
        partida.last_called_at = partida.last_called_at + cantidad * intervalo
    db.session.commit()
    return partida


def _carta_json(carta):
    return {"id": carta.id, "name": carta.name, "image": carta.image}


def _tablero_json(partida, tablero):
    return {
        "code": partida.code,
        "status": partida.status,
        "figure": partida.figure,
        "board_id": tablero.id,
        "cards": [
            {"position": c.position, "marked": c.marked, **_carta_json(c.card)}
            for c in tablero.cards
        ],
    }


def _ganador_json(ganador):
    return {
        "username": ganador.user.username,
        "board_id": ganador.board_id,
        "figure": ganador.figure,
        "won_at": ganador.won_at.isoformat(),
    }


def _estado_json(partida):
    # Una sola consulta (con la carta incluida): /state se consulta seguido.
    cantadas = db.session.scalars(
        select(CalledCard)
        .options(joinedload(CalledCard.card))
        .where(CalledCard.game_id == partida.id)
        .order_by(CalledCard.order)
    ).all()
    ganador = db.session.scalars(
        select(Winner).where(Winner.game_id == partida.id).order_by(Winner.won_at)
    ).first()
    jugadores = db.session.scalar(
        select(func.count()).select_from(Board).where(Board.game_id == partida.id)
    )
    return {
        "code": partida.code,
        "status": partida.status,
        "figure": partida.figure,
        "mode": partida.mode,
        "difficulty": partida.difficulty,
        "interval_seconds": DIFICULTADES[partida.difficulty],
        "players": jugadores,
        "current_card": _carta_json(cantadas[-1].card) if cantadas else None,
        "called_cards": [{"order": c.order, **_carta_json(c.card)} for c in cantadas],
        "remaining": TOTAL_CARTAS - len(cantadas),
        "winner": _ganador_json(ganador) if ganador else None,
    }


# ---------- rutas del profesor ----------


@bp.post("")
@require_host
def crear_partida():
    datos = _json_body()
    opciones = {"figure": "fila", "difficulty": "normal", "mode": "manual"}
    validos = {"figure": FIGURAS, "difficulty": DIFICULTADES_VALIDAS, "mode": MODOS}
    for campo in opciones:
        if campo in datos:
            opciones[campo] = _validar_opcion(datos, campo, validos[campo])

    db.session.flush()  # asegura g.user.id si el usuario es nuevo
    for _ in range(10):
        code = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(_LARGO_CODIGO))
        partida = Game(
            code=code, host_id=g.user.id, seed=secrets.randbelow(_MAX_SEMILLA), **opciones
        )
        try:
            with db.session.begin_nested():
                db.session.add(partida)
            break
        except IntegrityError:  # código repetido: probar otro
            continue
    else:
        raise ApiError(503, "No se pudo generar un código único; intenta de nuevo.")

    db.session.commit()
    return jsonify({"code": partida.code, **_estado_json(partida)}), 201


@bp.post("/<code>/start")
@require_host
def iniciar(code):
    partida = _buscar_partida(code, bloquear=True)
    _exigir_anfitrion(partida)
    if partida.status != "espera":
        raise ApiError(409, f"La partida ya se inició (estado: {partida.status}).")
    momento = _ahora()
    partida.status = "en_juego"
    partida.started_at = momento
    partida.last_called_at = momento
    db.session.commit()
    return jsonify(_estado_json(partida))


@bp.post("/<code>/next-card")
@require_host
def siguiente_carta(code):
    partida = _buscar_partida(code, bloquear=True)
    _exigir_anfitrion(partida)
    _exigir_en_juego(partida)
    if partida.mode != "manual":
        raise ApiError(409, "La partida está en modo auto; cambia a manual para sacar cartas.")
    if _cantidad_cantadas(partida) >= TOTAL_CARTAS:
        raise ApiError(409, "Ya se cantaron todas las cartas del mazo.")
    momento = _ahora()
    (cantada,) = _cantar(partida, 1, momento)
    partida.last_called_at = momento
    db.session.commit()
    return jsonify({"card": {"order": cantada.order, **_carta_json(cantada.card)}, **_estado_json(partida)})


@bp.post("/<code>/settings")
@require_host
def ajustes(code):
    datos = _json_body()
    validos = {"mode": MODOS, "difficulty": DIFICULTADES_VALIDAS, "figure": FIGURAS}
    cambios = {c: _validar_opcion(datos, c, v) for c, v in validos.items() if c in datos}
    if not cambios:
        raise ApiError(400, "Manda al menos uno de: mode, difficulty, figure.")

    partida = _buscar_partida(code, bloquear=True)
    _exigir_anfitrion(partida)
    if partida.status == "terminada":
        raise ApiError(409, "La partida ya terminó.")
    for campo, valor in cambios.items():
        setattr(partida, campo, valor)
    if partida.status == "en_juego" and ("mode" in cambios or "difficulty" in cambios):
        # El reloj del modo auto arranca desde ahora, para no soltar de golpe
        # las cartas "atrasadas" del tiempo que estuvo en manual.
        partida.last_called_at = _ahora()
    db.session.commit()
    return jsonify(_estado_json(partida))


# ---------- rutas de jugadores y pantallas ----------


@bp.post("/<code>/join")
@require_player
def unirse(code):
    # El candado serializa las uniones a la misma partida: así un doble clic
    # del mismo jugador no crea dos tableros.
    partida = _buscar_partida(code, bloquear=True)
    tablero = (
        db.session.query(Board).filter_by(game_id=partida.id, user_id=g.user.id).one_or_none()
    )
    if tablero is not None:
        db.session.commit()
        return jsonify(_tablero_json(partida, tablero))
    if partida.status == "terminada":
        raise ApiError(409, "La partida ya terminó.")

    semilla = secrets.randbelow(_MAX_SEMILLA)
    db.session.flush()  # asegura g.user.id si el usuario es nuevo
    tablero = Board(game_id=partida.id, user_id=g.user.id, seed=semilla)
    tablero.cards = [
        BoardCard(card_id=carta, position=posicion)
        for posicion, carta in enumerate(generar_tablero(semilla))
    ]
    db.session.add(tablero)
    db.session.commit()
    return jsonify(_tablero_json(partida, tablero)), 201


@bp.get("/<code>/state")
def estado(code):
    partida = _sincronizar_auto(code)
    return jsonify(_estado_json(partida))


@bp.post("/<code>/claim")
@require_player
def cantar_loteria(code):
    datos = _json_body()
    marcadas = datos.get("marcadas")
    if not isinstance(marcadas, list) or not all(type(m) is int for m in marcadas):
        raise ApiError(400, '"marcadas" debe ser una lista de ids de carta (enteros).')

    # Primero se ponen al día las cartas del modo auto; luego se bloquea la
    # partida para que dos reclamos simultáneos no produzcan dos ganadores.
    _sincronizar_auto(code)
    partida = _buscar_partida(code, bloquear=True)
    if partida.status == "terminada":
        raise ApiError(409, "La partida ya terminó.")
    _exigir_en_juego(partida)
    tablero = (
        db.session.query(Board).filter_by(game_id=partida.id, user_id=g.user.id).one_or_none()
    )
    if tablero is None:
        raise ApiError(404, "No tienes tablero en esta partida; únete primero.")

    cartas_tablero = [c.card_id for c in tablero.cards]  # ordenadas por posición
    cantadas = db.session.scalars(
        select(CalledCard.card_id).where(CalledCard.game_id == partida.id)
    ).all()
    if not validar_victoria(cartas_tablero, marcadas, cantadas, partida.figure):
        db.session.commit()
        return jsonify({"valid": False})

    marcas = set(marcadas)
    for casilla in tablero.cards:
        casilla.marked = casilla.card_id in marcas
    ganador = Winner(
        game_id=partida.id, user_id=g.user.id, board_id=tablero.id, figure=partida.figure
    )
    db.session.add(ganador)
    partida.status = "terminada"
    db.session.commit()
    return jsonify({"valid": True, "winner": _ganador_json(ganador), **_estado_json(partida)})
