"""Pruebas del panel del profesor con autenticación por sesión real (app/panel.py y app/routes/panel.py)."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.db import db
from app.game import barajar_mazo, generar_tablero
from app.models import Board, BoardCard, Game, User, Winner

pytestmark = pytest.mark.usefixtures("limpia_bd")

JSON_HEADERS = {"Accept": "application/json"}
PASSWORD_PRUEBA = "clave-panel-123"


# ---------- utilidades ----------


def cliente_autenticado(app, username, role="profesor"):
    """Registra o inicia sesión real vía `/api/auth/*` y devuelve el test_client."""
    cli = app.test_client()
    resp = cli.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD_PRUEBA},
    )
    if resp.status_code == 401:
        resp = cli.post(
            "/api/auth/register",
            json={"username": username, "password": PASSWORD_PRUEBA, "role": role},
        )
        assert resp.status_code == 201, resp.get_json()
    else:
        assert resp.status_code == 200, resp.get_json()
    return cli


def crear_usuario_bd(app, username, role="jugador"):
    with app.app_context():
        usuario = db.session.query(User).filter_by(username=username).one_or_none()
        if usuario is None:
            usuario = User(username=username, password_hash="!prueba", role=role)
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
    cli = cliente_autenticado(app, host_name, role="profesor")
    with app.app_context():
        host = db.session.query(User).filter_by(username=host_name).one()
        ahora = datetime.now(timezone.utc)
        partida = Game(
            code=code,
            host_id=host.id,
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
    return cli


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


# ---------- autenticación, suplantación y permisos ----------


def test_sin_sesion_vistas_redirigen_a_login_y_todos_los_post_dan_401(app):
    crear_partida_bd(app, code="ABC234", host_name="profe_luis")
    anon = app.test_client()

    # Vistas GET redirigen a /auth/login con ?next=...
    resp_index = anon.get("/panel/")
    assert resp_index.status_code == 302
    assert urlparse(resp_index.headers["Location"]).path == "/auth/login"

    resp_panel = anon.get("/panel/ABC234")
    assert resp_panel.status_code == 302
    destino_panel = urlparse(resp_panel.headers["Location"])
    assert destino_panel.path == "/auth/login"
    assert parse_qs(destino_panel.query)["next"] == ["/panel/ABC234"]

    # GET /estado sin sesión da 401
    assert anon.get("/panel/ABC234/estado").status_code == 401

    # Todos los POST sin sesión (HTML o JSON) dan 401
    assert (
        anon.post(
            "/panel/acceder", data={"code": "ABC234", "username": "profe_luis"}
        ).status_code
        == 401
    )
    assert anon.post("/panel/ABC234/iniciar").status_code == 401
    assert anon.post("/panel/ABC234/iniciar", headers=JSON_HEADERS).status_code == 401
    assert anon.post("/panel/ABC234/siguiente-carta").status_code == 401
    assert (
        anon.post("/panel/ABC234/siguiente-carta", headers=JSON_HEADERS).status_code
        == 401
    )
    assert anon.post("/panel/ABC234/ajustes", data={"mode": "auto"}).status_code == 401
    assert anon.post("/panel/ABC234/ajustes", json={"mode": "auto"}).status_code == 401

    # El intento previo en /panel/acceder no dejó ninguna sesión de profesor abierta.
    assert anon.get("/panel/ABC234").status_code == 302


@pytest.mark.parametrize(
    "atacante, rol",
    [("alumno_curioso", "jugador"), ("otro_profe", "profesor")],
    ids=["jugador", "otro_profesor"],
)
def test_no_anfitrion_no_puede_entrar_a_acceder_aunque_mande_username_del_profesor(
    app, atacante, rol
):
    crear_partida_bd(app, code="ABC234", host_name="profe_luis")
    cli_atacante = cliente_autenticado(app, atacante, role=rol)

    # Incluso enviando `username=profe_luis` en el POST, debe rechazarse con 403.
    resp_acceder = cli_atacante.post(
        "/panel/acceder", data={"code": "ABC234", "username": "profe_luis"}
    )
    assert resp_acceder.status_code == 403

    assert cli_atacante.get("/panel/ABC234").status_code == 403
    assert cli_atacante.get("/panel/ABC234/estado").status_code == 403
    assert (
        cli_atacante.post("/panel/ABC234/iniciar", headers=JSON_HEADERS).status_code
        == 403
    )
    assert (
        cli_atacante.post(
            "/panel/ABC234/siguiente-carta", headers=JSON_HEADERS
        ).status_code
        == 403
    )
    assert (
        cli_atacante.post("/panel/ABC234/ajustes", json={"mode": "auto"}).status_code
        == 403
    )


def test_jugador_autenticado_no_puede_abrir_pantalla_acceso_panel(app):
    cli_alumno = cliente_autenticado(app, "ana_alumna", role="jugador")
    assert cli_alumno.get("/panel/").status_code == 403


def test_acceso_exitoso_del_anfitrion_sin_campo_username_y_muestra_partidas(app):
    cli = crear_partida_bd(app, code="ABC234", host_name="profe_luis")
    agregar_jugador_bd(app, "ABC234", username="Ana")
    agregar_jugador_bd(app, "ABC234", username="Beto")

    acceso = cli.get("/panel/")
    html_acceso = acceso.get_data(as_text=True)
    assert acceso.status_code == 200
    assert 'name="code"' in html_acceso
    assert 'name="username"' not in html_acceso
    assert "ABC234" in html_acceso

    resp = cli.post("/panel/acceder", data={"code": "  abc 234  "})
    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == "/panel/ABC234"

    vista = cli.get("/panel/ABC234")
    html = vista.get_data(as_text=True)
    assert vista.status_code == 200
    assert "ABC234" in html
    assert "profe_luis" in html
    assert "Ana" in html
    assert "Beto" in html
    assert "Iniciar partida" in html


def test_panel_partida_inexistente_da_404(app):
    cli = crear_partida_bd(app, code="ABC234", host_name="profe_luis")
    assert cli.post("/panel/acceder", data={"code": "NOEXIS"}).status_code == 404
    assert cli.get("/panel/NOEXIS").status_code == 404
    assert cli.get("/panel/NOEXIS/estado").status_code == 404


# ---------- iniciar y cantar cartas (modo manual) ----------


def test_iniciar_y_sacar_cartas_sigue_orden_del_mazo_y_se_refleja_en_api(app):
    semilla = 9876
    cli = crear_partida_bd(app, code="ABC234", seed=semilla)

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
    cli = crear_partida_bd(app, code="ABC234")

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
    cli = crear_partida_bd(app, code="ABC234", status="en_juego")

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
    cli = crear_partida_bd(
        app,
        code="ABC234",
        status="en_juego",
        mode="auto",
        difficulty="dificil",
        seed=semilla,
    )

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
    cli = crear_partida_bd(app, code="ABC234", status="en_juego")

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
    cli = crear_partida_bd(
        app, code="ABC234", status="terminada", figure="cuatro_esquinas"
    )
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
