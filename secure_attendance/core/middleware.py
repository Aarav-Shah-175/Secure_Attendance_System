import ipaddress
import logging
from django.utils import timezone
from django.http import HttpResponse
from core.models import AttendanceSession

logger = logging.getLogger(__name__)


class HotspotRestrictionMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, "user"):
            if request.user.is_authenticated and request.user.role == "student":
                active_session = AttendanceSession.objects.filter(
                    active=True,
                    expiry__gt=timezone.now()
                ).first()

                if active_session:
                    client_ip = request.META.get("REMOTE_ADDR")

                    try:
                        student_ip = ipaddress.ip_address(client_ip)
                        network = ipaddress.ip_network(active_session.subnet_range)

                        if student_ip not in network:
                            logger.warning(
                                "Student %s IP %s outside allowed subnet %s",
                                request.user.email,
                                client_ip,
                                active_session.subnet_range
                            )
                            return HttpResponse(
                                "Not connected to professor hotspot",
                                status=403
                            )
                    except Exception as e:
                        logger.error("Network validation middleware error: %s", str(e))
                        return HttpResponse(
                            "Network validation failed",
                            status=403
                        )

        return self.get_response(request)
