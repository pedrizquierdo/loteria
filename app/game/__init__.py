"""Reglas del juego con IDs de cartas, sin acceso a servicios externos."""

from .constantes import DIFICULTADES
from .tableros import barajar_mazo, generar_tablero

__all__ = ["DIFICULTADES", "barajar_mazo", "generar_tablero"]
