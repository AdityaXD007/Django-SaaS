from .base import *

SECRET_KEY = "django-insecure-test-key-must-be-at-least-fifty-characters-long-for-jwt"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

DATABASES["default"]["CONN_MAX_AGE"] = 0
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
INVITATION_RETURN_TOKEN = True

