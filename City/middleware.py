from django.utils.deprecation import MiddlewareMixin

class CacheControlMiddleware(MiddlewareMixin):
    """
    Middleware to add Cache-Control headers to media files for browser-side caching.
    """
    def process_response(self, request, response):
        if request.path.startswith('/media/'):
            # Cache media files for 24 hours (86400 seconds)
            response['Cache-Control'] = 'public, max-age=86400'
        return response
