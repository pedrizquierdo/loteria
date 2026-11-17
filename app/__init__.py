from flask import Flask

from app.db import db
from config import Config


def create_app(config_class=Config):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from app.routes.health import bp as health_bp
    from app.routes.main import bp as main_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(main_bp)

    return app
