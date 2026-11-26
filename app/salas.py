"""Lógica de salas: crear partida con código y unirse desde el celular.

Reutiliza los mismos modelos (`Game`, `Board`, `BoardCard`, `User`) y reglas
(`generar_tablero`) que la API `/api/games`, de modo que las salas creadas
desde la web y desde la API son completamente interoperables.

La identificación por nombre de usuario es temporal mientras se integra el
login real (mismo esquema que `app/auth.py`).
"""

import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.auth import _SIN_PASSWORD
from app.db import db
from app.errors import ApiError
from app.game import DIFICULTADES, generar_tablero
from app.game.constantes import CARTAS
from app.models import (
    DIFICULTADES_VALIDAS,
    FIGURAS,
    MODOS,
    Board,
    BoardCard,
    CalledCard,
    Game,
    User,
)

# Sin 0/O ni 1/I/L para que el profesor pueda dictarlo y los alumnos teclearlo
# fácilmente desde el celular.
ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LARGO_CODIGO = 6
MAX_LARGO_CODIGO = 12
MAX_LARGO_NOMBRE = 80
MAX_SEMILLA = 2**31
TOTAL_CARTAS = len(CARTAS)

ETIQUETAS_FIGURA = {
    "fila": "Fila",
    "columna": "Columna",
    "diagonal": "Diagonal",
    "cuatro_esquinas": "Cuatro esquinas",
    "tablero_lleno": "Tablero lleno",
}

DESCRIPCIONES_FIGURA = {
    "fila": "Completa cualquiera de las 4 líneas horizontales",
    "columna": "Completa cualquiera de las 4 líneas verticales",
    "diagonal": "Completa cualquiera de las 2 diagonales",
    "cuatro_esquinas": "Marca las 4 esquinas del tablero",
    "tablero_lleno": "Marca las 16 cartas de tu tablero",
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


class SalaError(ApiError):
    """Error de validación o estado de sala con código HTTP asociado."""


def normalizar_codigo(codigo):
    """Limpia espacios y convierte el código a mayúsculas."""
    if not isinstance(codigo, str):
        raise SalaError(400, "Ingresa el código de la sala.")
    limpio = "".join(codigo.split()).upper()
    if not limpio:
        raise SalaError(400, "Ingresa el código de la sala.")
    if len(limpio) > MAX_LARGO_CODIGO:
        raise SalaError(400, "El código de sala no es válido.")
    return limpio


def normalizar_nombre(nombre):
    """Valida y limpia el nombre del usuario."""
    if not isinstance(nombre, str):
        raise SalaError(400, "Ingresa tu nombre para continuar.")
    limpio = nombre.strip()
    if not limpio:
        raise SalaError(400, "Ingresa tu nombre para continuar.")
    if len(limpio) > MAX_LARGO_NOMBRE:
        raise SalaError(
            400, f"El nombre no puede tener más de {MAX_LARGO_NOMBRE} caracteres."
        )
    return limpio


def generar_codigo_sala():
    """Genera un código aleatorio de 6 caracteres fáciles de dictar."""
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))


def _validar_opcion(campo, valor, validos):
    if not isinstance(valor, str) or valor not in validos:
        raise SalaError(
            400,
            f"Opción inválida para {campo}. Opciones válidas: {', '.join(validos)}.",
        )
    return valor


def _obtener_o_crear_usuario(nombre, rol_si_es_nuevo, exigir_rol=None):
    """Obtiene un usuario por nombre o lo crea con el rol indicado.

    Temporal mientras no existe login real (ver `app/auth.py`).
    """
    usuario = db.session.query(User).filter_by(username=nombre).one_or_none()
    if usuario is None:
        try:
            with db.session.begin_nested():
                usuario = User(
                    username=nombre,
                    password_hash=_SIN_PASSWORD,
                    role=rol_si_es_nuevo,
                )
                db.session.add(usuario)
        except IntegrityError:
            usuario = db.session.query(User).filter_by(username=nombre).one()

    if exigir_rol is not None and usuario.role != exigir_rol:
        raise SalaError(
            403,
            "Ese nombre ya está registrado como jugador. Usa un nombre de profesor.",
        )

    db.session.flush()
    return usuario


def buscar_sala(codigo, bloquear=False):
    """Busca una partida por su código (sin importar mayúsculas ni espacios)."""
    codigo_norm = normalizar_codigo(codigo)
    consulta = select(Game).where(Game.code == codigo_norm)
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    partida = db.session.execute(consulta).scalar_one_or_none()
    if partida is None:
        raise SalaError(
            404,
            f"No existe una sala con el código {codigo_norm}. Verifica el código con tu profesor.",
        )
    return partida


