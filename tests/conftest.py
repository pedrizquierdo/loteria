import os

import pytest

from app import create_app
from config import Config


class TestConfig(Config):
    """Configuración de pruebas.

    Usa TEST_DATABASE_URL si existe; si no, la DATABASE_URL normal
    (la base de Postgres del docker-compose).
    """

    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", os.environ.get("DATABASE_URL")
    )


class UnreachableDBConfig(TestConfig):
    """Apunta a un puerto donde no hay base de datos, para simular una caída."""

    SQLALCHEMY_DATABASE_URI = (
        "postgresql+psycopg2://nadie:nada@127.0.0.1:1/no_existe"
    )


@pytest.fixture
def app():
    if not TestConfig.SQLALCHEMY_DATABASE_URI:
        pytest.fail("Define DATABASE_URL o TEST_DATABASE_URL para correr las pruebas")
    return create_app(TestConfig)


@pytest.fixture
def db_session(app):
    """Sesión de BD aislada: todo lo que haga la prueba se revierte al final.

    Las tablas se crean de verdad (create_all no borra datos), pero cada
    prueba corre dentro de una transacción externa que se deshace en el
    teardown. Los commit() de la prueba (o de comandos como seed-cards)
    solo liberan un SAVEPOINT, así que la base queda igual que antes.
    """
    from sqlalchemy.orm import scoped_session, sessionmaker

    from app.db import db

    with app.app_context():
        db.create_all()
        connection = db.engine.connect()
        transaction = connection.begin()
        original = db.session
        # Sesión de SQLAlchemy "pura": la de Flask-SQLAlchemy ignora `bind`
        # y siempre usa el engine, lo que saltaría la transacción externa.
        db.session = scoped_session(
            sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
        )
        try:
            yield db.session
        finally:
            db.session.remove()
            db.session = original
            transaction.rollback()
            connection.close()


TABLAS_DE_JUEGO = ("users", "games", "boards", "board_cards", "called_cards", "winners")


@pytest.fixture
def limpia_bd(app):
    """Base real para pruebas que pasan por el client (las rutas hacen commit).

    `db_session` no sirve aquí: la sesión de Flask-SQLAlchemy que usan las
    rutas ignora `bind=connection`. En su lugar:
    - antes: crea las tablas y siembra las 54 cartas con `flask seed-cards`;
    - después: vacía las tablas de juego (TRUNCATE ... RESTART IDENTITY
      CASCADE) y deja las cartas.
    Requiere una base separada y desechable (TEST_DATABASE_URL).
    """
    from sqlalchemy import text

    from app.db import db

    # `seed-cards` no lleva @with_appcontext (el CLI `flask` empuja el
    # contexto por su cuenta), así que el runner de pruebas necesita uno.
    with app.app_context():
        db.create_all()
        resultado = app.test_cli_runner().invoke(args=["seed-cards"])
        assert resultado.exit_code == 0, resultado.output

    yield

    with app.app_context():
        db.session.remove()
        db.session.execute(
            text(f"TRUNCATE {', '.join(TABLAS_DE_JUEGO)} RESTART IDENTITY CASCADE")
        )
        db.session.commit()
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def client_sin_db():
    return create_app(UnreachableDBConfig).test_client()
