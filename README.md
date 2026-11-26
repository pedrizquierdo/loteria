# Lotería Mexicana en línea

Proyecto final de la materia de DevOps. El profesor "canta" las cartas desde un panel y los alumnos juegan desde el celular en tiempo real.

> Estado actual: ya existen la lógica del juego (`app/game/`) y los modelos de base de datos (`app/models.py`).

## Stack

- **Backend:** Python 3.12 + Flask (application factory)
- **Base de datos:** PostgreSQL 16 (en contenedor) vía Flask-SQLAlchemy
- **Contenedores:** Docker y Docker Compose
- **Entorno de desarrollo:** Dev Container de VS Code
- **Pruebas:** pytest

La misma imagen de Docker (`Dockerfile`) se usa en desarrollo y en el despliegue.

## Cómo levantarlo

### 1. Clonar y configurar variables

```bash
git clone <url-del-repo>
cd loteria
cp .env.example .env   # edita los valores; .env nunca se sube al repo
```

### 2a. Con Dev Container (recomendado)

1. Instala Docker Desktop, VS Code y la extensión **Dev Containers**.
2. Abre la carpeta en VS Code.
3. `Ctrl/Cmd + Shift + P` → **Dev Containers: Reopen in Container**.

VS Code levanta `app` y `db`, se conecta al contenedor `app` e instala las extensiones de Python y Docker. La app queda en <http://localhost:5000>.

### 2b. Con Docker Compose

```bash
docker compose up --build
```

- App: <http://localhost:5000>
- Healthcheck: <http://localhost:5000/health>

Para detener: `docker compose down` (agrega `-v` para borrar también los datos de la base).

> **macOS:** el puerto 5000 lo ocupa *AirPlay Receiver*. Pon `APP_PORT=5001` en tu `.env` y entra a <http://localhost:5001> (o desactiva AirPlay Receiver en Ajustes del Sistema).

## Base de datos

Con la base levantada, crea las tablas y carga las 54 cartas (ambos comandos son idempotentes):

```bash
flask --app run init-db      # crea las tablas que falten, sin borrar datos
flask --app run seed-cards   # carga las 54 cartas (id = número de carta)
```

Dentro del contenedor:

```bash
docker compose exec app flask --app run init-db
docker compose exec app flask --app run seed-cards
```

Tablas:

- `users`: usuarios (`profesor` o `jugador`).
- `cards`: las 54 cartas; el id es el número de la carta.
- `games`: partidas (código, figura, dificultad, modo, estado y semilla del mazo).
- `boards`: tablero de cada jugador en una partida, con su semilla.
- `board_cards`: las 16 cartas de cada tablero, su posición y si están marcadas.
- `called_cards`: cartas cantadas en cada partida, en orden.
- `winners`: ganadores de cada partida y la figura con que ganaron.

## Salas y acceso rápido desde el celular

- Las pantallas de `/salas/` permiten crear salas con código de 6 caracteres (`/salas/crear`) y unirse desde el celular (`/salas/unirse`).
- **Limitación conocida (acceso rápido en salón):** si un alumno se une con un apodo nuevo (sin cuenta registrada en `/auth/registro`), entra directo con solo escribir su nombre para agilizar la dinámica en clase; si otro alumno escribe ese mismo apodo sin contraseña, podrá recuperar ese tablero. En cambio, si el nombre pertenece a una cuenta registrada con contraseña real (`/auth/registro`), `/salas/crear` y `/salas/unirse` exigen haber iniciado sesión previamente (`/auth/login`) para evitar suplantación.

## Estructura de carpetas

```
loteria/
├── .devcontainer/
│   └── devcontainer.json   # Configuración del Dev Container
├── app/
│   ├── __init__.py         # create_app() (application factory)
│   ├── db.py               # Instancia de Flask-SQLAlchemy
│   ├── game/               # Lógica del juego (reservado)
│   ├── routes/
│   │   ├── health.py       # GET /health (estado de la app y la BD)
│   │   └── main.py         # GET /
│   └── templates/
│       └── index.html
├── config.py               # Configuración desde variables de entorno
├── run.py                  # Punto de entrada
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Flujo de trabajo con ramas

- **Nunca** se hace commit ni push directo a la rama principal.
- Cada cambio va en su propia rama:
  - `feature-descripcion` para funcionalidades (ej. `feature-panel-profe`)
  - `test-descripcion` para pruebas (ej. `test-health`)
- Al terminar, abre un **Pull Request** hacia la rama principal.
- Solo se hace merge cuando el PR está **aprobado** por al menos un compañero.

```bash
git checkout main && git pull
git checkout -b feature-mi-cambio
# ...trabajo, commits...
git push -u origin feature-mi-cambio
# abrir Pull Request en GitHub
```

## Módulos y responsables

| Módulo | Responsable |
|---|---|
| Lógica del juego | Emiliano Rascón |
| Backend y base de datos | Pedro Izquierdo |
| Salas, panel del profe, login y ranking | Luis Morell |
| Frontend | Barush Camargo |
| DevOps 1 (Docker, Dev Container, Actions de pruebas) | Alexis Mendoza |
| DevOps 2 (deploy en la nube y rollback) | Julián Rodríguez |
