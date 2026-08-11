"""
Attendance Agent — Standalone network verification process.

Replaces subnet/IP-based verification in Django.
Runs on the professor's laptop alongside the hotspot.
Students fetch cryptographic challenges via HTTP (LAN).
Django verifies proofs cryptographically — never touching IPs.
"""
