"""Pruebas de la API de partidas (app/routes/game.py).

Las rutas hacen commit de verdad, así que cada prueba usa `limpia_bd`
(tablas creadas, cartas sembradas y tablas de juego vaciadas al final).
La lógica de app/game/ ya tiene sus propias pruebas; aquí solo se usa
para calcular lo que la API debería responder.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db import db
from app.game import DIFICULTADES, barajar_mazo, generar_tablero
from app.models import Board, BoardCard, CalledCard, Game, User, Winner

pytestmark = pytest.mark.usefixtures("limpia_bd")

FIGURAS = ("fila", "columna", "diagonal", "cuatro_esquinas", "tablero_lleno")
PROFE = ("profe", "profesor")
OTRO_PROFE = ("otro_profe", "profesor")
ANA = ("ana", "jugador")
BETO = ("beto", "jugador")
CODIGO_INEXISTENTE = "NOEXIS"
_PASSWORD_PRUEBA = "clave-prueba-123"


# ---------- utilidades ----------


def cliente_como(client, usuario):
    """Devuelve un test_client autenticado por sesión real para `(username, role)`."""
    if not usuario:
        return client.application.test_client()
    sesiones = getattr(client, "_sesiones", None)
    if sesiones is None:
        sesiones = {}
        client._sesiones = sesiones
    if usuario in sesiones:
        return sesiones[usuario]

    cli = client.application.test_client()
    username, role = usuario
    resp = cli.post(
        "/api/auth/login",
        json={"username": username, "password": _PASSWORD_PRUEBA},
    )
    if resp.status_code == 401:
        resp = cli.post(
            "/api/auth/register",
            json={"username": username, "password": _PASSWORD_PRUEBA, "role": role},
        )
        assert resp.status_code == 201, resp.get_json()
    else:
        assert resp.status_code == 200, resp.get_json()
    sesiones[usuario] = cli
    return cli


def crear_partida(client, **opciones):
    resp = cliente_como(client, PROFE).post("/api/games", json=opciones)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["code"]


def partida_iniciada(client, **opciones):
    code = crear_partida(client, **opciones)
    assert cliente_como(client, PROFE).post(f"/api/games/{code}/start").status_code == 200
    return code


def unirse(client, code, usuario=ANA):
    return cliente_como(client, usuario).post(f"/api/games/{code}/join")


def siguiente(client, code):
    return cliente_como(client, PROFE).post(f"/api/games/{code}/next-card")


def estado(client, code):
    resp = client.get(f"/api/games/{code}/state")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def ajustes(client, code, usuario=PROFE, **cambios):
    return cliente_como(client, usuario).post(f"/api/games/{code}/settings", json=cambios)


def reclamar(client, code, marcadas, usuario=ANA):
    return cliente_como(client, usuario).post(
        f"/api/games/{code}/claim", json={"marcadas": marcadas}
    )


def ids_cantados(datos):
    return [c["id"] for c in datos["called_cards"]]


def semilla_partida(app, code):
    with app.app_context():
        return int(db.session.query(Game).filter_by(code=code).one().seed)


def ultimo_canto(app, code):
    with app.app_context():
        return db.session.query(Game).filter_by(code=code).one().last_called_at


def retrasar_reloj(app, code, segundos):
    """Simula que pasaron `segundos` desde la última carta."""
    with app.app_context():
        partida = db.session.query(Game).filter_by(code=code).one()
        partida.last_called_at = partida.last_called_at - timedelta(seconds=segundos)
        db.session.commit()


def primera_fila(app, code, username="ana"):
    """Ids de las posiciones 0..3 del tablero del jugador, leídos de la base."""
    with app.app_context():
        tablero = (
            db.session.query(Board)
            .join(User, Board.user_id == User.id)
            .join(Game, Board.game_id == Game.id)
            .filter(Game.code == code, User.username == username)
            .one()
        )
        return [c.card_id for c in tablero.cards[:4]]


def cantar_hasta(client, code, objetivo, parar_si=None):
    """Llama a next-card hasta que todas las cartas de `objetivo` estén
    cantadas (o hasta que `parar_si(cantadas)` sea verdadero)."""
    parar_si = parar_si or (lambda cantadas: set(objetivo) <= set(cantadas))
    datos = estado(client, code)
    while not parar_si(ids_cantados(datos)):
        resp = siguiente(client, code)
        assert resp.status_code == 200, resp.get_json()
        datos = resp.get_json()
    return ids_cantados(datos)


def ganadores(app, code):
    with app.app_context():
        return (
            db.session.query(Winner).join(Game).filter(Game.code == code).count()
        )


# ---------- crear partida ----------


def test_crear_partida_valores_por_defecto(client):
    resp = cliente_como(client, PROFE).post("/api/games")
    assert resp.status_code == 201
    datos = resp.get_json()
    assert len(datos["code"]) == 6
    assert (datos["status"], datos["figure"], datos["difficulty"], datos["mode"]) == (
        "espera",
        "fila",
        "normal",
        "manual",
    )
    assert datos["called_cards"] == []
    assert datos["current_card"] is None
    assert datos["remaining"] == 54
    assert datos["winner"] is None
    assert datos["players"] == 0


def test_crear_partida_genera_codigos_unicos(client):
    codigos = {crear_partida(client) for _ in range(20)}
    assert len(codigos) == 20


def test_crear_partida_guarda_semilla_entera_y_anfitrion(app, client):
    code = crear_partida(client)
    with app.app_context():
        partida = db.session.query(Game).filter_by(code=code).one()
        assert isinstance(partida.seed, int)
        assert partida.host.username == "profe"
        assert partida.host.role == "profesor"


def test_crear_partida_con_opciones(client):
    resp = cliente_como(client, PROFE).post(
        "/api/games",
        json={"figure": "cuatro_esquinas", "difficulty": "dificil", "mode": "auto"},
    )
    datos = resp.get_json()
    assert resp.status_code == 201
    assert (datos["figure"], datos["difficulty"], datos["mode"]) == (
        "cuatro_esquinas",
        "dificil",
        "auto",
    )
    assert datos["interval_seconds"] == 3


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"figure": "cruz"},
        {"difficulty": "imposible"},
        {"mode": "rapido"},
        {"figure": 3},
        [1, 2],
        "texto",
    ],
)
def test_crear_partida_rechaza_datos_invalidos(app, client, cuerpo):
    resp = cliente_como(client, PROFE).post("/api/games", json=cuerpo)
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    with app.app_context():
        assert db.session.query(Game).count() == 0


# ---------- autenticación por sesión ----------


@pytest.mark.parametrize(
    "ruta", ["", "/{code}/start", "/{code}/next-card", "/{code}/settings"]
)
def test_rutas_de_profesor_sin_sesion_dan_401(client, ruta):
    code = crear_partida(client)
    resp = client.post("/api/games" + ruta.format(code=code), json={"mode": "auto"})
    assert resp.status_code == 401
    assert "sesión" in resp.get_json()["error"].lower()


@pytest.mark.parametrize("ruta", ["/{code}/join", "/{code}/claim"])
def test_rutas_de_jugador_sin_sesion_dan_401(client, ruta):
    code = partida_iniciada(client)
    resp = client.post("/api/games" + ruta.format(code=code), json={"marcadas": []})
    assert resp.status_code == 401


def test_header_x_user_id_sin_sesion_es_rechazado(client):
    code = crear_partida(client)
    resp = client.post("/api/games", headers={"X-User-Id": "profe"})
    assert resp.status_code == 401
    resp_join = client.post(f"/api/games/{code}/join", headers={"X-User-Id": "ana"})
    assert resp_join.status_code == 401


def test_jugador_no_puede_crear_partida(client):
    code = crear_partida(client)
    unirse(client, code, ANA)
    resp = cliente_como(client, ANA).post("/api/games")
    assert resp.status_code == 403


@pytest.mark.parametrize("quien", [ANA, OTRO_PROFE], ids=["jugador", "otro_profesor"])
@pytest.mark.parametrize("ruta", ["start", "next-card", "settings"])
def test_solo_el_anfitrion_controla_la_partida(client, quien, ruta):
    code = crear_partida(client)
    unirse(client, code, ANA)
    if ruta == "next-card":
        cliente_como(client, PROFE).post(f"/api/games/{code}/start")
    resp = cliente_como(client, quien).post(
        f"/api/games/{code}/{ruta}", json={"mode": "auto"}
    )
    assert resp.status_code == 403


# ---------- 404 ----------


@pytest.mark.parametrize(
    "metodo, ruta, usuario, cuerpo",
    [
        ("post", "join", ANA, None),
        ("post", "start", PROFE, None),
        ("post", "next-card", PROFE, None),
        ("post", "settings", PROFE, {"mode": "auto"}),
        ("get", "state", None, None),
        ("post", "claim", ANA, {"marcadas": []}),
    ],
)
def test_codigo_inexistente_da_404(client, metodo, ruta, usuario, cuerpo):
    cli = cliente_como(client, usuario)
    llamar = getattr(cli, metodo)
    resp = llamar(f"/api/games/{CODIGO_INEXISTENTE}/{ruta}", json=cuerpo)
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_codigo_en_minusculas_funciona(client):
    code = crear_partida(client)
    assert unirse(client, code.lower()).status_code == 201
    assert client.get(f"/api/games/{code.lower()}/state").get_json()["code"] == code


# ---------- join ----------


def test_join_genera_tablero_de_16_cartas_distintas(app, client):
    code = crear_partida(client)
    resp = unirse(client, code)
    assert resp.status_code == 201
    datos = resp.get_json()
    ids = [c["id"] for c in datos["cards"]]

    assert len(ids) == 16
    assert len(set(ids)) == 16
    assert all(1 <= i <= 54 for i in ids)
    assert [c["position"] for c in datos["cards"]] == list(range(16))
    assert all(c["marked"] is False and c["name"] for c in datos["cards"])

    with app.app_context():
        tablero = db.session.get(Board, datos["board_id"])
        assert ids == generar_tablero(int(tablero.seed))
        assert [c.card_id for c in tablero.cards] == ids


def test_join_dos_veces_devuelve_el_mismo_tablero(app, client):
    code = crear_partida(client)
    primera = unirse(client, code)
    segunda = unirse(client, code)

    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.get_json()["board_id"] == primera.get_json()["board_id"]
    assert segunda.get_json()["cards"] == primera.get_json()["cards"]
    with app.app_context():
        assert db.session.query(Board).count() == 1
        assert db.session.query(BoardCard).count() == 16


def test_join_de_dos_jugadores_crea_dos_tableros(client):
    code = crear_partida(client)
    tablero_ana = unirse(client, code, ANA).get_json()
    tablero_beto = unirse(client, code, BETO).get_json()
    assert tablero_ana["board_id"] != tablero_beto["board_id"]
    assert estado(client, code)["players"] == 2


def test_join_se_permite_con_la_partida_en_juego(client):
    code = partida_iniciada(client)
    assert unirse(client, code).status_code == 201


# ---------- start y next-card ----------


def test_start_pone_la_partida_en_juego(app, client):
    code = crear_partida(client)
    resp = cliente_como(client, PROFE).post(f"/api/games/{code}/start")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "en_juego"
    with app.app_context():
        partida = db.session.query(Game).filter_by(code=code).one()
        assert partida.started_at is not None
        assert partida.last_called_at == partida.started_at


def test_start_dos_veces_da_409(client):
    code = partida_iniciada(client)
    assert cliente_como(client, PROFE).post(f"/api/games/{code}/start").status_code == 409


def test_next_card_antes_de_iniciar_da_409(client):
    code = crear_partida(client)
    assert siguiente(client, code).status_code == 409


def test_next_card_sigue_el_orden_del_mazo_sin_repetir(app, client):
    code = partida_iniciada(client)
    mazo = barajar_mazo(semilla_partida(app, code))

    for orden in range(1, 6):
        resp = siguiente(client, code)
        assert resp.status_code == 200
        carta = resp.get_json()["card"]
        assert carta["order"] == orden
        assert carta["id"] == mazo[orden - 1]

    datos = estado(client, code)
    assert ids_cantados(datos) == mazo[:5]
    assert [c["order"] for c in datos["called_cards"]] == [1, 2, 3, 4, 5]
    assert datos["current_card"]["id"] == mazo[4]
    assert datos["remaining"] == 49


def test_next_card_actualiza_last_called_at(app, client):
    code = partida_iniciada(client)
    antes = ultimo_canto(app, code)
    siguiente(client, code)
    assert ultimo_canto(app, code) > antes


def test_next_card_despues_de_54_da_409_y_sigue_en_juego(app, client):
    code = partida_iniciada(client)
    for _ in range(54):
        assert siguiente(client, code).status_code == 200

    resp = siguiente(client, code)
    assert resp.status_code == 409
    datos = estado(client, code)
    assert ids_cantados(datos) == barajar_mazo(semilla_partida(app, code))
    assert datos["remaining"] == 0
    assert datos["status"] == "en_juego"


def test_next_card_en_modo_auto_da_409(client):
    code = partida_iniciada(client, mode="auto")
    assert siguiente(client, code).status_code == 409


# ---------- settings ----------


def test_settings_cambia_mode_difficulty_y_figure(client):
    code = crear_partida(client)
    resp = ajustes(client, code, mode="auto", difficulty="facil", figure="diagonal")
    assert resp.status_code == 200
    datos = resp.get_json()
    assert (datos["mode"], datos["difficulty"], datos["figure"]) == ("auto", "facil", "diagonal")
    assert datos["interval_seconds"] == 9

    datos = estado(client, code)
    assert (datos["mode"], datos["difficulty"], datos["figure"]) == ("auto", "facil", "diagonal")


@pytest.mark.parametrize("figura", FIGURAS)
def test_settings_acepta_cada_figura(client, figura):
    code = crear_partida(client)
    assert ajustes(client, code, figure=figura).get_json()["figure"] == figura


@pytest.mark.parametrize(
    "cambios",
    [
        {"mode": "rapido"},
        {"difficulty": "imposible"},
        {"figure": "cruz"},
        {"figure": "Fila"},
        {"mode": None},
        {"mode": "auto", "figure": "cruz"},  # uno inválido invalida todo
        {},
    ],
)
def test_settings_rechaza_valores_invalidos(client, cambios):
    code = crear_partida(client)
    resp = ajustes(client, code, **cambios)
    assert resp.status_code == 400
    datos = estado(client, code)
    assert (datos["mode"], datos["figure"]) == ("manual", "fila")


@pytest.mark.parametrize("cambio", [{"mode": "auto"}, {"difficulty": "dificil"}])
def test_settings_mode_o_difficulty_reinicia_el_reloj(app, client, cambio):
    code = partida_iniciada(client)
    retrasar_reloj(app, code, 100)
    ajustes(client, code, **cambio)
    transcurrido = datetime.now(timezone.utc) - ultimo_canto(app, code)
    assert transcurrido < timedelta(seconds=5)


def test_settings_solo_figure_no_reinicia_el_reloj(app, client):
    code = partida_iniciada(client)
    retrasar_reloj(app, code, 100)
    antes = ultimo_canto(app, code)
    ajustes(client, code, figure="columna")
    assert ultimo_canto(app, code) == antes


def test_pasar_a_auto_no_suelta_cartas_atrasadas(app, client):
    code = partida_iniciada(client, difficulty="dificil")
    retrasar_reloj(app, code, 300)  # mucho tiempo en manual
    ajustes(client, code, mode="auto")
    assert estado(client, code)["called_cards"] == []


# ---------- reloj automático ----------


@pytest.mark.parametrize("dificultad, segundos", [("facil", 9), ("normal", 5), ("dificil", 3)])
def test_auto_saca_cartas_segun_la_dificultad(app, client, dificultad, segundos):
    assert DIFICULTADES[dificultad] == segundos
    code = partida_iniciada(client, mode="auto", difficulty=dificultad)
    mazo = barajar_mazo(semilla_partida(app, code))

    # Todavía no se cumple el intervalo: no sale nada.
    retrasar_reloj(app, code, segundos - 1)
    assert estado(client, code)["called_cards"] == []

    # Ya pasó un intervalo (segundos - 1 + 2 > segundos): sale una carta.
    retrasar_reloj(app, code, 2)
    assert ids_cantados(estado(client, code)) == mazo[:1]

    # Pasaron tres intervalos más: salen tres de golpe, en orden.
    retrasar_reloj(app, code, 3 * segundos)
    datos = estado(client, code)
    assert ids_cantados(datos) == mazo[:4]
    assert [c["order"] for c in datos["called_cards"]] == [1, 2, 3, 4]


def test_auto_dos_consultas_seguidas_no_repiten_carta(app, client):
    code = partida_iniciada(client, mode="auto", difficulty="dificil")
    retrasar_reloj(app, code, 3 * 2 + 1)

    primera = ids_cantados(estado(client, code))
    segunda = ids_cantados(estado(client, code))
    assert len(primera) == 2
    assert segunda == primera
    with app.app_context():
        assert db.session.query(CalledCard).count() == 2


def test_auto_conserva_el_ritmo_del_reloj(app, client):
    code = partida_iniciada(client, mode="auto", difficulty="normal")
    retrasar_reloj(app, code, 12)  # 2 intervalos de 5 s y sobran 2 s
    antes = ultimo_canto(app, code)
    assert len(estado(client, code)["called_cards"]) == 2
    assert ultimo_canto(app, code) - antes == timedelta(seconds=10)


def test_auto_nunca_pasa_de_54(app, client):
    code = partida_iniciada(client, mode="auto", difficulty="dificil")
    retrasar_reloj(app, code, 3 * 1000)

    datos = estado(client, code)
    assert ids_cantados(datos) == barajar_mazo(semilla_partida(app, code))
    assert datos["remaining"] == 0
    assert datos["status"] == "en_juego"

    retrasar_reloj(app, code, 3 * 1000)
    assert len(estado(client, code)["called_cards"]) == 54
    with app.app_context():
        assert db.session.query(CalledCard).count() == 54


@pytest.mark.parametrize("cambios", [{"mode": "manual"}, None], ids=["manual", "sin_iniciar"])
def test_reloj_no_corre_fuera_de_auto_en_juego(app, client, cambios):
    if cambios is None:
        code = crear_partida(client, mode="auto")
        with app.app_context():  # simula un reloj viejo aunque no haya iniciado
            partida = db.session.query(Game).filter_by(code=code).one()
            partida.last_called_at = datetime.now(timezone.utc) - timedelta(seconds=300)
            db.session.commit()
    else:
        code = partida_iniciada(client, **cambios)
        retrasar_reloj(app, code, 300)
    assert estado(client, code)["called_cards"] == []


# ---------- claim ----------


def test_claim_valido_gana_y_termina_la_partida(app, client):
    code = partida_iniciada(client)
    unirse(client, code, ANA)
    unirse(client, code, BETO)
    ajustes(client, code, figure="fila")
    fila = primera_fila(app, code)
    cantar_hasta(client, code, fila)

    resp = reclamar(client, code, fila)
    assert resp.status_code == 200
    datos = resp.get_json()
    assert datos["valid"] is True
    assert datos["winner"]["username"] == "ana"
    assert datos["winner"]["figure"] == "fila"
    assert datos["status"] == "terminada"

    datos = estado(client, code)
    assert datos["status"] == "terminada"
    assert datos["winner"]["username"] == "ana"
    with app.app_context():
        ganador = db.session.query(Winner).one()
        assert ganador.user.username == "ana"
        assert ganador.figure == "fila"
        assert ganador.game.code == code
        marcadas = {c.card_id for c in ganador.board.cards if c.marked}
        assert marcadas == set(fila)


def test_claim_con_carta_no_cantada_es_invalido(app, client):
    code = partida_iniciada(client)
    unirse(client, code)
    fila = primera_fila(app, code)

    resp = reclamar(client, code, fila)  # no se ha cantado ninguna
    assert resp.status_code == 200
    assert resp.get_json() == {"valid": False}
    assert estado(client, code)["status"] == "en_juego"
    assert ganadores(app, code) == 0


def test_claim_con_figura_incompleta_es_invalido(app, client):
    code = partida_iniciada(client)
    unirse(client, code)
    fila = primera_fila(app, code)
    # Canta hasta que haya al menos una carta de la fila, pero no las cuatro.
    cantadas = cantar_hasta(
        client, code, fila, parar_si=lambda c: 1 <= len(set(fila) & set(c)) < 4
    )
    marcadas = [carta for carta in fila if carta in cantadas]

    resp = reclamar(client, code, marcadas)
    assert resp.get_json() == {"valid": False}
    datos = estado(client, code)
    assert datos["status"] == "en_juego"
    assert datos["winner"] is None
    assert ganadores(app, code) == 0


def test_claim_con_cartas_de_otro_tablero_es_invalido(app, client):
    code = partida_iniciada(client)
    unirse(client, code, ANA)
    unirse(client, code, BETO)
    fila_ana = primera_fila(app, code, "ana")
    cantar_hasta(client, code, fila_ana)
    if set(fila_ana) <= set(primera_fila(app, code, "beto")):
        pytest.skip("tableros con la misma primera fila (casi imposible)")

    assert reclamar(client, code, fila_ana, usuario=BETO).get_json() == {"valid": False}
    assert ganadores(app, code) == 0


def test_claim_usa_la_figura_de_la_partida(app, client):
    code = partida_iniciada(client, figure="tablero_lleno")
    unirse(client, code)
    fila = primera_fila(app, code)
    cantar_hasta(client, code, fila)
    assert reclamar(client, code, fila).get_json() == {"valid": False}
    assert estado(client, code)["status"] == "en_juego"


@pytest.mark.parametrize(
    "marcadas", ["x", [True], [1, "2"], [1.0], None, {"a": 1}], ids=repr
)
def test_claim_con_marcadas_invalidas_da_400(client, marcadas):
    code = partida_iniciada(client)
    unirse(client, code)
    assert reclamar(client, code, marcadas).status_code == 400


def test_claim_sin_tablero_da_404(client):
    code = partida_iniciada(client)
    assert reclamar(client, code, [], usuario=("intruso", "jugador")).status_code == 404


def test_claim_antes_de_iniciar_da_409(client):
    code = crear_partida(client)
    unirse(client, code)
    assert reclamar(client, code, []).status_code == 409


def _partida_ganada_por_ana(app, client):
    code = partida_iniciada(client)
    unirse(client, code, ANA)
    unirse(client, code, BETO)
    fila = primera_fila(app, code)
    cantar_hasta(client, code, fila)
    assert reclamar(client, code, fila).get_json()["valid"] is True
    return code, fila


def test_claim_en_partida_terminada_da_409(app, client):
    code, fila = _partida_ganada_por_ana(app, client)
    assert reclamar(client, code, [], usuario=BETO).status_code == 409
    assert reclamar(client, code, fila, usuario=ANA).status_code == 409
    assert ganadores(app, code) == 1


def test_partida_terminada_rechaza_next_card_y_settings(app, client):
    code, _ = _partida_ganada_por_ana(app, client)
    assert siguiente(client, code).status_code == 409
    assert ajustes(client, code, mode="auto").status_code == 409


def test_join_en_partida_terminada_solo_para_quien_ya_tenia_tablero(app, client):
    code, _ = _partida_ganada_por_ana(app, client)
    assert unirse(client, code, ANA).status_code == 200
    assert unirse(client, code, ("tarde", "jugador")).status_code == 409


def test_claim_en_auto_pone_al_dia_las_cartas_antes_de_validar(app, client):
    code = partida_iniciada(client, mode="auto", difficulty="dificil")
    unirse(client, code)
    fila = primera_fila(app, code)
    retrasar_reloj(app, code, 3 * 1000)  # nadie consultó /state, pero ya salieron todas
    assert reclamar(client, code, fila).get_json()["valid"] is True
