from flask import Blueprint, jsonify
from sqlalchemy import text

from app.db import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc.__class__.__name__}"

    healthy = db_status == "ok"
    body = {"status": "ok" if healthy else "degraded", "database": db_status}
    return jsonify(body), 200 if healthy else 503
