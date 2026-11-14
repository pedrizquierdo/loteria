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
def client(app):
    return app.test_client()


@pytest.fixture
def client_sin_db():
    return create_app(UnreachableDBConfig).test_client()
