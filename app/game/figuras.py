"""Validación de tableros y marcas mediante IDs enteros del 1 al 54."""

from .constantes import CARTAS, TAMANO_TABLERO


def _ids_validos(cartas: object) -> bool:
    return isinstance(cartas, (list, tuple, set, frozenset)) and all(
        type(carta) is int and carta in CARTAS for carta in cartas
    )


def validar_marcas(tablero: list[int], marcadas: list[int], cantadas: list[int]) -> bool:
    """Comprueba el tablero y que cada marca le pertenezca y ya se haya cantado.

    El tablero debe conservar su orden (lista o tupla). Las marcas y las
    cantadas admiten listas, tuplas o conjuntos; sus duplicados son inocuos.
    Entradas inválidas devuelven False en lugar de aceptar una victoria.
    """
    if not isinstance(tablero, (list, tuple)) or not _ids_validos(tablero):
        return False
    if len(tablero) != TAMANO_TABLERO or len(set(tablero)) != TAMANO_TABLERO:
        return False
    if not _ids_validos(marcadas) or not _ids_validos(cantadas):
        return False
    return set(marcadas) <= set(tablero) and set(marcadas) <= set(cantadas)
