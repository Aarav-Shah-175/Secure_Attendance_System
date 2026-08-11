"""
__main__.py — Entry point for the Attendance Agent.

Run with:
    python -m attendance_agent
    python -m attendance_agent --config /path/to/attendance_agent.toml
"""
import argparse
import logging
import sys

from attendance_agent.config import load_config
from attendance_agent.agent import AttendanceAgent
from attendance_agent.api import create_app
from attendance_agent.heartbeat import HeartbeatSender


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="attendance_agent",
        description="Secure Attendance — Network Verification Agent",
    )
    parser.add_argument("--config", metavar="PATH", help="Path to attendance_agent.toml")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-register", action="store_true", help="Skip Django registration on startup")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("attendance_agent")

    # Load configuration
    config = load_config(args.config)
    logger.info("Loaded config: Agent will listen on %s:%d", config.host, config.port)
    logger.info("Django URL: %s", config.django_url)
    logger.info("Hotspot IP: %s", config.hotspot_ip)

    if not config.api_token:
        logger.critical(
            "ATTENDANCE_AGENT_API_TOKEN is not set. Set it in attendance_agent.toml or env. Exiting."
        )
        sys.exit(1)

    # Initialize agent core
    agent = AttendanceAgent(config)
    logger.info("Agent ID: %s", agent.agent_id)

    # Register public key with Django
    if not args.no_register:
        ok = agent.register_with_django()
        if not ok:
            logger.warning(
                "Could not register with Django. Ensure Django is running and ATTENDANCE_AGENT_API_TOKEN matches."
            )
            logger.warning("Continuing anyway — will retry on next restart.")

    # Start heartbeat background thread
    heartbeat = HeartbeatSender(
        django_url=config.django_url,
        api_token=config.api_token,
        agent_id=agent.agent_id,
        get_active_sessions=agent.list_active_sessions,
        interval_seconds=config.heartbeat_interval_seconds,
        verify_ssl=config.verify_ssl,
        register_func=agent.register_with_django,
    )
    heartbeat.start()
    logger.info("Heartbeat thread started (interval=%ds).", config.heartbeat_interval_seconds)

    # Create and start Flask HTTP server
    app = create_app(agent, config)
    logger.info(
        "Attendance Agent HTTP server starting on http://%s:%d",
        config.hotspot_ip,
        config.port,
    )
    logger.info("Students should fetch challenges from: http://%s:%d/challenge?session_id=<id>", config.hotspot_ip, config.port)

    try:
        # Use Werkzeug dev server (sufficient for LAN; use gunicorn in production)
        app.run(
            host=config.host,
            port=config.port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        logger.info("Shutting down Attendance Agent...")
    finally:
        heartbeat.stop()
        heartbeat.join(timeout=5)
        logger.info("Agent stopped.")


if __name__ == "__main__":
    main()
