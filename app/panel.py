"""Lógica del panel del profesor para controlar una partida en vivo.

Reutiliza los mismos modelos (`Game`, `CalledCard`, `Board`, `Winner`) y el
reloj automático de `app/routes/game.py` (`_sincronizar_auto`) para mantener
una sola fuente de verdad con `/api/games`.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db import db
from app.errors import ApiError
from app.game import DIFICULTADES, barajar_mazo
from app.game.constantes import CARTAS
from app.models import (
    DIFICULTADES_VALIDAS,
    FIGURAS,
    MODOS,
    Board,
    CalledCard,
    Game,
    User,
    Winner,
)
from app.routes.game import _cantidad_cantadas, _sincronizar_auto

TOTAL_CARTAS = len(CARTAS)
MAX_LARGO_CODIGO = 12

ETIQUETAS_FIGURA = {
    "fila": "Fila",
    "columna": "Columna",
    "diagonal": "Diagonal",
    "cuatro_esquinas": "Cuatro esquinas",
    "tablero_lleno": "Tablero lleno",
}

ETIQUETAS_MODO = {
    "manual": "Manual",
    "auto": "Automático",
}

ETIQUETAS_DIFICULTAD = {
    "facil": f"Fácil ({DIFICULTADES['facil']} s)",
    "normal": f"Normal ({DIFICULTADES['normal']} s)",
    "dificil": f"Difícil ({DIFICULTADES['dificil']} s)",
}

ETIQUETAS_ESTADO = {
    "espera": "En espera",
    "en_juego": "En juego",
    "terminada": "Terminada",
}


def _ahora():
    return datetime.now(timezone.utc)


def normalizar_codigo(codigo):
    if not isinstance(codigo, str):
        raise ApiError(400, "Ingresa el código de la partida.")
    limpio = "".join(codigo.split()).upper()
    if not limpio or len(limpio) > MAX_LARGO_CODIGO:
        raise ApiError(400, "El código de la partida no es válido.")
    return limpio


def buscar_partida_panel(codigo, bloquear=False):
    codigo_norm = normalizar_codigo(codigo)
    consulta = select(Game).where(Game.code == codigo_norm)
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    partida = db.session.execute(consulta).scalar_one_or_none()
    if partida is None:
        raise ApiError(404, f"No existe la partida {codigo_norm}.")
    return partida


def exigir_anfitrion_por_nombre(partida, username):
    if not username:
        raise ApiError(401, "Debes identificarte como profesor para usar el panel.")
    if partida.host.username != username:
        raise ApiError(403, "Solo el profesor que creó la partida puede controlarla.")


def _validar_opcion(campo, valor, validos):
    if not isinstance(valor, str) or valor not in validos:
        raise ApiError(
            400, f"Valor inválido para {campo}: {valor!r}. Válidos: {', '.join(validos)}."
        )
    return valor


def estado_panel(partida):
    """Construye el estado completo que consume el panel del profesor."""
    cantadas = db.session.scalars(
        select(CalledCard)
        .options(joinedload(CalledCard.card))
        .where(CalledCard.game_id == partida.id)
        .order_by(CalledCard.order)
    ).all()
    tableros = db.session.scalars(
        select(Board)
        .options(joinedload(Board.user))
        .where(Board.game_id == partida.id)
        .order_by(Board.id)
    ).all()
    ganador = db.session.scalars(
        select(Winner)
        .options(joinedload(Winner.user))
        .where(Winner.game_id == partida.id)
        .order_by(Winner.won_at)
    ).first()

    lista_cantadas = [
        {
            "order": c.order,
            "id": c.card.id,
            "name": c.card.name,
            "image": c.card.image,
        }
        for c in cantadas
    ]
    jugadores = [t.user.username for t in tableros]

    return {
        "code": partida.code,
        "host": partida.host.username,
        "status": partida.status,
        "status_label": ETIQUETAS_ESTADO.get(partida.status, partida.status),
        "figure": partida.figure,
        "figure_label": ETIQUETAS_FIGURA.get(partida.figure, partida.figure),
        "mode": partida.mode,
        "mode_label": ETIQUETAS_MODO.get(partida.mode, partida.mode),
        "difficulty": partida.difficulty,
        "difficulty_label": ETIQUETAS_DIFICULTAD.get(
            partida.difficulty, partida.difficulty
        ),
        "interval_seconds": DIFICULTADES[partida.difficulty],
        "players_count": len(jugadores),
        "players": jugadores,
        "current_card": lista_cantadas[-1] if lista_cantadas else None,
        "called_cards": lista_cantadas,
        "called_count": len(lista_cantadas),
        "remaining": TOTAL_CARTAS - len(lista_cantadas),
        "winner": (
            {
                "username": ganador.user.username,
                "figure": ganador.figure,
                "figure_label": ETIQUETAS_FIGURA.get(ganador.figure, ganador.figure),
                "won_at": ganador.won_at.isoformat(),
            }
            if ganador
            else None
        ),
    }


def sincronizar_y_obtener_estado(codigo, username):
    """Sincroniza el reloj automático si aplica y devuelve el estado del panel."""
    codigo_norm = normalizar_codigo(codigo)
    partida = _sincronizar_auto(codigo_norm)
    exigir_anfitrion_por_nombre(partida, username)
    return estado_panel(partida)


def iniciar_partida_panel(codigo, username):
    partida = buscar_partida_panel(codigo, bloquear=True)
    exigir_anfitrion_por_nombre(partida, username)
    if partida.status != "espera":
        raise ApiError(409, f"La partida ya se inició (estado: {partida.status}).")
    momento = _ahora()
    partida.status = "en_juego"
    partida.started_at = momento
    partida.last_called_at = momento
    db.session.commit()
    return estado_panel(partida)


def siguiente_carta_panel(codigo, username):
    partida = buscar_partida_panel(codigo, bloquear=True)
    exigir_anfitrion_por_nombre(partida, username)
    if partida.status != "en_juego":
        raise ApiError(409, f"La partida no está en juego (estado: {partida.status}).")
    if partida.mode != "manual":
        raise ApiError(
            409, "La partida está en modo automático; cambia a manual para sacar cartas."
        )
    ya = _cantidad_cantadas(partida)
    if ya >= TOTAL_CARTAS:
        raise ApiError(409, "Ya se cantaron todas las cartas del mazo.")

    momento = _ahora()
    mazo = barajar_mazo(int(partida.seed))
    nueva = CalledCard(
        game_id=partida.id, card_id=mazo[ya], order=ya + 1, called_at=momento
    )
    db.session.add(nueva)
    partida.last_called_at = momento
    db.session.commit()
    datos = estado_panel(partida)
    datos["card"] = datos["current_card"]
    return datos


def actualizar_ajustes_panel(codigo, username, cambios_crudos):
    validos = {"mode": MODOS, "difficulty": DIFICULTADES_VALIDAS, "figure": FIGURAS}
    cambios = {
        campo: _validar_opcion(campo, cambios_crudos[campo], opciones)
        for campo, opciones in validos.items()
        if campo in cambios_crudos and cambios_crudos[campo] is not None
    }
    if not cambios:
        raise ApiError(400, "Envía al menos uno de: mode, difficulty, figure.")

    partida = buscar_partida_panel(codigo, bloquear=True)
    exigir_anfitrion_por_nombre(partida, username)
    if partida.status == "terminada":
        raise ApiError(409, "La partida ya terminó.")

    for campo, valor in cambios.items():
        setattr(partida, campo, valor)

    if partida.status == "en_juego" and ("mode" in cambios or "difficulty" in cambios):
        partida.last_called_at = _ahora()

    db.session.commit()
    return estado_panel(partida)


def listar_partidas_profesor(username, limite=10):
    if not username:
        return []
    return db.session.scalars(
        select(Game)
        .join(User, Game.host_id == User.id)
        .where(User.username == username)
        .order_by(Game.created_at.desc(), Game.id.desc())
        .limit(limite)
    ).all()
