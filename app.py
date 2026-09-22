from __future__ import annotations

import csv
import hmac
import io
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from flask import Flask, Response, jsonify, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(BASE_DIR / "instance" / "audioclaro.db")))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024

_schema_ready = False
_schema_lock = threading.Lock()

FIELDS = (
    "participant_code",
    "activity",
    "audios_per_day",
    "recent_episode",
    "impact",
    "preference",
    "feedback",
    "second_action",
    "confidence",
    "concern",
    "notes",
)

REQUIRED_FIELDS = FIELDS[:-1]
ALLOWED_AUDIO_RANGES = {"0 a 2", "3 a 5", "6 a 10", "Mais de 10"}
ALLOWED_THREE_WAY = {"sim", "nao", "depende"}
ALLOWED_TWO_WAY = {"sim", "nao"}


def _postgres_url() -> str:
    if DATABASE_URL.startswith("postgres://"):
        return "postgresql://" + DATABASE_URL.removeprefix("postgres://")
    return DATABASE_URL


@contextmanager
def database() -> Iterator[Any]:
    if IS_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(_postgres_url(), row_factory=dict_row)
    else:
        SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(SQLITE_PATH)
        connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def sql(query: str) -> str:
    return query.replace("?", "%s") if IS_POSTGRES else query


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with database() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS validations (
                    id TEXT PRIMARY KEY,
                    participant_code TEXT NOT NULL,
                    activity TEXT NOT NULL,
                    audios_per_day TEXT NOT NULL,
                    recent_episode TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    preference TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    second_action TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    concern TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    consent INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS validations_created_at_idx ON validations (created_at)"
            )
        _schema_ready = True


def clean_text(value: Any, maximum: int = 900) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:maximum]


def validate_payload(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "Envie os dados em formato JSON."

    if clean_text(payload.get("website")):
        return {"honeypot": True}, None

    data = {field: clean_text(payload.get(field)) for field in FIELDS}
    data["participant_code"] = data["participant_code"][:12]
    data["activity"] = data["activity"][:80]

    missing = [field for field in REQUIRED_FIELDS if not data[field]]
    if missing:
        return None, "Preencha todos os campos obrigatórios."

    if data["audios_per_day"] not in ALLOWED_AUDIO_RANGES:
        return None, "Selecione uma faixa válida de áudios por dia."
    if data["preference"] not in ALLOWED_THREE_WAY:
        return None, "Selecione uma preferência válida."
    if data["second_action"] not in ALLOWED_TWO_WAY:
        return None, "Selecione uma opção válida para a segunda ação."
    if data["confidence"] not in ALLOWED_THREE_WAY:
        return None, "Selecione uma opção válida de confiança."
    if payload.get("consent") is not True:
        return None, "Confirme o consentimento e a ausência de dados sensíveis."

    data["consent"] = 1
    return data, None


def admin_token() -> str | None:
    configured = os.getenv("ADMIN_TOKEN", "").strip()
    if configured:
        return configured
    if not os.getenv("VERCEL"):
        return "dev-audioclaro"
    return None


def require_admin() -> Response | None:
    expected = admin_token()
    supplied = request.headers.get("X-Admin-Token", "")
    if expected is None:
        return jsonify(error="ADMIN_TOKEN não configurado no ambiente."), 503
    if not hmac.compare_digest(supplied, expected):
        return jsonify(error="Senha administrativa inválida."), 401
    return None


def serialize_row(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in ("id", *FIELDS, "consent", "created_at")}


@app.after_request
def secure_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index() -> Response:
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/<path:asset>")
def public_asset(asset: str) -> Response:
    return send_from_directory(PUBLIC_DIR, asset)


@app.get("/api/health")
def health() -> Response:
    ensure_schema()
    return jsonify(status="ok", storage="postgres" if IS_POSTGRES else "sqlite")


@app.post("/api/responses")
def create_response() -> Response:
    payload, error = validate_payload(request.get_json(silent=True))
    if error:
        return jsonify(error=error), 400
    if payload and payload.get("honeypot"):
        return jsonify(status="saved"), 201

    ensure_schema()
    record_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    values = [record_id, *(payload[field] for field in FIELDS), payload["consent"], created_at]
    placeholders = ", ".join("?" for _ in values)
    columns = ", ".join(("id", *FIELDS, "consent", "created_at"))

    with database() as connection:
        connection.execute(
            sql(f"INSERT INTO validations ({columns}) VALUES ({placeholders})"),
            values,
        )
    return jsonify(id=record_id, status="saved"), 201


@app.get("/api/stats")
def public_stats() -> Response:
    ensure_schema()
    with database() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN recent_episode <> '' THEN 1 ELSE 0 END), 0) AS problem_count,
                COALESCE(SUM(CASE WHEN preference = 'sim' THEN 1 ELSE 0 END), 0) AS preference_count,
                COALESCE(SUM(CASE WHEN second_action = 'sim' THEN 1 ELSE 0 END), 0) AS action_count,
                COALESCE(SUM(CASE WHEN confidence = 'sim' THEN 1 ELSE 0 END), 0) AS confidence_count
            FROM validations
            """
        ).fetchone()
    total = int(row["total"])
    percent = lambda count: round((int(count) / total) * 100) if total else 0
    return jsonify(
        total=total,
        problem_percent=percent(row["problem_count"]),
        preference_percent=percent(row["preference_count"]),
        action_percent=percent(row["action_count"]),
        confidence_percent=percent(row["confidence_count"]),
    )


@app.get("/api/responses")
def list_responses() -> Response:
    denied = require_admin()
    if denied:
        return denied
    ensure_schema()
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM validations ORDER BY created_at DESC"
        ).fetchall()
    return jsonify(items=[serialize_row(row) for row in rows], total=len(rows))


@app.delete("/api/responses/<record_id>")
def delete_response(record_id: str) -> Response:
    denied = require_admin()
    if denied:
        return denied
    try:
        uuid.UUID(record_id)
    except ValueError:
        return jsonify(error="Identificador inválido."), 400
    ensure_schema()
    with database() as connection:
        cursor = connection.execute(
            sql("DELETE FROM validations WHERE id = ?"), (record_id,)
        )
        deleted = cursor.rowcount
    if not deleted:
        return jsonify(error="Resposta não encontrada."), 404
    return jsonify(status="deleted")


@app.get("/api/export.csv")
def export_csv() -> Response:
    denied = require_admin()
    if denied:
        return denied
    ensure_schema()
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM validations ORDER BY created_at ASC"
        ).fetchall()

    fieldnames = ["id", *FIELDS, "consent", "created_at"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(serialize_row(row))

    filename = f"audioclaro-validacoes-{datetime.now(timezone.utc).date().isoformat()}.csv"
    return Response(
        "\ufeff" + stream.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.errorhandler(413)
def payload_too_large(_: Exception) -> tuple[Response, int]:
    return jsonify(error="Os dados enviados ultrapassam o limite permitido."), 413


@app.errorhandler(500)
def internal_error(_: Exception) -> tuple[Response, int]:
    app.logger.exception("Erro interno no AudioClaro")
    return jsonify(error="Não foi possível concluir a operação agora."), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)

