"""Pruebas del ranking de ganadores (app/ranking.py y app/routes/ranking.py)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.db import db
from app.models import Board, Game, User, Winner

pytestmark = pytest.mark.usefixtures("limpia_bd")


# ---------- utilidades ----------


def registrar_victoria(app, username, code, figure="fila", minutos_atras=0):
    with app.app_context():
        host = db.session.query(User).filter_by(username="profe").one_or_none()
        if host is None:
            host = User(username="profe", password_hash="!prueba", role="profesor")
            db.session.add(host)
            db.session.flush()

        jugador = db.session.query(User).filter_by(username=username).one_or_none()
        if jugador is None:
            jugador = User(username=username, password_hash="!prueba", role="jugador")
            db.session.add(jugador)
            db.session.flush()

        partida = Game(
            code=code,
            host_id=host.id,
            figure=figure,
            status="terminada",
            seed=100,
        )
        db.session.add(partida)
        db.session.flush()

        tablero = Board(game_id=partida.id, user_id=jugador.id, seed=200)
        db.session.add(tablero)
        db.session.flush()

        momento = datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)
        victoria = Winner(
            game_id=partida.id,
            user_id=jugador.id,
            board_id=tablero.id,
            figure=figure,
            won_at=momento,
        )
        db.session.add(victoria)
        db.session.commit()


# ---------- estado vacío ----------


def test_ranking_vacio_en_web_y_api(client):
    resp_api = client.get("/api/ranking")
    assert resp_api.status_code == 200
    datos = resp_api.get_json()
    assert datos["total_wins"] == 0
    assert datos["total_players"] == 0
    assert datos["ranking"] == []
    assert datos["recent_wins"] == []
    assert datos["figure"] is None

    resp_web = client.get("/ranking")
    html = resp_web.get_data(as_text=True)
    assert resp_web.status_code == 200
    assert "Aún no hay ganadores registrados" in html


# ---------- ordenamiento, empates y límite ----------


def test_ranking_ordena_por_victorias_y_desempata_por_primero_en_alcanzarlas(app, client):
    # Carla gana 3 veces; Ana gana 2 (última hace 10 min); Beto gana 2 (última hace 2 min).
    registrar_victoria(app, "Carla", "G00001", "fila", minutos_atras=30)
    registrar_victoria(app, "Carla", "G00002", "diagonal", minutos_atras=20)
    registrar_victoria(app, "Carla", "G00003", "columna", minutos_atras=5)
    registrar_victoria(app, "Ana", "G00004", "fila", minutos_atras=25)
    registrar_victoria(app, "Ana", "G00005", "cuatro_esquinas", minutos_atras=10)
    registrar_victoria(app, "Beto", "G00006", "fila", minutos_atras=15)
    registrar_victoria(app, "Beto", "G00007", "tablero_lleno", minutos_atras=2)

    resp = client.get("/api/ranking")
    assert resp.status_code == 200
    datos = resp.get_json()

    assert datos["total_wins"] == 7
    assert datos["total_players"] == 3
    assert [(r["position"], r["username"], r["wins"]) for r in datos["ranking"]] == [
        (1, "Carla", 3),
        (2, "Ana", 2),
        (3, "Beto", 2),
    ]
    # Victorias recientes: la más nueva (hace 2 min, Beto en G00007) aparece primero.
    assert datos["recent_wins"][0]["username"] == "Beto"
    assert datos["recent_wins"][0]["game_code"] == "G00007"
    assert datos["recent_wins"][0]["figure"] == "tablero_lleno"


def test_ranking_respeta_parametro_limit_y_rechaza_limites_invalidos(app, client):
    for i in range(5):
        registrar_victoria(app, f"jugador_{i}", f"LIM00{i}", minutos_atras=10 - i)

    resp = client.get("/api/ranking?limit=2")
    assert resp.status_code == 200
    datos = resp.get_json()
    assert len(datos["ranking"]) == 2
    assert datos["total_players"] == 5

    for invalido in ("0", "-3", "101", "abc"):
        assert client.get(f"/api/ranking?limit={invalido}").status_code == 400


# ---------- filtro por figura ----------


@pytest.mark.parametrize(
    "figura", ["fila", "columna", "diagonal", "cuatro_esquinas", "tablero_lleno"]
)
def test_ranking_filtra_correctamente_por_cada_figura(app, client, figura):
    registrar_victoria(app, "Ana", "FIG001", figure=figura, minutos_atras=5)
    otra = "diagonal" if figura != "diagonal" else "fila"
    registrar_victoria(app, "Beto", "FIG002", figure=otra, minutos_atras=1)

    resp = client.get(f"/api/ranking?figure={figura}")
    assert resp.status_code == 200
    datos = resp.get_json()
    assert datos["figure"] == figura
    assert datos["total_wins"] == 1
    assert [r["username"] for r in datos["ranking"]] == ["Ana"]
    assert all(v["figure"] == figura for v in datos["recent_wins"])


def test_ranking_rechaza_figura_invalida_con_400(client):
    resp_api = client.get("/api/ranking?figure=cruz")
    assert resp_api.status_code == 400
    assert "error" in resp_api.get_json()

    resp_web = client.get("/ranking?figure=cruz")
    assert resp_web.status_code == 400
    assert 'role="alert"' in resp_web.get_data(as_text=True)


# ---------- vista HTML y seguridad ----------


def test_vista_ranking_muestra_podio_tabla_y_escapa_html(app, client):
    nombre_xss = "<script>alert('xss')</script>"
    registrar_victoria(app, "Carla", "WEB001", "fila", minutos_atras=10)
    registrar_victoria(app, "Carla", "WEB002", "diagonal", minutos_atras=5)
    registrar_victoria(app, nombre_xss, "WEB003", "cuatro_esquinas", minutos_atras=1)

    resp = client.get("/ranking")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Carla" in html
    assert "WEB003" in html
    assert nombre_xss not in html
    assert "&lt;script&gt;" in html
