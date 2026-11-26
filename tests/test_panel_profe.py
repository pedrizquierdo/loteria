"""Pruebas del panel del profesor (app/panel.py y app/routes/panel.py)."""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest

from app.db import db
from app.game import barajar_mazo, generar_tablero
from app.models import Board, BoardCard, Game, User, Winner

pytestmark = pytest.mark.usefixtures("limpia_bd")

JSON_HEADERS = {"Accept": "application/json"}


# ---------- utilidades ----------


def crear_usuario_bd(app, username, role="profesor"):
    with app.app_context():
        usuario = db.session.query(User).filter_by(username=username).one_or_none()
        if usuario is None:
            usuario = User(
                username=username, password_hash="!prueba", role=role
            )
            db.session.add(usuario)
            db.session.commit()
        return usuario.id


def crear_partida_bd(
    app,
    host_name="profe_luis",
    code="K7M9P2",
    figure="fila",
    difficulty="normal",
    mode="manual",
    status="espera",
    seed=12345,
):
    host_id = crear_usuario_bd(app, host_name, role="profesor")
    with app.app_context():
        ahora = datetime.now(timezone.utc)
        partida = Game(
            code=code,
            host_id=host_id,
            figure=figure,
            difficulty=difficulty,
            mode=mode,
            status=status,
            seed=seed,
            started_at=ahora if status != "espera" else None,
            last_called_at=ahora if status != "espera" else None,
        )
        db.session.add(partida)
        db.session.commit()
        return partida.id


def agregar_jugador_bd(app, code, username="ana", seed=77):
    user_id = crear_usuario_bd(app, username, role="jugador")
    with app.app_context():
        partida = db.session.query(Game).filter_by(code=code).one()
        tablero = Board(game_id=partida.id, user_id=user_id, seed=seed)
        tablero.cards = [
            BoardCard(card_id=carta, position=pos)
            for pos, carta in enumerate(generar_tablero(seed))
        ]
        db.session.add(tablero)
        db.session.commit()
        return tablero.id


def autenticar_panel(app, code, username="profe_luis"):
    cli = app.test_client()
    resp = cli.post("/panel/acceder", data={"code": code, "username": username})
    assert resp.status_code == 302, resp.get_data(as_text=True)
    return cli


# ---------- acceso y permisos ----------


def test_pantalla_acceso_responde_200(client):
    resp = client.get("/panel/")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'name="code"' in html
    assert 'name="username"' in html


def test_acceso_exitoso_abre_panel_del_anfitrion(app):
    crear_partida_bd(app, code="ABC234", host_name="profe_luis")
    agregar_jugador_bd(app, "ABC234", username="Ana")
    agregar_jugador_bd(app, "ABC234", username="Beto")

    cli = autenticar_panel(app, "abc 234", username="profe_luis")
    vista = cli.get("/panel/ABC234")
    html = vista.get_data(as_text=True)

    assert vista.status_code == 200
    assert "ABC234" in html
    assert "profe_luis" in html
    assert "Ana" in html
    assert "Beto" in html
    assert "Iniciar partida" in html

    # La pantalla de acceso muestra ahora sus partidas recientes.
    acceso = cli.get("/panel/")
    assert "ABC234" in acceso.get_data(as_text=True)


def test_acceso_rechaza_otro_profesor_y_codigo_inexistente(app, client):
    crear_partida_bd(app, code="ABC234", host_name="profe_luis")

    resp_403 = client.post(
        "/panel/acceder", data={"code": "ABC234", "username": "intruso"}
    )
    assert resp_403.status_code == 403

    resp_404 = client.post(
        "/panel/acceder", data={"code": "NOEXIS", "username": "profe_luis"}
    )
    assert resp_404.status_code == 404


def test_panel_control_sin_sesion_redirige_y_otro_usuario_da_403(app):
    crear_partida_bd(app, code="ABC234", host_name="profe_luis")
    crear_partida_bd(app, code="XYZ789", host_name="otro_profe")

    anon = app.test_client()
    resp_anon = anon.get("/panel/ABC234")
    assert resp_anon.status_code == 302
    assert resp_anon.headers["Location"].endswith("/panel/?code=ABC234")
    assert anon.get("/panel/ABC234/estado").status_code == 401

    otro = autenticar_panel(app, "XYZ789", username="otro_profe")
    assert otro.get("/panel/ABC234").status_code == 403
    assert otro.get("/panel/ABC234/estado").status_code == 403
    assert (
        otro.post("/panel/ABC234/iniciar", headers=JSON_HEADERS).status_code == 403
    )
    assert (
        otro.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS).status_code
        == 403
    )
    assert (
        otro.post(
            "/panel/ABC234/ajustes", json={"mode": "auto"}
        ).status_code
        == 403
    )


def test_panel_partida_inexistente_da_404(app):
    crear_partida_bd(app, code="ABC234", host_name="profe_luis")
    cli = autenticar_panel(app, "ABC234")
    assert cli.get("/panel/NOEXIS").status_code == 404
    assert cli.get("/panel/NOEXIS/estado").status_code == 404


# ---------- iniciar y cantar cartas (modo manual) ----------


