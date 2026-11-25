"""Comandos de consola: `flask init-db` y `flask seed-cards`."""

import click
from sqlalchemy import inspect

from app.db import db
from app.models import Card

# Las 54 cartas tradicionales de la lotería mexicana; el índice + 1 es su número.
CARTAS_TRADICIONALES = (
    "El Gallo", "El Diablito", "La Dama", "El Catrín", "El Paraguas",
    "La Sirena", "La Escalera", "La Botella", "El Barril", "El Árbol",
    "El Melón", "El Valiente", "El Gorrito", "La Muerte", "La Pera",
    "La Bandera", "El Bandolón", "El Violoncello", "La Garza", "El Pájaro",
    "La Mano", "La Bota", "La Luna", "El Cotorro", "El Borracho",
    "El Negrito", "El Corazón", "La Sandía", "El Tambor", "El Camarón",
    "Las Jaras", "El Músico", "La Araña", "El Soldado", "La Estrella",
    "El Cazo", "El Mundo", "El Apache", "El Nopal", "El Alacrán",
    "La Rosa", "La Calavera", "La Campana", "El Cantarito", "El Venado",
    "El Sol", "La Corona", "La Chalupa", "El Pino", "El Pescado",
    "La Palma", "La Maceta", "El Arpa", "La Rana",
)


def _tablas_existentes():
    return set(inspect(db.engine).get_table_names())


def crear_tablas():
    """Crea las tablas que falten (no borra datos). Devuelve las recién creadas."""
    antes = _tablas_existentes()
    db.create_all()
    return sorted(set(db.metadata.tables) - antes)


@click.command("init-db")
def init_db():
    """Crea las tablas de la base de datos (idempotente)."""
    creadas = crear_tablas()
    if creadas:
        click.echo(f"Tablas creadas ({len(creadas)}): {', '.join(creadas)}")
    else:
        click.echo("Todas las tablas ya existían; no se creó ninguna.")


@click.command("seed-cards")
def seed_cards():
    """Carga las 54 cartas (idempotente). Crea las tablas si faltan."""
    if not set(db.metadata.tables) <= _tablas_existentes():
        creadas = crear_tablas()
        click.echo(
            f"Aviso: faltaban tablas y se crearon ({', '.join(creadas)}). "
            "Usa `flask --app run init-db` para crearlas."
        )
    nuevas = actualizadas = 0
    for numero, nombre in enumerate(CARTAS_TRADICIONALES, start=1):
        carta = db.session.get(Card, numero)
        if carta is None:
            db.session.add(Card(id=numero, name=nombre))
            nuevas += 1
        elif carta.name != nombre:
            carta.name = nombre
            actualizadas += 1
    db.session.commit()
    click.echo(
        f"Cartas: {nuevas} nuevas, {actualizadas} actualizadas, "
        f"{db.session.query(Card).count()} en total."
    )


def register_cli(app):
    app.cli.add_command(init_db)
    app.cli.add_command(seed_cards)
