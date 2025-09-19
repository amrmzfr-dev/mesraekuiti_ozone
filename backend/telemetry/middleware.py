from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib.auth import logout


class PreventBackAfterLogoutMiddleware(MiddlewareMixin):
    """
    Middleware to prevent users from accessing cached pages after logout.
    Adds cache control headers to prevent browser caching of authenticated pages.
    """
    
    def process_response(self, request, response):
        # Only apply to authenticated pages (not API endpoints)
        if (request.user.is_authenticated and 
            not request.path.startswith('/api/') and 
            not request.path.startswith('/admin/') and
            not request.path.startswith('/accounts/')):
            
            # Add headers to prevent caching
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
        return response