def test_iniciar_y_sacar_cartas_sigue_orden_del_mazo_y_se_refleja_en_api(app):
    semilla = 9876
    crear_partida_bd(app, code="ABC234", seed=semilla)
    cli = autenticar_panel(app, "ABC234")

    # Antes de iniciar no puede sacar carta.
    assert (
        cli.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS).status_code
        == 409
    )

    resp_start = cli.post("/panel/ABC234/iniciar", headers=JSON_HEADERS)
    assert resp_start.status_code == 200
    assert resp_start.get_json()["status"] == "en_juego"

    # Iniciar dos veces da 409.
    assert cli.post("/panel/ABC234/iniciar", headers=JSON_HEADERS).status_code == 409

    mazo = barajar_mazo(semilla)
    for orden in range(1, 5):
        resp = cli.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS)
        assert resp.status_code == 200
        datos = resp.get_json()
        assert datos["card"]["order"] == orden
        assert datos["card"]["id"] == mazo[orden - 1]
        assert datos["remaining"] == 54 - orden

    # La API pública `/api/games/<code>/state` ve exactamente las mismas cartas.
    api_state = cli.get("/api/games/ABC234/state").get_json()
    assert [c["id"] for c in api_state["called_cards"]] == mazo[:4]
    assert api_state["status"] == "en_juego"


def test_acciones_html_sin_js_redirigen_al_panel(app):
    crear_partida_bd(app, code="ABC234")
    cli = autenticar_panel(app, "ABC234")

    r1 = cli.post("/panel/ABC234/iniciar")
    assert r1.status_code == 302
    assert urlparse(r1.headers["Location"]).path == "/panel/ABC234"

    r2 = cli.post("/panel/ABC234/siguiente-carta")
    assert r2.status_code == 302

    r3 = cli.post(
        "/panel/ABC234/ajustes",
        data={"figure": "diagonal", "mode": "manual", "difficulty": "facil"},
    )
    assert r3.status_code == 302

    estado = cli.get("/panel/ABC234/estado").get_json()
    assert estado["called_count"] == 1
    assert estado["figure"] == "diagonal"
    assert estado["difficulty"] == "facil"


def test_sacar_carta_despues_de_54_da_409(app):
    crear_partida_bd(app, code="ABC234", status="en_juego")
    cli = autenticar_panel(app, "ABC234")

    for _ in range(54):
        assert (
            cli.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS).status_code
            == 200
        )

    assert (
        cli.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS).status_code
        == 409
    )


def test_sacar_carta_en_modo_auto_da_409_y_estado_sincroniza_reloj(app):
    semilla = 4242
    crear_partida_bd(
        app, code="ABC234", status="en_juego", mode="auto", difficulty="dificil", seed=semilla
    )
    cli = autenticar_panel(app, "ABC234")

    assert (
        cli.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS).status_code
        == 409
    )

    # Retrasar el reloj 7 segundos con dificultad difícil (3 s) => salen 2 cartas.
    with app.app_context():
        partida = db.session.query(Game).filter_by(code="ABC234").one()
        partida.last_called_at = datetime.now(timezone.utc) - timedelta(seconds=7)
        db.session.commit()

    datos = cli.get("/panel/ABC234/estado").get_json()
    assert [c["id"] for c in datos["called_cards"]] == barajar_mazo(semilla)[:2]
    assert datos["current_card"]["id"] == barajar_mazo(semilla)[1]


# ---------- ajustes en vivo y partida terminada ----------


def test_ajustes_actualiza_figura_modo_y_dificultad_y_rechaza_invalidos(app):
    crear_partida_bd(app, code="ABC234", status="en_juego")
    cli = autenticar_panel(app, "ABC234")

    # Simular tiempo viejo en manual antes de cambiar a auto: no debe soltar cartas atrasadas.
    with app.app_context():
        partida = db.session.query(Game).filter_by(code="ABC234").one()
        partida.last_called_at = datetime.now(timezone.utc) - timedelta(seconds=300)
        db.session.commit()

    resp = cli.post(
        "/panel/ABC234/ajustes",
        json={"mode": "auto", "difficulty": "dificil", "figure": "cuatro_esquinas"},
    )
    assert resp.status_code == 200
    datos = resp.get_json()
    assert (datos["mode"], datos["difficulty"], datos["figure"]) == (
        "auto",
        "dificil",
        "cuatro_esquinas",
    )
    assert cli.get("/panel/ABC234/estado").get_json()["called_count"] == 0

    assert cli.post("/panel/ABC234/ajustes", json={"figure": "cruz"}).status_code == 400
    assert cli.post("/panel/ABC234/ajustes", json={}).status_code == 400


def test_partida_terminada_muestra_ganador_y_bloquea_controles(app):
    crear_partida_bd(app, code="ABC234", status="terminada", figure="cuatro_esquinas")
    tablero_id = agregar_jugador_bd(app, "ABC234", username="Ana <script>x</script>")
    with app.app_context():
        partida = db.session.query(Game).filter_by(code="ABC234").one()
        tablero = db.session.get(Board, tablero_id)
        db.session.add(
            Winner(
                game_id=partida.id,
                user_id=tablero.user_id,
                board_id=tablero.id,
                figure="cuatro_esquinas",
            )
        )
        db.session.commit()

    cli = autenticar_panel(app, "ABC234")
    html = cli.get("/panel/ABC234").get_data(as_text=True)
    assert "Ganador confirmado" in html
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html

    assert cli.post("/panel/ABC234/iniciar", headers=JSON_HEADERS).status_code == 409
    assert (
        cli.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS).status_code
        == 409
    )
    assert cli.post("/panel/ABC234/ajustes", json={"mode": "auto"}).status_code == 409
