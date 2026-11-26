"""Errores de la API que se responden como JSON."""

from flask import jsonify


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def respuesta_de_error(error):
    return jsonify({"error": error.message}), error.status
