import base64
import json
import hmac
import hashlib
import time
from typing import Tuple, Optional

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
from django.contrib.auth.models import User


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_jwt(payload: dict, expires_in_seconds: int = 60 * 60 * 24) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload)
    payload.setdefault("iat", int(time.time()))
    payload.setdefault("exp", int(time.time()) + expires_in_seconds)

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    secret = settings.SECRET_KEY.encode("utf-8")
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_jwt(token: str) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        raise exceptions.AuthenticationFailed("Invalid token format")

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    secret = settings.SECRET_KEY.encode("utf-8")
    expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(signature_b64)):
        raise exceptions.AuthenticationFailed("Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise exceptions.AuthenticationFailed("Invalid token payload")

    now = int(time.time())
    if "exp" in payload and now > int(payload["exp"]):
        raise exceptions.AuthenticationFailed("Token expired")

    return payload


class JwtAuthentication(BaseAuthentication):
    def authenticate(self, request) -> Optional[Tuple[User, None]]:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        payload = decode_jwt(token)
        user_id = payload.get("uid")
        username = payload.get("username")
        if not user_id and not username:
            raise exceptions.AuthenticationFailed("Invalid token claims")
        try:
            user = User.objects.get(id=user_id) if user_id else User.objects.get(username=username)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found")
        return (user, None)


