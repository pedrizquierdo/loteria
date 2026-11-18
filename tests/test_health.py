def test_health_responde_200(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_health_devuelve_json_con_estado_ok(client):
    response = client.get("/health")

    assert response.is_json
    assert response.get_json()["status"] == "ok"


def test_health_confirma_conexion_a_la_base(client):
    response = client.get("/health")

    assert response.get_json()["database"] == "ok"


def test_health_reporta_fallo_si_la_base_no_responde(client_sin_db):
    """Comprueba que /health de verdad consulta la base y no responde 'ok' siempre."""
    response = client_sin_db.get("/health")
    data = response.get_json()

    assert response.status_code == 503
    assert data["status"] == "degraded"
    assert data["database"].startswith("error")
