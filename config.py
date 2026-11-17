import os


class Config:
    """Configuración leída desde variables de entorno."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insegura-cambiar")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
