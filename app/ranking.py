"""Consultas de ranking e historial de ganadores a partir de la tabla `winners`."""

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.db import db
from app.errors import ApiError
from app.models import FIGURAS, User, Winner

ETIQUETAS_FIGURA = {
    "fila": "Fila",
    "columna": "Columna",
    "diagonal": "Diagonal",
    "cuatro_esquinas": "Cuatro esquinas",
    "tablero_lleno": "Tablero lleno",
}

LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 100


def validar_figura(figura):
    """Valida el filtro opcional de figura ganadora (None o vacío = todas)."""
    if figura is None or figura == "":
        return None
    if not isinstance(figura, str) or figura not in FIGURAS:
        raise ApiError(
            400,
            f"Figura inválida: {figura!r}. Válidas: {', '.join(FIGURAS)}.",
        )
    return figura


def validar_limite(limite, default=LIMITE_POR_DEFECTO, maximo=LIMITE_MAXIMO):
    """Valida el límite de resultados solicitado (entero entre 1 y `maximo`)."""
    if limite is None or limite == "":
        return default
    if isinstance(limite, bool):
        raise ApiError(400, f"El límite debe ser un entero entre 1 y {maximo}.")
    try:
        valor = int(limite)
    except (TypeError, ValueError) as exc:
        raise ApiError(
            400, f"El límite debe ser un entero entre 1 y {maximo}."
        ) from exc
    if valor < 1 or valor > maximo:
        raise ApiError(400, f"El límite debe estar entre 1 y {maximo}.")
    return valor


def obtener_ranking(figura=None, limite=LIMITE_POR_DEFECTO):
    """Devuelve el top de jugadores ordenados por número de victorias."""
    figura_val = validar_figura(figura)
    limite_val = validar_limite(limite)

    conteo = func.count(Winner.id).label("wins")
    ultima = func.max(Winner.won_at).label("last_won_at")

    consulta = (
        select(User.username, conteo, ultima)
        .join(Winner, Winner.user_id == User.id)
        .group_by(User.id, User.username)
        .order_by(conteo.desc(), ultima.asc(), User.username.asc())
        .limit(limite_val)
    )
    if figura_val is not None:
        consulta = consulta.where(Winner.figure == figura_val)

    filas = db.session.execute(consulta).all()
    return [
        {
            "position": idx,
            "username": fila.username,
            "wins": int(fila.wins),
            "last_won_at": fila.last_won_at.isoformat() if fila.last_won_at else None,
        }
        for idx, fila in enumerate(filas, start=1)
    ]


def obtener_victorias_recientes(figura=None, limite=15):
    """Devuelve las victorias más recientes con código de partida y figura."""
    figura_val = validar_figura(figura)
    limite_val = validar_limite(limite, default=15)

    consulta = (
        select(Winner)
        .options(joinedload(Winner.user), joinedload(Winner.game))
        .order_by(Winner.won_at.desc(), Winner.id.desc())
        .limit(limite_val)
    )
    if figura_val is not None:
        consulta = consulta.where(Winner.figure == figura_val)

    registros = db.session.scalars(consulta).all()
    return [
        {
            "username": r.user.username,
            "game_code": r.game.code,
            "figure": r.figure,
            "figure_label": ETIQUETAS_FIGURA.get(r.figure, r.figure),
            "won_at": r.won_at.isoformat(),
        }
        for r in registros
    ]


def resumen_ranking(figura=None, limite=LIMITE_POR_DEFECTO):
    """Resumen completo del ranking, totales e historial reciente."""
    figura_val = validar_figura(figura)
    limite_val = validar_limite(limite)

    q_total = select(func.count(Winner.id))
    q_jugadores = select(func.count(func.distinct(Winner.user_id)))
    if figura_val is not None:
        q_total = q_total.where(Winner.figure == figura_val)
        q_jugadores = q_jugadores.where(Winner.figure == figura_val)

    total_victorias = int(db.session.scalar(q_total) or 0)
    total_jugadores = int(db.session.scalar(q_jugadores) or 0)

    return {
        "figure": figura_val,
        "figure_label": ETIQUETAS_FIGURA[figura_val] if figura_val else "Todas",
        "total_wins": total_victorias,
        "total_players": total_jugadores,
        "ranking": obtener_ranking(figura=figura_val, limite=limite_val),
        "recent_wins": obtener_victorias_recientes(figura=figura_val, limite=min(limite_val, 15)),
    }
