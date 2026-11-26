"""Pruebas de registro, inicio/cierre de sesión y autenticación por sesión (app/auth.py y app/routes/auth.py)."""

from urllib.parse import urlparse

import pytest

from app.auth import _SIN_PASSWORD
from app.db import db
from app.models import User

pytestmark = pytest.mark.usefixtures("limpia_bd")


# ---------- API JSON: registro ----------


def test_api_register_crea_jugador_con_hash_e_inicia_sesion(app, client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "  ana_lopez  ", "password": "secreto123"},
    )
    assert resp.status_code == 201
    datos = resp.get_json()
    assert datos["user"]["username"] == "ana_lopez"
    assert datos["user"]["role"] == "jugador"
    assert "password_hash" not in datos["user"]

    with app.app_context():
        usuario = db.session.query(User).filter_by(username="ana_lopez").one()
        assert usuario.password_hash != "secreto123"
        assert not usuario.password_hash.startswith("!")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["authenticated"] is True
    assert me.get_json()["user"]["username"] == "ana_lopez"


def test_api_register_acepta_rol_profesor(app, client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "profe_luis", "password": "secreto123", "role": "profesor"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["user"]["role"] == "profesor"


def test_api_register_rechaza_usuario_duplicado_con_409(client):
    assert (
        client.post(
            "/api/auth/register", json={"username": "ana", "password": "secreto123"}
        ).status_code
        == 201
    )
    dup = client.post(
        "/api/auth/register", json={"username": "ana", "password": "otro_password"}
    )
    assert dup.status_code == 409
    assert "error" in dup.get_json()


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"username": "", "password": "secreto123"},
        {"username": "   ", "password": "secreto123"},
        {"username": "x" * 81, "password": "secreto123"},
        {"username": "ana", "password": ""},
        {"username": "ana", "password": "12345"},
        {"username": "ana", "password": "a" * 129},
        {"username": "ana", "password": "secreto123", "role": "admin"},
        {"username": "ana", "password": "secreto123", "role": "Profesor"},
        [1, 2, 3],
    ],
)
def test_api_register_rechaza_datos_invalidos_con_400(app, client, cuerpo):
    resp = client.post("/api/auth/register", json=cuerpo)
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    with app.app_context():
        assert db.session.query(User).count() == 0


# ---------- API JSON: login, logout y me ----------


