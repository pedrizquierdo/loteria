"""Pruebas de creación de salas con código y unión de alumnos (app/salas.py y app/routes/salas.py).

Cada prueba usa `limpia_bd` (tablas creadas, 54 cartas sembradas y tablas de
juego vaciadas al terminar), siguiendo la misma convención que `test_game_routes.py`.
"""

import re
from urllib.parse import urlparse

import pytest

from app import salas as modulo_salas
from app.db import db
from app.game import generar_tablero
from app.models import Board, BoardCard, Game, User
from app.salas import ALFABETO_CODIGO, LARGO_CODIGO

pytestmark = pytest.mark.usefixtures("limpia_bd")

PASSWORD_PRUEBA = "clave-salas-123"


# ---------- utilidades ----------


def registrar_y_entrar(app, username, role="jugador"):
    """Crea un test_client autenticado por sesión real vía `/api/auth/register`."""
    cli = app.test_client()
    resp = cli.post(
        "/api/auth/register",
        json={"username": username, "password": PASSWORD_PRUEBA, "role": role},
    )
    assert resp.status_code == 201, resp.get_json()
    return cli


def extraer_codigo_de_redirect(resp):
    """Extrae el código de la URL de redirección `/salas/<CODE>`."""
    assert resp.status_code in (302, 303), resp.get_data(as_text=True)
    ruta = urlparse(resp.headers["Location"]).path
    coincidencia = re.fullmatch(r"/salas/([A-Z0-9]+)", ruta)
    assert coincidencia is not None, f"Redirección inesperada: {ruta}"
    return coincidencia.group(1)


def crear_sala_web(cliente, username="Prof. Luis", **opciones):
    datos = {"username": username, **opciones}
    resp = cliente.post("/salas/crear", data=datos)
    return extraer_codigo_de_redirect(resp), resp


def unirse_web(cliente, code, username="Ana"):
    return cliente.post("/salas/unirse", data={"code": code, "username": username})


# ---------- pantallas de inicio y navegación ----------


def test_inicio_salas_muestra_accesos_a_crear_y_unirse(client):
    resp = client.get("/salas/")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Salas de Lotería Mexicana" in html
    assert "/salas/crear" in html
    assert "/salas/unirse" in html


def test_pantalla_crear_sala_responde_200(client):
    resp = client.get("/salas/crear")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'name="username"' in html
    assert 'name="figure"' in html
    assert 'name="mode"' in html
    assert 'name="difficulty"' in html


def test_pantalla_unirse_responde_200_y_prellena_codigo_desde_query(app, client):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, figure="diagonal")

    resp = client.get(f"/salas/unirse?code={codigo.lower()}")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert f'value="{codigo}"' in html
    assert f"Sala {codigo}" in html
    assert "Diagonal" in html


def test_pantalla_unirse_con_codigo_inexistente_en_query_muestra_aviso(client):
    resp = client.get("/salas/unirse?code=noexis")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'value="NOEXIS"' in html
    assert "No existe una sala con el código NOEXIS" in html


def test_atajo_unirse_con_codigo_redirige_a_unirse_normalizado(client):
    resp = client.get("/salas/ab12cd/unirse")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/salas/unirse?code=AB12CD")


# ---------- crear sala (profesor) ----------


