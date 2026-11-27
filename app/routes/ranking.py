"""Rutas web y API JSON del ranking de ganadores (`/ranking` y `/api/ranking`)."""

from flask import Blueprint, jsonify, render_template, request

from app.errors import ApiError, respuesta_de_error
from app.models import FIGURAS
from app.ranking import ETIQUETAS_FIGURA, resumen_ranking

bp = Blueprint("ranking", __name__)
bp.register_error_handler(ApiError, respuesta_de_error)


def _filtros_figura():
    return [(clave, ETIQUETAS_FIGURA[clave]) for clave in FIGURAS]


@bp.get("/api/ranking")
def api_ranking():
    figura = request.args.get("figure")
    limite = request.args.get("limit")
    return jsonify(resumen_ranking(figura=figura, limite=limite))


@bp.get("/ranking")
def vista_ranking():
    figura = request.args.get("figure")
    limite = request.args.get("limit")
    try:
        datos = resumen_ranking(figura=figura, limite=limite)
    except ApiError as err:
        return (
            render_template(
                "ranking/index.html",
                datos=resumen_ranking(),
                figuras=_filtros_figura(),
                error=err.message,
            ),
            err.status,
        )

    return render_template(
        "ranking/index.html",
        datos=datos,
        figuras=_filtros_figura(),
        error=None,
    )
