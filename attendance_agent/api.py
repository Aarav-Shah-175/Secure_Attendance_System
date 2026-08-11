"""
api.py — Flask HTTP API for Attendance Agent.

Exposed to students on the local hotspot (HTTP, port 5000).
Exposed to Django on localhost/HTTPS for control messages.

Routes:
    GET  /status               → agent health and active sessions
    POST /start-session        → Django pushes session_secret (internal)
    POST /stop-session         → Django signals session end (internal)
    GET  /challenge            → student requests a challenge
    GET  /health               → simple liveness probe
"""
import json
import logging
import time

from flask import Flask, request, jsonify, abort  # type: ignore
from functools import wraps

from attendance_agent.agent import AttendanceAgent
from attendance_agent.config import AgentConfig

logger = logging.getLogger(__name__)


def create_app(agent: AttendanceAgent, config: AgentConfig) -> Flask:
    app = Flask(__name__)
    app.config["AGENT"] = agent
    app.config["AGENT_CONFIG"] = config

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def require_agent_token(f):
        """Require the pre-shared Django API token for internal control endpoints."""
        @wraps(f)
        def decorated(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {config.api_token}"
            if not auth or auth != expected:
                abort(401)
            return f(*args, **kwargs)
        return decorated

    # ------------------------------------------------------------------
    # CORS — allow any LAN origin for student challenge fetch
    # ------------------------------------------------------------------

    @app.after_request
    def add_cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    @app.route("/", methods=["OPTIONS"])
    @app.route("/<path:p>", methods=["OPTIONS"])
    def handle_options(p=""):
        return "", 204

    # ------------------------------------------------------------------
    # Public endpoints (students — no auth required)
    # ------------------------------------------------------------------

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "agent_id": agent.agent_id,
            "public_key_pem": agent.public_key_pem,
        })

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify({
            "status": "ok",
            "agent_id": agent.agent_id,
            "public_key_pem": agent.public_key_pem,
            "active_sessions": agent.list_active_sessions(),
            "timestamp": int(time.time()),
        })

    @app.route("/challenge", methods=["GET"])
    def get_challenge():
        """
        Student GETs a one-time challenge from the Agent.
        Query param: session_id (required)
        """
        session_id = request.args.get("session_id")
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        challenge = agent.generate_challenge(session_id)
        if challenge is None:
            return jsonify({
                "error": "No active session found. Session may have expired or not started."
            }), 404

        return jsonify(challenge)

    # ------------------------------------------------------------------
    # Internal control endpoints (Django → Agent; require API token)
    # ------------------------------------------------------------------

    @app.route("/start-session", methods=["POST"])
    @require_agent_token
    def start_session():
        """
        Django pushes session_secret when professor starts a session.
        Body JSON: { session_id, session_secret_hex, expires_at }
        session_secret_hex: hex-encoded 256-bit secret (plaintext after ECDH decrypt on Django side)
        """
        try:
            body = request.get_json(force=True)
            session_id = body["session_id"]
            session_secret_hex = body["session_secret_hex"]
            expires_at = body.get("expires_at")  # Unix float timestamp

            ok = agent.start_session(session_id, session_secret_hex, expires_at)
            if ok:
                return jsonify({"status": "ok", "session_id": session_id})
            else:
                return jsonify({"error": "Failed to start session in agent"}), 400
        except (KeyError, TypeError) as exc:
            return jsonify({"error": f"Invalid payload: {exc}"}), 400
        except Exception as exc:
            logger.error("start-session error: %s", exc)
            return jsonify({"error": "Internal error"}), 500

    @app.route("/stop-session", methods=["POST"])
    @require_agent_token
    def stop_session():
        """Django signals session has ended."""
        try:
            body = request.get_json(force=True)
            session_id = body["session_id"]
            agent.stop_session(session_id)
            return jsonify({"status": "ok", "session_id": session_id})
        except (KeyError, TypeError) as exc:
            return jsonify({"error": f"Invalid payload: {exc}"}), 400

    return app
