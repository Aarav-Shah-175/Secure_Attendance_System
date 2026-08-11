"""
middleware.py — HTTP request middleware.

HotspotRestrictionMiddleware has been REMOVED in the Agent-based architecture.
Network presence is now proven by the Attendance Agent challenge-response
mechanism — Django no longer inspects client IP addresses for subnet membership.
"""
# No middleware required for network restriction in the new architecture.
# This file is intentionally minimal to preserve Django's middleware list reference.
