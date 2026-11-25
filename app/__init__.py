from flask import Flask

from app.db import db
from config import Config


def create_app(config_class=Config):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    # Importar los modelos los registra en db.metadata para db.create_all().
    from app import models  # noqa: F401
    from app.cli import register_cli

    register_cli(app)

    from app.routes.health import bp as health_bp
    from app.routes.main import bp as main_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(main_bp)

    return app
