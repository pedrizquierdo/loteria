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

    from app.routes.auth import bp as auth_bp
    from app.routes.game import bp as game_bp
    from app.routes.health import bp as health_bp
    from app.routes.main import bp as main_bp
    from app.routes.panel import bp as panel_bp
    from app.routes.ranking import bp as ranking_bp
    from app.routes.salas import bp as salas_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(salas_bp)
    app.register_blueprint(panel_bp)
    app.register_blueprint(ranking_bp)

    return app
