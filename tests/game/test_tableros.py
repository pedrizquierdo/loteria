"""Pruebas de generación sin fixtures de Flask ni conexión a una base."""

import random

import pytest

from app.game import DIFICULTADES, barajar_mazo, generar_tablero
from app.game.constantes import CARTAS, LADO_TABLERO, TAMANO_TABLERO


def test_constantes():
    assert CARTAS == tuple(range(1, 55))
    assert LADO_TABLERO == 4
    assert TAMANO_TABLERO == 16
    assert DIFICULTADES == {"facil": 9, "normal": 5, "dificil": 3}


@pytest.mark.parametrize("semilla", range(100))
def test_mazo_y_tablero_sin_repeticiones(semilla):
    mazo = barajar_mazo(semilla)
    tablero = generar_tablero(semilla)
    assert isinstance(mazo, list)
    assert len(mazo) == 54
    assert set(mazo) == set(range(1, 55))
    assert isinstance(tablero, list)
    assert len(tablero) == len(set(tablero)) == 16
    assert set(tablero) <= set(range(1, 55))


@pytest.mark.parametrize("generar", [barajar_mazo, generar_tablero])
def test_resultado_reproducible_e_independiente(generar):
    esperado = generar(42)
    resultado = generar(42)
    assert resultado == esperado
    resultado.pop()
    assert generar(42) == esperado


@pytest.mark.parametrize("generar", [barajar_mazo, generar_tablero])
def test_semillas_distintas_cambian_el_resultado(generar):
    assert generar(1) != generar(2)


@pytest.mark.parametrize("generar", [barajar_mazo, generar_tablero])
def test_no_modifica_el_azar_global_ni_las_cartas(generar):
    estado = random.getstate()
    generar(42)
    assert random.getstate() == estado
    assert CARTAS == tuple(range(1, 55))


@pytest.mark.parametrize("generar", [barajar_mazo, generar_tablero])
@pytest.mark.parametrize("semilla", [None, True, 1.5, "42", [], {}])
def test_rechaza_semillas_no_enteras(generar, semilla):
    with pytest.raises(ValueError, match="entero"):
        generar(semilla)
