from .common import *

_debug = os.environ.get("DEBUG", 'False')
DEBUG = (_debug == "True" or _debug == "true")
ALLOWED_HOSTS = ['charcha.hashedin.com']
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
