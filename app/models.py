"""Modelos de base de datos (solo datos; la lógica del juego vive en app/game/)."""

from datetime import datetime, timezone

from app.db import db
from app.game.constantes import CARTAS, DIFICULTADES, TAMANO_TABLERO

ROLES = ("profesor", "jugador")
FIGURAS = ("fila", "columna", "diagonal", "cuatro_esquinas", "tablero_lleno")
DIFICULTADES_VALIDAS = tuple(DIFICULTADES)
MODOS = ("manual", "auto")
ESTADOS = ("espera", "en_juego", "terminada")


def _ahora():
    return datetime.now(timezone.utc)


def _en(columna, valores):
    """Texto SQL para un CheckConstraint del tipo `columna IN (...)`."""
    lista = ", ".join(f"'{v}'" for v in valores)
    return f"{columna} IN ({lista})"


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (db.CheckConstraint(_en("role", ROLES), name="ck_users_role"),)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="jugador")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_ahora)

    hosted_games = db.relationship("Game", back_populates="host")
    boards = db.relationship("Board", back_populates="user")
    wins = db.relationship("Winner", back_populates="user")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Card(db.Model):
    __tablename__ = "cards"
    __table_args__ = (
        db.CheckConstraint(
            f"id BETWEEN {CARTAS[0]} AND {CARTAS[-1]}", name="ck_cards_id_rango"
        ),
    )

    # El id es el número de la carta (1 a 54); no es autoincremental.
    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    name = db.Column(db.String(80), unique=True, nullable=False)
    image = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Card {self.id} {self.name}>"


class Game(db.Model):
    __tablename__ = "games"
    __table_args__ = (
        db.CheckConstraint(_en("figure", FIGURAS), name="ck_games_figure"),
        db.CheckConstraint(
            _en("difficulty", DIFICULTADES_VALIDAS), name="ck_games_difficulty"
        ),
        db.CheckConstraint(_en("mode", MODOS), name="ck_games_mode"),
        db.CheckConstraint(_en("status", ESTADOS), name="ck_games_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(12), unique=True, nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    figure = db.Column(db.String(20), nullable=False)
    difficulty = db.Column(db.String(10), nullable=False, default="normal")
    mode = db.Column(db.String(10), nullable=False, default="manual")
    status = db.Column(db.String(10), nullable=False, default="espera")
    seed = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_ahora)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_called_at = db.Column(db.DateTime(timezone=True), nullable=True)

    host = db.relationship("User", back_populates="hosted_games")
    boards = db.relationship(
        "Board", back_populates="game", cascade="all, delete-orphan"
    )
    called_cards = db.relationship(
        "CalledCard",
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="CalledCard.order",
    )
    winners = db.relationship(
        "Winner", back_populates="game", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Game {self.code} {self.status}>"


class Board(db.Model):
    __tablename__ = "boards"
    __table_args__ = (
        db.UniqueConstraint("game_id", "user_id", name="uq_boards_game_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    seed = db.Column(db.BigInteger, nullable=False)

    game = db.relationship("Game", back_populates="boards")
    user = db.relationship("User", back_populates="boards")
    cards = db.relationship(
        "BoardCard",
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="BoardCard.position",
    )
    wins = db.relationship("Winner", back_populates="board")

    def __repr__(self):
        return f"<Board game={self.game_id} user={self.user_id}>"


class BoardCard(db.Model):
    __tablename__ = "board_cards"
    __table_args__ = (
        db.UniqueConstraint("board_id", "position", name="uq_board_cards_position"),
        db.UniqueConstraint("board_id", "card_id", name="uq_board_cards_card"),
        db.CheckConstraint(
            f"position BETWEEN 0 AND {TAMANO_TABLERO - 1}",
            name="ck_board_cards_position",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.Integer, db.ForeignKey("boards.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("cards.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    marked = db.Column(db.Boolean, nullable=False, default=False)

    board = db.relationship("Board", back_populates="cards")
    card = db.relationship("Card")

    def __repr__(self):
        return f"<BoardCard board={self.board_id} pos={self.position} card={self.card_id}>"


class CalledCard(db.Model):
    __tablename__ = "called_cards"
    __table_args__ = (
        db.UniqueConstraint("game_id", "card_id", name="uq_called_cards_game_card"),
    )

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("cards.id"), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    called_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_ahora)

    game = db.relationship("Game", back_populates="called_cards")
    card = db.relationship("Card")

    def __repr__(self):
        return f"<CalledCard game={self.game_id} #{self.order} card={self.card_id}>"


class Winner(db.Model):
    __tablename__ = "winners"
    __table_args__ = (db.CheckConstraint(_en("figure", FIGURAS), name="ck_winners_figure"),)

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    board_id = db.Column(db.Integer, db.ForeignKey("boards.id"), nullable=False)
    figure = db.Column(db.String(20), nullable=False)
    won_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_ahora)

    game = db.relationship("Game", back_populates="winners")
    user = db.relationship("User", back_populates="wins")
    board = db.relationship("Board", back_populates="wins")

    def __repr__(self):
        return f"<Winner game={self.game_id} user={self.user_id} {self.figure}>"
