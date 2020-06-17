from .common import *

_debug = os.environ.get("DEBUG", 'False')
DEBUG = (_debug == "True" or _debug == "true")
ALLOWED_HOSTS = ['charcha.hashedin.com']
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=False

DEFAULT_FILE_STORAGE='storages.backends.s3boto3.S3Boto3Storage'
MEDIA_ROOT=os.path.join(BASE_DIR, "media")
MEDIA_URL="https://charcha-media-files.s3.ap-south-1.amazonaws.com/"
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME='charcha-media-files'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=315360000, public, immutable'
}
AWS_S3_REGION_NAME='ap-south-1'
AWS_DEFAULT_ACL="public-read"
