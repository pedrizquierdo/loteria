def test_index_responde_200(client):
    response = client.get("/")

    assert response.status_code == 200


def test_index_muestra_titulo(client):
    response = client.get("/")

    assert "Lotería Mexicana en línea" in response.get_data(as_text=True)
