from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse


def rate_limit_request(key_prefix: str, limit: int = 5, window_seconds: int = 60):
    """
    Decorator enforcing cache-backed rate limiting per IP / User.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Identify caller by user ID if authenticated, else client IP
            if hasattr(request, 'user') and request.user.is_authenticated:
                identifier = f"user_{request.user.id}"
            else:
                identifier = f"ip_{request.META.get('REMOTE_ADDR', '0.0.0.0')}"

            cache_key = f"rate_limit:{key_prefix}:{identifier}"
            current_count = cache.get(cache_key, 0)

            if current_count >= limit:
                return JsonResponse(
                    {
                        "status": "error",
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests. Please wait before retrying."
                    },
                    status=429
                )

            cache.set(cache_key, current_count + 1, window_seconds)
            return view_func(request, *args, **kwargs)

        return _wrapped_view
    return decorator