def test_crear_sala_con_valores_por_defecto_guarda_en_bd_y_muestra_codigo(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis")

    assert len(codigo) == LARGO_CODIGO
    assert all(ch in ALFABETO_CODIGO for ch in codigo)

    with app.app_context():
        partida = db.session.query(Game).filter_by(code=codigo).one()
        assert partida.host.username == "Prof. Luis"
        assert partida.host.role == "profesor"
        assert (partida.status, partida.figure, partida.difficulty, partida.mode) == (
            "espera",
            "fila",
            "normal",
            "manual",
        )
        assert isinstance(partida.seed, int)

    vista = cliente_profe.get(f"/salas/{codigo}")
    html = vista.get_data(as_text=True)
    assert vista.status_code == 200
    assert codigo in html
    assert f"/salas/unirse?code={codigo}" in html
    assert "En espera" in html
    assert "Fila" in html


def test_crear_sala_con_opciones_personalizadas(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(
        cliente_profe,
        username="Prof. Elena",
        figure="cuatro_esquinas",
        difficulty="dificil",
        mode="auto",
    )

    with app.app_context():
        partida = db.session.query(Game).filter_by(code=codigo).one()
        assert (partida.figure, partida.difficulty, partida.mode) == (
            "cuatro_esquinas",
            "dificil",
            "auto",
        )

    html = cliente_profe.get(f"/salas/{codigo}").get_data(as_text=True)
    assert "Cuatro esquinas" in html
    assert "Automático" in html
    assert "Difícil" in html


def test_crear_multiples_salas_genera_codigos_unicos(app):
    cliente_profe = app.test_client()
    codigos = {crear_sala_web(cliente_profe)[0] for _ in range(15)}
    assert len(codigos) == 15


@pytest.mark.parametrize(
    "payload",
    [
        {"username": ""},
        {"username": "   "},
        {"username": "a" * 81},
        {"username": "Prof. Luis", "figure": "cruz"},
        {"username": "Prof. Luis", "difficulty": "imposible"},
        {"username": "Prof. Luis", "mode": "rapido"},
    ],
)
def test_crear_sala_rechaza_datos_invalidos(app, client, payload):
    resp = client.post("/salas/crear", data=payload)

    assert resp.status_code == 400
    assert 'role="alert"' in resp.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(Game).count() == 0


def test_jugador_existente_no_puede_crear_sala(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis")

    cliente_alumno = app.test_client()
    assert unirse_web(cliente_alumno, codigo, username="Ana").status_code == 302

    resp = cliente_alumno.post("/salas/crear", data={"username": "Ana"})
    assert resp.status_code == 403
    assert "jugador" in resp.get_data(as_text=True).lower()
    with app.app_context():
        assert db.session.query(Game).count() == 1


def test_crear_sala_reintenta_si_colisiona_codigo_y_da_503_si_se_agotan(
    app, monkeypatch
):
    cliente_profe = app.test_client()
    codigo_existente, _ = crear_sala_web(cliente_profe, username="Prof. Luis")

    # Primero colisiona una vez y luego devuelve un código libre.
    secuencia = iter([codigo_existente, "K7M9P2"])
    monkeypatch.setattr(modulo_salas, "generar_codigo_sala", lambda: next(secuencia))
    nuevo_codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis")
    assert nuevo_codigo == "K7M9P2"

    # Si siempre colisiona, responde 503 sin crear una tercera partida.
    monkeypatch.setattr(modulo_salas, "generar_codigo_sala", lambda: codigo_existente)
    resp = cliente_profe.post("/salas/crear", data={"username": "Prof. Luis"})
    assert resp.status_code == 503
    with app.app_context():
        assert db.session.query(Game).count() == 2


# ---------- unirse a sala (alumno desde celular) ----------


def test_alumno_se_une_y_recibe_tablero_de_16_cartas_unicas(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis", figure="columna")

    cliente_ana = app.test_client()
    resp = unirse_web(cliente_ana, codigo, username="Ana López")

    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == f"/salas/{codigo}/jugador"

    with app.app_context():
        ana = db.session.query(User).filter_by(username="Ana López").one()
        assert ana.role == "jugador"
        tablero = db.session.query(Board).filter_by(user_id=ana.id).one()
        ids = [c.card_id for c in tablero.cards]
        nombres = [c.card.name for c in tablero.cards]

        assert len(ids) == 16
        assert len(set(ids)) == 16
        assert all(1 <= i <= 54 for i in ids)
        assert [c.position for c in tablero.cards] == list(range(16))
        assert ids == generar_tablero(int(tablero.seed))

    vista = cliente_ana.get(f"/salas/{codigo}/jugador")
    html = vista.get_data(as_text=True)
    assert vista.status_code == 200
    assert codigo in html
    assert "Ana López" in html
    assert "Columna" in html
    assert "Esperando a que el profesor inicie la partida" in html
    for nombre_carta in nombres:
        assert nombre_carta in html


def test_unirse_acepta_codigo_en_minusculas_y_con_espacios(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe)

    cliente_alumno = app.test_client()
    codigo_sucio = f"  {codigo[:3].lower()} {codigo[3:].lower()}  "
    resp = unirse_web(cliente_alumno, codigo_sucio, username="Beto")

    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == f"/salas/{codigo}/jugador"


def test_unirse_dos_veces_devuelve_el_mismo_tablero_sin_duplicar(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe)

    cliente_ana = app.test_client()
    assert unirse_web(cliente_ana, codigo, username="Ana").status_code == 302
    with app.app_context():
        tablero_1 = db.session.query(Board).one()
        id_1 = tablero_1.id
        cartas_1 = [c.card_id for c in tablero_1.cards]

    # Vuelve a enviar el formulario desde otro navegador/sesión con el mismo nombre.
    otro_navegador = app.test_client()
    resp = unirse_web(otro_navegador, codigo, username="Ana")
    assert resp.status_code == 302

    with app.app_context():
        assert db.session.query(Board).count() == 1
        assert db.session.query(BoardCard).count() == 16
        tablero_2 = db.session.query(Board).one()
        assert tablero_2.id == id_1
        assert [c.card_id for c in tablero_2.cards] == cartas_1


def test_varios_alumnos_se_unen_y_aparecen_en_la_sala_del_profesor(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis")

    for alumno in ("Ana", "Beto", "Carla"):
        cli = app.test_client()
        assert unirse_web(cli, codigo, username=alumno).status_code == 302

    html_profe = cliente_profe.get(f"/salas/{codigo}").get_data(as_text=True)
    assert "Ana" in html_profe
    assert "Beto" in html_profe
    assert "Carla" in html_profe

    estado = cliente_profe.get(f"/salas/{codigo}/estado").get_json()
    assert estado["players_count"] == 3
    assert estado["players"] == ["Ana", "Beto", "Carla"]


def test_unirse_con_codigo_inexistente_da_404_y_no_crea_usuario(app, client):
    resp = unirse_web(client, "NOEXIS", username="Fantasma")

    assert resp.status_code == 404
    assert "No existe una sala con el código NOEXIS" in resp.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(User).filter_by(username="Fantasma").count() == 0


@pytest.mark.parametrize(
    "code, username",
    [
        ("", "Ana"),
        ("   ", "Ana"),
        ("CODIGO_DEMASIADO_LARGO", "Ana"),
        ("ABC234", ""),
        ("ABC234", "   "),
        ("ABC234", "x" * 81),
    ],
)
def test_unirse_rechaza_entradas_invalidas_con_400(app, client, code, username):
    resp = unirse_web(client, code, username=username)
    assert resp.status_code == 400
    assert 'role="alert"' in resp.get_data(as_text=True)


def test_unirse_se_permite_cuando_la_partida_esta_en_juego(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis")

    with app.app_context():
        partida = db.session.query(Game).filter_by(code=codigo).one()
        partida.status = "en_juego"
        db.session.commit()

    cliente_ana = app.test_client()
    resp = unirse_web(cliente_ana, codigo, username="Ana")
    assert resp.status_code == 302

    html = cliente_ana.get(f"/salas/{codigo}/jugador").get_data(as_text=True)
    assert "En juego" in html


def test_unirse_en_partida_terminada_solo_permite_a_quien_ya_tenia_tablero(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis")

    cliente_ana = app.test_client()
    assert unirse_web(cliente_ana, codigo, username="Ana").status_code == 302

    with app.app_context():
        partida = db.session.query(Game).filter_by(code=codigo).one()
        partida.status = "terminada"
        db.session.commit()

    # Un alumno nuevo no puede entrar y no queda registrado como usuario huérfano.
    cliente_nuevo = app.test_client()
    resp_nuevo = unirse_web(cliente_nuevo, codigo, username="Tarde")
    assert resp_nuevo.status_code == 409
    assert "terminó" in resp_nuevo.get_data(as_text=True).lower()
    with app.app_context():
        assert db.session.query(User).filter_by(username="Tarde").count() == 0

    # Ana sí puede volver a entrar para consultar su tablero.
    resp_ana = unirse_web(app.test_client(), codigo, username="Ana")
    assert resp_ana.status_code == 302


# ---------- control de vistas y redirecciones ----------


def test_visitante_sin_sesion_en_ver_sala_es_redirigido_a_unirse(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe)

    visitante = app.test_client()
    resp = visitante.get(f"/salas/{codigo}")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/salas/unirse?code={codigo}")


def test_alumno_unido_que_abre_url_de_sala_va_a_su_vista_de_jugador(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe)

    cliente_ana = app.test_client()
    unirse_web(cliente_ana, codigo, username="Ana")

    resp = cliente_ana.get(f"/salas/{codigo}")
    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == f"/salas/{codigo}/jugador"


def test_visitante_sin_tablero_en_vista_jugador_es_redirigido_a_unirse(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe)

    visitante = app.test_client()
    resp = visitante.get(f"/salas/{codigo}/jugador")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/salas/unirse?code={codigo}")


@pytest.mark.parametrize("ruta", ["/salas/NOEXIS", "/salas/NOEXIS/jugador"])
def test_rutas_de_sala_inexistente_responden_404(client, ruta):
    resp = client.get(ruta)
    assert resp.status_code == 404
    assert "NOEXIS" in resp.get_data(as_text=True)


# ---------- endpoint de estado en vivo ----------


def test_estado_sala_devuelve_json_completo_y_acepta_minusculas(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(
        cliente_profe,
        username="Prof. Luis",
        figure="tablero_lleno",
        difficulty="facil",
        mode="auto",
    )
    unirse_web(app.test_client(), codigo, username="Ana")

    resp = cliente_profe.get(f"/salas/{codigo.lower()}/estado")
    assert resp.status_code == 200
    datos = resp.get_json()
    assert datos["code"] == codigo
    assert datos["host"] == "Prof. Luis"
    assert datos["status"] == "espera"
    assert datos["figure"] == "tablero_lleno"
    assert datos["mode"] == "auto"
    assert datos["difficulty"] == "facil"
    assert datos["interval_seconds"] == 9
    assert datos["players_count"] == 1
    assert datos["players"] == ["Ana"]
    assert datos["called_count"] == 0
    assert datos["remaining"] == 54


def test_estado_sala_inexistente_da_404_json(client):
    resp = client.get("/salas/NOEXIS/estado")
    assert resp.status_code == 404
    assert resp.is_json
    assert "error" in resp.get_json()


# ---------- interoperabilidad con API /api/games (sesión real) ----------


def test_sala_creada_en_web_es_compatible_con_api_games(app):
    cliente_profe = registrar_y_entrar(app, "profe_web", role="profesor")
    codigo, _ = crear_sala_web(cliente_profe, username="profe_web", figure="diagonal")

    resp_estado = cliente_profe.get(f"/api/games/{codigo}/state")
    assert resp_estado.status_code == 200
    datos = resp_estado.get_json()
    assert datos["code"] == codigo
    assert datos["figure"] == "diagonal"
    assert datos["status"] == "espera"

    resp_start = cliente_profe.post(f"/api/games/{codigo}/start")
    assert resp_start.status_code == 200
    assert resp_start.get_json()["status"] == "en_juego"


def test_sala_creada_por_api_permite_unirse_desde_web_y_comparte_tablero(app):
    cliente_profe = registrar_y_entrar(app, "profe_api", role="profesor")
    resp_crear = cliente_profe.post(
        "/api/games",
        json={"figure": "fila", "difficulty": "normal", "mode": "manual"},
    )
    assert resp_crear.status_code == 201
    codigo = resp_crear.get_json()["code"]

    # Alumna registrada con sesión real se une desde el celular (pantalla web).
    cliente_ana = registrar_y_entrar(app, "ana", role="jugador")
    assert unirse_web(cliente_ana, codigo, username="ana").status_code == 302

    # La API refleja el jugador y devuelve exactamente el mismo tablero si vuelve a llamar /join.
    assert cliente_profe.get(f"/api/games/{codigo}/state").get_json()["players"] == 1

    resp_join_api = cliente_ana.post(f"/api/games/{codigo}/join")
    assert resp_join_api.status_code == 200  # ya tenía tablero
    with app.app_context():
        tablero = db.session.query(Board).one()
        assert resp_join_api.get_json()["board_id"] == tablero.id
        assert [c["id"] for c in resp_join_api.get_json()["cards"]] == [
            c.card_id for c in tablero.cards
        ]


# ---------- seguridad y cuentas registradas ----------


def test_cuenta_con_contrasena_real_no_puede_suplantarse_en_salas(app):
    cliente_profe = registrar_y_entrar(app, "profe_seguro", role="profesor")
    cliente_ana = registrar_y_entrar(app, "ana_segura", role="jugador")

    # Un visitante sin sesión no puede crear sala usando el nombre del profesor registrado.
    intruso = app.test_client()
    resp_crear = intruso.post("/salas/crear", data={"username": "profe_seguro"})
    assert resp_crear.status_code == 401
    assert "/auth/login" in resp_crear.get_data(as_text=True)

    # El profesor autenticado sí puede crear la sala normalmente.
    codigo, _ = crear_sala_web(cliente_profe, username="profe_seguro")

    # Ana autenticada se une a la sala.
    assert unirse_web(cliente_ana, codigo, username="ana_segura").status_code == 302

    # Un intruso sin sesión no puede robar el tablero de Ana escribiendo su nombre.
    resp_robar = unirse_web(app.test_client(), codigo, username="ana_segura")
    assert resp_robar.status_code == 401
    assert "/auth/login" in resp_robar.get_data(as_text=True)


def test_nombre_con_html_se_escapa_en_vistas(app):
    cliente_profe = app.test_client()
    codigo, _ = crear_sala_web(cliente_profe, username="Prof. Luis")

    nombre_malicioso = "<script>alert('xss')</script>"
    cliente_alumno = app.test_client()
    assert unirse_web(cliente_alumno, codigo, username=nombre_malicioso).status_code == 302

    html_alumno = cliente_alumno.get(f"/salas/{codigo}/jugador").get_data(as_text=True)
    html_profe = cliente_profe.get(f"/salas/{codigo}").get_data(as_text=True)

    assert nombre_malicioso not in html_alumno
    assert nombre_malicioso not in html_profe
    assert "&lt;script&gt;" in html_alumno
    assert "&lt;script&gt;" in html_profe