def test_api_login_y_logout_ciclo_completo(app):
    cli_reg = app.test_client()
    assert (
        cli_reg.post(
            "/api/auth/register",
            json={"username": "profe_ana", "password": "clave_segura", "role": "profesor"},
        ).status_code
        == 201
    )

    cli = app.test_client()
    assert cli.get("/api/auth/me").status_code == 401

    resp = cli.post(
        "/api/auth/login",
        json={"username": "profe_ana", "password": "clave_segura"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["user"]["username"] == "profe_ana"
    assert cli.get("/api/auth/me").status_code == 200

    assert cli.post("/api/auth/logout").status_code == 200
    assert cli.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "username, password",
    [
        ("no_existe", "clave_segura"),
        ("ana", "clave_equivocada"),
    ],
)
def test_api_login_credenciales_incorrectas_dan_401(app, username, password):
    app.test_client().post(
        "/api/auth/register", json={"username": "ana", "password": "clave_segura"}
    )
    resp = app.test_client().post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 401
    assert "incorrectos" in resp.get_json()["error"].lower()


def test_api_login_rechaza_usuario_con_hash_temporal_inutilizable(app):
    with app.app_context():
        db.session.add(
            User(username="legacy", password_hash=_SIN_PASSWORD, role="jugador")
        )
        db.session.commit()

    resp = app.test_client().post(
        "/api/auth/login", json={"username": "legacy", "password": _SIN_PASSWORD}
    )
    assert resp.status_code == 401


def test_sesion_invalida_si_usuario_fue_borrado(app):
    cli = app.test_client()
    cli.post("/api/auth/register", json={"username": "temporal", "password": "secreto123"})
    with app.app_context():
        db.session.query(User).filter_by(username="temporal").delete()
        db.session.commit()

    assert cli.get("/api/auth/me").status_code == 401


# ---------- Pantallas web (/auth/*) ----------


def test_pantallas_login_y_registro_responden_200(client):
    resp_login = client.get("/auth/login")
    resp_reg = client.get("/auth/registro")

    assert resp_login.status_code == 200
    assert 'name="username"' in resp_login.get_data(as_text=True)
    assert 'name="password"' in resp_login.get_data(as_text=True)

    assert resp_reg.status_code == 200
    assert 'name="confirm_password"' in resp_reg.get_data(as_text=True)
    assert 'name="role"' in resp_reg.get_data(as_text=True)


def test_registro_web_exitoso_y_cuenta_y_logout(app):
    cli = app.test_client()
    resp = cli.post(
        "/auth/registro",
        data={
            "username": "Prof. Luis",
            "password": "password123",
            "confirm_password": "password123",
            "role": "profesor",
        },
    )
    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == "/auth/cuenta"

    cuenta = cli.get("/auth/cuenta")
    html = cuenta.get_data(as_text=True)
    assert cuenta.status_code == 200
    assert "Prof. Luis" in html
    assert "Profesor" in html

    salida = cli.post("/auth/logout")
    assert salida.status_code == 302
    assert urlparse(salida.headers["Location"]).path == "/auth/login"
    assert cli.get("/auth/cuenta").status_code == 302


def test_registro_web_rechaza_contrasenas_distintas(app, client):
    resp = client.post(
        "/auth/registro",
        data={
            "username": "ana",
            "password": "password123",
            "confirm_password": "otra_password",
            "role": "jugador",
        },
    )
    assert resp.status_code == 400
    assert "no coinciden" in resp.get_data(as_text=True).lower()
    with app.app_context():
        assert db.session.query(User).count() == 0


def test_login_web_con_credenciales_invalidas_da_401(client):
    resp = client.post(
        "/auth/login",
        data={"username": "nadie", "password": "password123"},
    )
    assert resp.status_code == 401
    assert 'role="alert"' in resp.get_data(as_text=True)


def test_login_web_respeta_next_interno_y_bloquea_open_redirect(app):
    app.test_client().post(
        "/api/auth/register", json={"username": "ana", "password": "password123"}
    )

    # Ruta interna válida
    cli_ok = app.test_client()
    resp_ok = cli_ok.post(
        "/auth/login",
        data={"username": "ana", "password": "password123", "next": "/salas/crear"},
    )
    assert resp_ok.status_code == 302
    assert urlparse(resp_ok.headers["Location"]).path == "/salas/crear"

    # Redirecciones externas bloqueadas
    for malicioso in ("https://evil.example/phish", "//evil.example", "/\\evil.example"):
        cli_bad = app.test_client()
        resp_bad = cli_bad.post(
            "/auth/login",
            data={"username": "ana", "password": "password123", "next": malicioso},
        )
        assert resp_bad.status_code == 302
        assert urlparse(resp_bad.headers["Location"]).path == "/auth/cuenta"


def test_nombre_con_html_se_escapa_en_vista_cuenta(app):
    cli = app.test_client()
    nombre = "<script>alert(1)</script>"
    resp = cli.post(
        "/auth/registro",
        data={
            "username": nombre,
            "password": "password123",
            "confirm_password": "password123",
            "role": "jugador",
        },
    )
    assert resp.status_code == 302
    html = cli.get("/auth/cuenta").get_data(as_text=True)
    assert nombre not in html
    assert "&lt;script&gt;" in html


# ---------- Integración con /api/games ----------


def test_sesion_real_permite_crear_y_unirse_en_api_games_y_bloquea_header_falso(app):
    profe = app.test_client()
    alumno = app.test_client()
    anon = app.test_client()

    profe.post(
        "/api/auth/register",
        json={"username": "profe1", "password": "password123", "role": "profesor"},
    )
    alumno.post(
        "/api/auth/register",
        json={"username": "alumno1", "password": "password123", "role": "jugador"},
    )

    resp_crear = profe.post("/api/games", json={"figure": "diagonal"})
    assert resp_crear.status_code == 201
    code = resp_crear.get_json()["code"]

    assert alumno.post("/api/games").status_code == 403
    assert alumno.post(f"/api/games/{code}/join").status_code == 201
    assert anon.post("/api/games", headers={"X-User-Id": "profe1"}).status_code == 401
