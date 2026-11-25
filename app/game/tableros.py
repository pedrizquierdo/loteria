"""Generación reproducible sin modificar datos ni el azar global."""

from random import Random

from .constantes import CARTAS, TAMANO_TABLERO


def _generador(semilla: int) -> Random:
    if type(semilla) is not int:
        raise ValueError("La semilla debe ser un entero.")
    return Random(semilla)


def barajar_mazo(semilla: int) -> list[int]:
    """Devuelve las 54 cartas barajadas; la misma semilla repite el resultado."""
    mazo = list(CARTAS)
    _generador(semilla).shuffle(mazo)
    return mazo


def generar_tablero(semilla: int) -> list[int]:
    """Devuelve 16 IDs distintos, ordenados por filas de izquierda a derecha.

    El backend proporciona la semilla. Jugadores distintos pueden compartir
    cartas; solo se impiden repeticiones dentro de cada tablero.
    """
    return _generador(semilla).sample(CARTAS, TAMANO_TABLERO)
