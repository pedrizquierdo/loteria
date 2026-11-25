"""Reglas de victoria usando posiciones conocidas y cartas desordenadas."""

from copy import deepcopy

import pytest

from app.game import validar_victoria
from app.game.figuras import validar_marcas


TABLERO = [54, 3, 22, 7, 41, 12, 9, 33, 18, 50, 2, 28, 16, 39, 25, 44]
PATRONES = [
    ("fila", [0, 1, 2, 3]),
    ("fila", [4, 5, 6, 7]),
    ("fila", [8, 9, 10, 11]),
    ("fila", [12, 13, 14, 15]),
    ("columna", [0, 4, 8, 12]),
    ("columna", [1, 5, 9, 13]),
    ("columna", [2, 6, 10, 14]),
    ("columna", [3, 7, 11, 15]),
    ("diagonal", [0, 5, 10, 15]),
    ("diagonal", [3, 6, 9, 12]),
    ("cuatro_esquinas", [0, 3, 12, 15]),
    ("tablero_lleno", list(range(16))),
]


@pytest.mark.parametrize("figura,posiciones", PATRONES)
def test_figura_completa_gana(figura, posiciones):
    marcas = [TABLERO[i] for i in posiciones]
    assert validar_victoria(TABLERO, marcas, marcas, figura) is True


@pytest.mark.parametrize("figura,posiciones", PATRONES)
def test_cada_carta_de_la_figura_es_necesaria(figura, posiciones):
    marcas = [TABLERO[i] for i in posiciones]
    for carta in marcas:
        incompletas = [marca for marca in marcas if marca != carta]
        assert validar_victoria(TABLERO, incompletas, marcas, figura) is False
        assert validar_victoria(TABLERO, marcas, incompletas, figura) is False


@pytest.mark.parametrize("figura,posiciones", PATRONES[:-1])
def test_marca_extra_debe_haber_sido_cantada(figura, posiciones):
    marcas = [TABLERO[i] for i in posiciones]
    extra = next(carta for carta in TABLERO if carta not in marcas)
    assert validar_victoria(TABLERO, marcas + [extra], marcas, figura) is False
    assert validar_victoria(TABLERO, marcas + [extra], marcas + [extra], figura) is True


@pytest.mark.parametrize("figura", ["fila", "columna", "diagonal", "cuatro_esquinas", "tablero_lleno"])
def test_sin_marcas_no_hay_victoria(figura):
    assert validar_victoria(TABLERO, [], TABLERO, figura) is False


@pytest.mark.parametrize("figura", ["columna", "diagonal", "cuatro_esquinas", "tablero_lleno"])
def test_una_fila_no_sustituye_otra_figura(figura):
    assert validar_victoria(TABLERO, TABLERO[:4], TABLERO, figura) is False


@pytest.mark.parametrize("figura", ["desconocida", "", "Fila", None, [], {}, 1])
def test_figura_invalida(figura):
    assert validar_victoria(TABLERO, TABLERO, TABLERO, figura) is False


@pytest.mark.parametrize("tablero", [
    None, [], TABLERO[:-1], TABLERO + [1], [1] * 16, set(TABLERO),
    [0] + TABLERO[1:], [55] + TABLERO[1:], [True] + TABLERO[1:],
    [54.0] + TABLERO[1:], ["54"] + TABLERO[1:], [[54]] + TABLERO[1:],
])
def test_tablero_invalido(tablero):
    assert validar_victoria(tablero, TABLERO, TABLERO, "fila") is False


@pytest.mark.parametrize("valor", [None, "54", 54, {}, [[54]], [True], [3.0], [0], [55]])
def test_marcas_y_cantadas_invalidas(valor):
    assert validar_victoria(TABLERO, valor, TABLERO, "fila") is False
    assert validar_victoria(TABLERO, TABLERO, valor, "fila") is False


def test_marca_ajena_al_tablero_invalida_la_victoria():
    assert validar_victoria(TABLERO, TABLERO[:4] + [1], TABLERO + [1], "fila") is False


def test_cantadas_pueden_incluir_cartas_ajenas_al_tablero():
    assert validar_victoria(TABLERO, TABLERO[:4], list(range(1, 55)), "fila") is True


def test_marcas_y_cantadas_repetidas_no_cambian_el_resultado():
    assert validar_victoria(TABLERO, TABLERO[:4] * 2, TABLERO * 2, "fila") is True
    assert validar_victoria(TABLERO, [54] * 16, TABLERO, "tablero_lleno") is False


def test_admite_tuplas_y_conjuntos_de_ids():
    assert validar_victoria(tuple(TABLERO), set(TABLERO[:4]), frozenset(TABLERO), "fila") is True


def test_no_modifica_las_entradas():
    entradas = [TABLERO.copy(), TABLERO[:4], TABLERO.copy()]
    originales = deepcopy(entradas)
    assert validar_victoria(*entradas, "fila") is True
    assert entradas == originales


def test_marcas_validas_no_implican_victoria():
    assert validar_marcas(TABLERO, [], []) is True
    assert validar_victoria(TABLERO, [], [], "fila") is False


def test_comprueba_marcas_antes_de_evaluar_la_figura():
    class FiguraNoEvaluable(str):
        def __hash__(self):
            raise AssertionError("La figura se evaluó antes de rechazar las marcas")

    assert validar_victoria(TABLERO, TABLERO[:4], [], FiguraNoEvaluable("fila")) is False
