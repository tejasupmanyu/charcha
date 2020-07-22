import json
import os
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials
from oauth2client.client import GoogleCredentials

from apiclient.discovery import build

def _load_slide_client():
    keyfile_str = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', None)
    if not keyfile_str:
        logger.warn("Environment variable GOOGLE_SERVICE_ACCOUNT_JSON not found. \
            Disabling notifications via google chatbot")
        return None
    
    keyfile_dict = json.loads(keyfile_str)
    scopes = 'https://www.googleapis.com/auth/drive'
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        keyfile_dict, scopes)
    slides_client = build('slides', 'v1', http=credentials.authorize(Http()))
    return slides_client

# client = _load_slide_client()

def get_nested(obj, path):
    tokens = path.split('.')
    for token in tokens:
        if token in obj:
            obj = obj[token]
        else:
            return None
    return obj

with open('/home/sri/apps/charcha/hashers.latest.json') as f:
    hasher_profile = json.load(f)

slides = hasher_profile['slides']
slide_emails = [None] * len(slides)
for index, slide in enumerate(slides):
    notes = []
    notes_page_elements = get_nested(slide, 'slideProperties.notesPage.pageElements')
    if not notes_page_elements:
        continue
    for pe in notes_page_elements:
        text_elements = get_nested(pe, 'shape.text.textElements')
        if not text_elements:
            continue
        for te in text_elements:
            text = get_nested(te, 'textRun.content')
            if not text:
                continue
            notes.append(text)
    
    slide_emails[index] = "".join(notes)

print(slide_emails)