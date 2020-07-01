import json
import os
from google.oauth2 import service_account
import googleapiclient.discovery

import logging

logger = logging.getLogger(__name__)

def _load_drive_client():
    keyfile_str = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', None)
    if not keyfile_str:
        logger.warn("Environment variable GOOGLE_SERVICE_ACCOUNT_JSON not found.")
        return None
    
    service_account_info = json.loads(keyfile_str)
    scopes = ['https://www.googleapis.com/auth/drive.metadata']
    credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=scopes)
    delegated_credentials = credentials.with_subject("sripathi.krishnan@hashedin.com")
    drive_client = googleapiclient.discovery.build('drive', 'v3', credentials=delegated_credentials)
    return drive_client

def list_files(service):
    # Call the Drive v3 API
    results = service.files().list(
        pageSize=10, fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        print('No files found.')
    else:
        print('Files:')
        for item in items:
            print(u'{0} ({1})'.format(item['name'], item['id']))

if __name__ == '__main__':
    list_files(_load_drive_client())