def crear_sala(nombre_profesor, figure="fila", difficulty="normal", mode="manual"):
    """Crea una nueva partida en estado de espera con código único."""
    nombre_norm = normalizar_nombre(nombre_profesor)
    figura_val = _validar_opcion("figura", figure, FIGURAS)
    dificultad_val = _validar_opcion("dificultad", difficulty, DIFICULTADES_VALIDAS)
    modo_val = _validar_opcion("modo", mode, MODOS)

    profesor = _obtener_o_crear_usuario(
        nombre_norm, rol_si_es_nuevo="profesor", exigir_rol="profesor"
    )

    for _ in range(10):
        codigo = generar_codigo_sala()
        partida = Game(
            code=codigo,
            host_id=profesor.id,
            figure=figura_val,
            difficulty=dificultad_val,
            mode=modo_val,
            seed=secrets.randbelow(MAX_SEMILLA),
        )
        try:
            with db.session.begin_nested():
                db.session.add(partida)
            break
        except IntegrityError:
            continue
    else:
        raise SalaError(
            503, "No se pudo generar un código único; intenta nuevamente."
        )

    db.session.commit()
    return partida, profesor


def unirse_a_sala(codigo, nombre_jugador):
    """Une un alumno a una sala y genera su tablero de 16 cartas.

    Es idempotente: si el alumno ya tenía tablero en esta sala, devuelve el
    mismo sin crear duplicados. Devuelve `(partida, tablero, jugador, creado)`.
    """
    codigo_norm = normalizar_codigo(codigo)
    nombre_norm = normalizar_nombre(nombre_jugador)

    # Bloquea la partida primero: si no existe, falla con 404 sin crear usuarios.
    partida = buscar_sala(codigo_norm, bloquear=True)

    usuario = db.session.query(User).filter_by(username=nombre_norm).one_or_none()
    if usuario is not None:
        tablero_existente = (
            db.session.execute(
                select(Board)
                .options(joinedload(Board.cards).joinedload(BoardCard.card))
                .where(Board.game_id == partida.id, Board.user_id == usuario.id)
            )
            .unique()
            .scalar_one_or_none()
        )
        if tablero_existente is not None:
            db.session.commit()
            return partida, tablero_existente, usuario, False

    if partida.status == "terminada":
        raise SalaError(409, "La partida ya terminó; ya no es posible unirse.")

    jugador = _obtener_o_crear_usuario(nombre_norm, rol_si_es_nuevo="jugador")
    semilla = secrets.randbelow(MAX_SEMILLA)
    tablero = Board(game_id=partida.id, user_id=jugador.id, seed=semilla)
    tablero.cards = [
        BoardCard(card_id=carta, position=posicion)
        for posicion, carta in enumerate(generar_tablero(semilla))
    ]
    db.session.add(tablero)
    db.session.commit()

    # Recarga el tablero con sus cartas asociadas para renderizar sin consultas extra.
    tablero = (
        db.session.execute(
            select(Board)
            .options(joinedload(Board.cards).joinedload(BoardCard.card))
            .where(Board.id == tablero.id)
        )
        .unique()
        .scalar_one()
    )
    return partida, tablero, jugador, True


def obtener_tablero_jugador(partida, username):
    """Devuelve el tablero del jugador en `partida` (con sus cartas), o None."""
    if not username:
        return None
    return (
        db.session.execute(
            select(Board)
            .join(User, Board.user_id == User.id)
            .options(
                joinedload(Board.user),
                joinedload(Board.cards).joinedload(BoardCard.card),
            )
            .where(Board.game_id == partida.id, User.username == username)
        )
        .unique()
        .scalar_one_or_none()
    )


def listar_jugadores_sala(partida):
    """Devuelve los nombres de los jugadores unidos en orden de llegada."""
    tableros = db.session.scalars(
        select(Board)
        .options(joinedload(Board.user))
        .where(Board.game_id == partida.id)
        .order_by(Board.id)
    ).all()
    return [t.user.username for t in tableros]


def resumen_sala(partida):
    """Diccionario serializable con la información de la sala y jugadores."""
    jugadores = listar_jugadores_sala(partida)
    cantadas = db.session.scalar(
        select(func.count())
        .select_from(CalledCard)
        .where(CalledCard.game_id == partida.id)
    )
    return {
        "code": partida.code,
        "host": partida.host.username,
        "status": partida.status,
        "status_label": ETIQUETAS_ESTADO.get(partida.status, partida.status),
        "figure": partida.figure,
        "figure_label": ETIQUETAS_FIGURA.get(partida.figure, partida.figure),
        "figure_description": DESCRIPCIONES_FIGURA.get(partida.figure, ""),
        "mode": partida.mode,
        "mode_label": ETIQUETAS_MODO.get(partida.mode, partida.mode),
        "difficulty": partida.difficulty,
        "difficulty_label": ETIQUETAS_DIFICULTAD.get(
            partida.difficulty, partida.difficulty
        ),
        "interval_seconds": DIFICULTADES[partida.difficulty],
        "players_count": len(jugadores),
        "players": jugadores,
        "called_count": cantadas,
        "remaining": TOTAL_CARTAS - cantadas,
    }
