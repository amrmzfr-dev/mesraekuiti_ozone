from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
import json

# Import hardcoded access control
from .access_control import get_user_access, is_user_authorized
from .jwt_auth import create_jwt, decode_jwt


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def api_login(request):
    """
    API endpoint for user login
    Returns JSON response with user info and session cookie
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return Response({
                'success': False,
                'error': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_active:
                # Check hardcoded access control
                access_info = get_user_access(username)
                if access_info is None:
                    return Response({
                        'success': False,
                        'error': 'Access denied - user not in authorized list'
                    }, status=status.HTTP_403_FORBIDDEN)
                
                # Issue JWT instead of server session
                token = create_jwt({
                    'uid': user.id,
                    'username': user.username,
                })
                return Response({
                    'success': True,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email or 'Not provided',
                        'first_name': user.first_name or '',
                        'last_name': user.last_name or '',
                        'access_level': access_info['access_level'],
                        'can_manage_devices': access_info['can_manage_devices'],
                        'can_view_stats': access_info['can_view_stats'],
                        'can_export_data': access_info['can_export_data'],
                    },
                    'token': token,
                })
            else:
                return Response({
                    'success': False,
                    'error': 'Account is disabled'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'success': False,
                'error': 'Invalid username or password'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
    except json.JSONDecodeError:
        return Response({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def api_logout(request):
    """
    API endpoint for user logout
    """
    try:
        logout(request)  # Idempotent: clears session if present
        return Response({'success': True, 'message': 'Successfully logged out'})
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_user_info(request):
    """
    API endpoint to get current user information
    """
    try:
        # Authorize via Bearer token
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.lower().startswith('bearer '):
            return Response({'success': False, 'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        payload = decode_jwt(auth.split(' ', 1)[1])
        user = User.objects.get(id=payload.get('uid'))
        # Check hardcoded access control
        access_info = get_user_access(user.username)
        if access_info is None:
            return Response({
                'success': False,
                'error': 'Access denied - user not in authorized list'
            }, status=status.HTTP_403_FORBIDDEN)
        
        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email or 'Not provided',
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'access_level': access_info['access_level'],
                'can_manage_devices': access_info['can_manage_devices'],
                'can_view_stats': access_info['can_view_stats'],
                'can_export_data': access_info['can_export_data'],
            }
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def api_register(request):
    """
    API endpoint for user registration
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        email = data.get('email', '')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        
        if not username or not password:
            return Response({
                'success': False,
                'error': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user already exists
        if User.objects.filter(username=username).exists():
            return Response({
                'success': False,
                'error': 'Username already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new user
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        
        return Response({
            'success': True,
            'message': 'User created successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        }, status=status.HTTP_201_CREATED)
        
    except json.JSONDecodeError:
        return Response({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'success': False,
            'error': 'Server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_check_auth(request):
    """
    API endpoint to check if user is authenticated
    """
    try:
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if auth.lower().startswith('bearer '):
            payload = decode_jwt(auth.split(' ', 1)[1])
            access_info = get_user_access(payload.get('username'))
            if access_info is None:
                return Response({'authenticated': False, 'error': 'Access denied - user not in authorized list'})
            return Response({
                'authenticated': True,
                'user': {
                    'id': payload.get('uid'),
                    'username': payload.get('username'),
                    'email': 'Not provided',
                    'first_name': '',
                    'last_name': '',
                    'access_level': access_info['access_level'],
                    'can_manage_devices': access_info['can_manage_devices'],
                    'can_view_stats': access_info['can_view_stats'],
                    'can_export_data': access_info['can_export_data'],
                }
            })
        return Response({'authenticated': False})
    except Exception as e:
        return Response({
            'authenticated': False,
            'error': 'Server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def api_csrf(request):
    """Return CSRF token and set CSRF cookie."""
    token = get_token(request)
    return Response({"csrfToken": token})
