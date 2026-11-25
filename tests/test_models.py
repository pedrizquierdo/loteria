"""Pruebas de los modelos de base de datos y del comando `flask seed-cards`."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.game import barajar_mazo, generar_tablero
from app.models import (
    Board,
    BoardCard,
    CalledCard,
    Card,
    Game,
    User,
    Winner,
)

FIGURAS = ("fila", "columna", "diagonal", "cuatro_esquinas", "tablero_lleno")


# ---------- utilidades ----------


@pytest.fixture
def cartas(db_session):
    """Garantiza las 54 cartas (dentro de la transacción de la prueba)."""
    for numero in range(1, 55):
        if db_session.get(Card, numero) is None:
            db_session.add(Card(id=numero, name=f"Carta {numero}"))
    db_session.flush()


def crear_usuario(session, username="ana", role="jugador"):
    usuario = User(username=username, password_hash="hash-falso", role=role)
    session.add(usuario)
    session.flush()
    return usuario


def crear_partida(session, host=None, code="ABC123", **campos):
    if host is None:
        host = crear_usuario(session, username=f"profe-{code}", role="profesor")
    datos = {"figure": "fila", "difficulty": "normal", "mode": "manual", "seed": 42}
    datos.update(campos)
    partida = Game(code=code, host=host, **datos)
    session.add(partida)
    session.flush()
    return partida


def crear_tablero(session, partida, usuario, seed=7):
    tablero = Board(game=partida, user=usuario, seed=seed)
    session.add(tablero)
    session.flush()
    return tablero


def esperar_integrity_error(session, objeto):
    session.add(objeto)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------- crear, guardar y leer ----------


def test_user_se_guarda_y_lee(db_session):
    crear_usuario(db_session, username="profe", role="profesor")
    db_session.commit()
    db_session.expire_all()

    usuario = db_session.query(User).filter_by(username="profe").one()
    assert usuario.role == "profesor"
    assert usuario.password_hash == "hash-falso"
    assert usuario.created_at is not None


def test_user_rol_por_defecto_es_jugador(db_session):
    usuario = User(username="beto", password_hash="x")
    db_session.add(usuario)
    db_session.flush()
    assert usuario.role == "jugador"


def test_card_se_guarda_con_id_igual_al_numero(db_session):
    db_session.query(Card).filter_by(id=1).delete()
    db_session.add(Card(id=1, name="Prueba Gallo", image="gallo.png"))
    db_session.commit()
    db_session.expire_all()

    carta = db_session.get(Card, 1)
    assert carta.name == "Prueba Gallo"
    assert carta.image == "gallo.png"


def test_card_imagen_es_opcional(db_session):
    db_session.query(Card).filter_by(id=2).delete()
    db_session.add(Card(id=2, name="Prueba Diablito"))
    db_session.flush()
    assert db_session.get(Card, 2).image is None


def test_game_se_guarda_y_lee_con_valores_por_defecto(db_session):
    host = crear_usuario(db_session, username="profe", role="profesor")
    db_session.add(Game(code="XYZ", host=host, figure="diagonal", seed=123))
    db_session.commit()
    db_session.expire_all()

    partida = db_session.query(Game).filter_by(code="XYZ").one()
    assert partida.host.username == "profe"
    assert partida.figure == "diagonal"
    assert partida.seed == 123
    assert (partida.difficulty, partida.mode, partida.status) == (
        "normal",
        "manual",
        "espera",
    )
    assert partida.created_at is not None
    assert partida.started_at is None
    assert partida.last_called_at is None
    assert host.hosted_games == [partida]


def test_game_acepta_semilla_grande(db_session):
    partida = crear_partida(db_session, seed=2**40)
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(Game, partida.id).seed == 2**40


@pytest.mark.parametrize("figura", FIGURAS)
def test_game_acepta_cada_figura_valida(db_session, figura):
    partida = crear_partida(db_session, code=f"F-{figura[:8]}", figure=figura)
    assert partida.id is not None


def test_board_se_guarda_y_lee(db_session):
    partida = crear_partida(db_session)
    jugador = crear_usuario(db_session)
    crear_tablero(db_session, partida, jugador, seed=99)
    db_session.commit()
    db_session.expire_all()

    tablero = db_session.query(Board).one()
    assert tablero.seed == 99
    assert tablero.game.code == "ABC123"
    assert tablero.user.username == "ana"
    assert partida.boards == [tablero]
    assert jugador.boards == [tablero]


def test_board_card_se_guarda_y_lee(db_session, cartas):
    tablero = crear_tablero(db_session, crear_partida(db_session), crear_usuario(db_session))
    db_session.add(BoardCard(board=tablero, card_id=10, position=0))
    db_session.commit()
    db_session.expire_all()

    casilla = db_session.query(BoardCard).one()
    assert casilla.position == 0
    assert casilla.marked is False
    assert casilla.card.id == 10
    assert casilla.board.id == tablero.id


def test_called_card_se_guarda_y_lee(db_session, cartas):
    partida = crear_partida(db_session)
    db_session.add(CalledCard(game=partida, card_id=5, order=1))
    db_session.commit()
    db_session.expire_all()

    cantada = db_session.query(CalledCard).one()
    assert (cantada.card.id, cantada.order) == (5, 1)
    assert cantada.game.id == partida.id
    assert cantada.called_at is not None


def test_winner_se_guarda_y_lee(db_session):
    partida = crear_partida(db_session)
    jugador = crear_usuario(db_session)
    tablero = crear_tablero(db_session, partida, jugador)
    db_session.add(Winner(game=partida, user=jugador, board=tablero, figure="fila"))
    db_session.commit()
    db_session.expire_all()

    ganador = db_session.query(Winner).one()
    assert ganador.figure == "fila"
    assert ganador.won_at is not None
    assert ganador.game.id == partida.id
    assert ganador.user.username == "ana"
    assert ganador.board.id == tablero.id
    assert partida.winners == [ganador]
    assert jugador.wins == [ganador]
    assert tablero.wins == [ganador]


# ---------- restricciones únicas ----------


def test_username_unico(db_session):
    crear_usuario(db_session, username="repetido")
    esperar_integrity_error(
        db_session, User(username="repetido", password_hash="x", role="jugador")
    )


def test_code_de_game_unico(db_session):
    host = crear_usuario(db_session, role="profesor")
    crear_partida(db_session, host=host, code="DUP")
    esperar_integrity_error(
        db_session, Game(code="DUP", host=host, figure="fila", seed=1)
    )


def test_un_tablero_por_jugador_por_partida(db_session):
    partida = crear_partida(db_session)
    jugador = crear_usuario(db_session)
    crear_tablero(db_session, partida, jugador, seed=1)
    esperar_integrity_error(db_session, Board(game=partida, user=jugador, seed=2))


def test_board_card_posicion_unica_por_tablero(db_session, cartas):
    tablero = crear_tablero(db_session, crear_partida(db_session), crear_usuario(db_session))
    db_session.add(BoardCard(board=tablero, card_id=1, position=3))
    db_session.flush()
    esperar_integrity_error(db_session, BoardCard(board=tablero, card_id=2, position=3))


def test_board_card_carta_unica_por_tablero(db_session, cartas):
    tablero = crear_tablero(db_session, crear_partida(db_session), crear_usuario(db_session))
    db_session.add(BoardCard(board=tablero, card_id=1, position=0))
    db_session.flush()
    esperar_integrity_error(db_session, BoardCard(board=tablero, card_id=1, position=1))


def test_called_card_unica_por_partida(db_session, cartas):
    partida = crear_partida(db_session)
    db_session.add(CalledCard(game=partida, card_id=7, order=1))
    db_session.flush()
    esperar_integrity_error(db_session, CalledCard(game=partida, card_id=7, order=2))


def test_misma_carta_en_tableros_y_partidas_distintas_si_se_permite(db_session, cartas):
    partida_a = crear_partida(db_session, code="A")
    partida_b = crear_partida(db_session, code="B")
    jugador_1 = crear_usuario(db_session, username="j1")
    jugador_2 = crear_usuario(db_session, username="j2")
    tablero_1 = crear_tablero(db_session, partida_a, jugador_1)
    tablero_2 = crear_tablero(db_session, partida_a, jugador_2)
    db_session.add_all(
        [
            BoardCard(board=tablero_1, card_id=1, position=0),
            BoardCard(board=tablero_2, card_id=1, position=0),
            CalledCard(game=partida_a, card_id=1, order=1),
            CalledCard(game=partida_b, card_id=1, order=1),
        ]
    )
    db_session.flush()
    assert db_session.query(BoardCard).count() == 2
    assert db_session.query(CalledCard).count() == 2


# ---------- valores inválidos ----------


@pytest.mark.parametrize("rol", ["admin", "Profesor", ""])
def test_rol_invalido_es_rechazado(db_session, rol):
    esperar_integrity_error(db_session, User(username="x", password_hash="x", role=rol))


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("status", "pausada"),
        ("status", "terminado"),
        ("mode", "automatico"),
        ("mode", "Manual"),
        ("difficulty", "imposible"),
        ("difficulty", "medio"),
        ("figure", "cruz"),
        ("figure", "esquinas"),
        ("figure", "Fila"),
    ],
)
def test_valor_invalido_en_game_es_rechazado(db_session, campo, valor):
    host = crear_usuario(db_session, role="profesor")
    datos = {"figure": "fila", "difficulty": "normal", "mode": "manual", "status": "espera"}
    datos[campo] = valor
    esperar_integrity_error(db_session, Game(code="INV", host=host, seed=1, **datos))


@pytest.mark.parametrize("campo", ["status", "mode", "difficulty"])
def test_game_acepta_todos_los_valores_validos(db_session, campo):
    validos = {
        "status": ("espera", "en_juego", "terminada"),
        "mode": ("manual", "auto"),
        "difficulty": ("facil", "normal", "dificil"),
    }[campo]
    host = crear_usuario(db_session, role="profesor")
    for i, valor in enumerate(validos):
        crear_partida(db_session, host=host, code=f"{campo[:3]}{i}", **{campo: valor})


def test_figura_invalida_en_winner_es_rechazada(db_session):
    partida = crear_partida(db_session)
    jugador = crear_usuario(db_session)
    tablero = crear_tablero(db_session, partida, jugador)
    esperar_integrity_error(
        db_session, Winner(game=partida, user=jugador, board=tablero, figure="cruz")
    )


@pytest.mark.parametrize("figura", FIGURAS)
def test_winner_acepta_cada_figura_valida(db_session, figura):
    partida = crear_partida(db_session)
    jugador = crear_usuario(db_session)
    tablero = crear_tablero(db_session, partida, jugador)
    db_session.add(Winner(game=partida, user=jugador, board=tablero, figure=figura))
    db_session.flush()


@pytest.mark.parametrize("numero", [0, 55, -1])
def test_card_fuera_de_rango_es_rechazada(db_session, numero):
    esperar_integrity_error(db_session, Card(id=numero, name=f"Fuera {numero}"))


@pytest.mark.parametrize("posicion", [-1, 16])
def test_board_card_posicion_fuera_de_rango_es_rechazada(db_session, cartas, posicion):
    tablero = crear_tablero(db_session, crear_partida(db_session), crear_usuario(db_session))
    esperar_integrity_error(
        db_session, BoardCard(board=tablero, card_id=1, position=posicion)
    )


# ---------- relaciones ----------


def test_tablero_trae_sus_16_casillas_en_orden(db_session, cartas):
    tablero = crear_tablero(
        db_session, crear_partida(db_session), crear_usuario(db_session), seed=2024
    )
    ids = generar_tablero(tablero.seed)
    # Se insertan al revés para comprobar que la relación ordena por posición.
    for posicion in reversed(range(16)):
        db_session.add(BoardCard(board_id=tablero.id, card_id=ids[posicion], position=posicion))
    db_session.commit()
    db_session.expire_all()

    casillas = db_session.get(Board, tablero.id).cards
    assert len(casillas) == 16
    assert [c.position for c in casillas] == list(range(16))
    assert [c.card_id for c in casillas] == ids
    assert all(c.marked is False for c in casillas)


def test_partida_trae_sus_cartas_cantadas_en_orden(db_session, cartas):
    partida = crear_partida(db_session, seed=31)
    mazo = barajar_mazo(partida.seed)[:5]
    # Se insertan en desorden para comprobar que la relación ordena por `order`.
    for orden in (3, 1, 5, 2, 4):
        db_session.add(CalledCard(game_id=partida.id, card_id=mazo[orden - 1], order=orden))
    db_session.commit()
    db_session.expire_all()

    cantadas = db_session.get(Game, partida.id).called_cards
    assert [c.order for c in cantadas] == [1, 2, 3, 4, 5]
    assert [c.card_id for c in cantadas] == mazo


def test_borrar_partida_borra_tableros_casillas_cantadas_y_ganadores(db_session, cartas):
    partida = crear_partida(db_session)
    jugador = crear_usuario(db_session)
    tablero = crear_tablero(db_session, partida, jugador)
    db_session.add_all(
        [
            BoardCard(board=tablero, card_id=1, position=0),
            CalledCard(game=partida, card_id=1, order=1),
            Winner(game=partida, user=jugador, board=tablero, figure="fila"),
        ]
    )
    db_session.flush()

    db_session.delete(partida)
    db_session.flush()
    for modelo in (Board, BoardCard, CalledCard, Winner):
        assert db_session.query(modelo).count() == 0
    assert db_session.get(User, jugador.id) is not None
    assert db_session.get(Card, 1) is not None


# ---------- comando seed-cards ----------


def test_seed_cards_carga_54_cartas_con_id_igual_al_numero(app, db_session):
    resultado = app.test_cli_runner().invoke(args=["seed-cards"])
    assert resultado.exit_code == 0, resultado.output

    cartas = db_session.query(Card).order_by(Card.id).all()
    assert [c.id for c in cartas] == list(range(1, 55))
    assert cartas[0].name == "El Gallo"
    assert cartas[53].name == "La Rana"
    assert len({c.name for c in cartas}) == 54


def test_seed_cards_dos_veces_no_duplica(app, db_session):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed-cards"]).exit_code == 0
    segunda = runner.invoke(args=["seed-cards"])

    assert segunda.exit_code == 0, segunda.output
    assert "0 nuevas" in segunda.output
    assert db_session.query(Card).count() == 54


def test_seed_cards_corrige_nombres_cambiados(app, db_session):
    runner = app.test_cli_runner()
    runner.invoke(args=["seed-cards"])
    db_session.get(Card, 1).name = "Nombre incorrecto"
    db_session.commit()

    resultado = runner.invoke(args=["seed-cards"])
    assert "1 actualizadas" in resultado.output
    db_session.expire_all()
    assert db_session.get(Card, 1).name == "El Gallo"
    assert db_session.query(Card).count() == 54
