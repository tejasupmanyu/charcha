from django.db import models
from django.conf import settings
import json
import os
import logging
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials
from apiclient.discovery import build

logger = logging.getLogger(__name__)

def _load_chat_client():
    keyfile_str = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', None)
    if not keyfile_str:
        logger.warn("Environment variable GOOGLE_SERVICE_ACCOUNT_JSON not found. \
            Disabling notifications via google chatbot")
        return None
    
    keyfile_dict = json.loads(keyfile_str)
    scopes = 'https://www.googleapis.com/auth/chat.bot'
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        keyfile_dict, scopes)
    chat_client = build('chat', 'v1', http=credentials.authorize(Http()))
    return chat_client

# chat_client can be None, in which case we will not send any notifications via chat
_chat_client = _load_chat_client()

def members(spaceid):
    members = []
    page_token = None
    is_first_call = True
    while is_first_call or page_token:
        is_first_call = False
        response = _chat_client.spaces().members().list(parent=spaceid, pageSize=1000, pageToken=page_token).execute()
        page_token = response['nextPageToken']
        members.extend(response['memberships'])
    return members

def notify_space(spaceid, event):
    if not _chat_client:
      return
    message = _create_message(event)
    try:
      _chat_client.spaces().messages() \
          .create(parent=spaceid, body=message) \
          .execute()
    except Exception:
      logger.exception("Cannot send message to space " + spaceid)

def _create_message(event):
    return {
      "cards":[
        {
          "header":{
            "title": event["heading"],
            "subtitle": event["sub_heading"],
            "imageUrl": event["image"],
            "imageStyle":"IMAGE"
          }
        },
        {
          "sections":[
            {
              "widgets":[
                {
                  "textParagraph":{
                    "text":"<b>" + event["line1"] + "</b>"
                  }
                },
                {
                  "textParagraph":{
                    "text": event["line2"]
                  }
                }
              ]
            }
          ]
        },
        {
          "sections":{
            "widgets":[
              {
                "buttons":[
                  {
                    "textButton":{
                      "text": event["link_title"],
                      "onClick":{
                        "openLink":{
                          "url": event["link"]
                        }
                      }
                    }
                  }
                ]
              }
            ]
          }
        }
      ]
    }


