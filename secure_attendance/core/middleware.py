import ipaddress
from django.utils import timezone#type: ignore
from core.models import AttendanceSession
from django.http import HttpResponse#type: ignore


class HotspotRestrictionMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # Let Django attach user first
        response = None

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

                        print("==== HOTSPOT DEBUG ====")
                        print("Student IP:", client_ip)
                        print("Expected subnet:", active_session.subnet_range)
                        print("Gateway IP:", active_session.gateway_ip)
                        print("========================")
                        if student_ip not in network:
                            return HttpResponse(
                                "Not connected to professor hotspot",
                                status=403
                            )
                    except Exception:
                        return HttpResponse(
                            "Network validation failed",
                            status=403
                        )

        response = self.get_response(request)
        return response
