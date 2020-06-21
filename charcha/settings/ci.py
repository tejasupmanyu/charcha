from .production import *

# Don't upload files to S3, instead store them locally
DEFAULT_FILE_STORAGE='django.core.files.storage.FileSystemStorage'
MEDIA_ROOT=os.path.join(BASE_DIR, "media")
MEDIA_URL="/media/"

