"""Validación de tableros y marcas mediante IDs enteros del 1 al 54."""

from .constantes import CARTAS, LADO_TABLERO, TAMANO_TABLERO


_FIGURAS = {
    "fila": tuple(
        tuple(fila * LADO_TABLERO + columna for columna in range(LADO_TABLERO))
        for fila in range(LADO_TABLERO)
    ),
    "columna": tuple(
        tuple(fila * LADO_TABLERO + columna for fila in range(LADO_TABLERO))
        for columna in range(LADO_TABLERO)
    ),
    "diagonal": (
        tuple(i * LADO_TABLERO + i for i in range(LADO_TABLERO)),
        tuple(i * LADO_TABLERO + LADO_TABLERO - 1 - i for i in range(LADO_TABLERO)),
    ),
    "cuatro_esquinas": ((0, 3, 12, 15),),
    "tablero_lleno": (tuple(range(TAMANO_TABLERO)),),
}


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


def validar_victoria(
    tablero: list[int], marcadas: list[int], cantadas: list[int], figura: str
) -> bool:
    """Valida todas las marcas antes de comprobar la figura solicitada.

    Figuras: fila, columna, diagonal, cuatro_esquinas y tablero_lleno.
    Basta una fila, columna o diagonal completa. Se permiten marcas extra
    solo si pertenecen al tablero y ya fueron cantadas. Una figura desconocida
    o cualquier entrada inválida devuelve False. No modifica sus argumentos.
    """
    if not validar_marcas(tablero, marcadas, cantadas):
        return False
    if not isinstance(figura, str) or figura not in _FIGURAS:
        return False
    marcas = set(marcadas)
    return any(
        all(tablero[posicion] in marcas for posicion in patron)
        for patron in _FIGURAS[figura]
    )
