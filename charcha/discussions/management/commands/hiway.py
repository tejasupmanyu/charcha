import requests
import json
import urllib
import os
import django
import datetime
from collections import namedtuple
from django.core.management.base import BaseCommand, CommandError
from charcha.discussions.models import User, Tag
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)
METABASE_URL = "https://data.hashedin.com/api/card/<<ID>>/query"

HasherProfile = namedtuple('HasherProfile', ('id', 'email', 'first_name', 'last_name', 'band', 'designation', 'employee_id', 'joining_date'))
Project = namedtuple('Project', ('id', 'state', 'title', 'project_manager', 'project_manager_email'))

IS_PROJECT_STATE_VISIBLE = {
    'LEAD':  True,
    'ABANDONDED': False, 
    'CLOSED': False, 
    'COMPLETED': False, 
    'IN_PROGRESS': True, 
    'SOW': True, 
    'DELIVERED': True, 
}

class Command(BaseCommand):
    help = 'Imports hashers and projects from hiway'

    def handle(self, *args, **options):
        hashedin, _ = Tag.objects.get_or_create(name="Hashedin", parent=None, is_external=False)
        hashers, _ = Tag.objects.get_or_create(name="Hashers", parent=hashedin, is_external=False)
        projects_tag, _ = Tag.objects.get_or_create(name="Projects", parent=hashedin, is_external=False)

        metabase_token = _login_to_metabase()
        hashers = get_hasher_profiles(metabase_token)
        hiway_projects = get_projects(metabase_token)
        
        for hasher in hashers:
            try:
                user = User.objects.get(email=hasher.email)
                user.band = hasher.band
                user.designation = hasher.designation
                user.employee_id = hasher.employee_id
                if hasher.joining_date:
                    user.joining_date = datetime.datetime.strptime(hasher.joining_date, '%Y-%m-%dT%H:%M:%SZ')
                user.save()
            except User.DoesNotExist:
                logger.warn("User with email " + hasher.email + " does not exist in charcha database")

        for project in hiway_projects:
            is_visible = IS_PROJECT_STATE_VISIBLE[project.state]
            Tag.objects.update_or_create(
                ext_id = project.id,
                parent = projects_tag,
                defaults = {
                    'name': project.title,
                    'ext_code': project.id,
                    'fqn': "Projects: " + project.title,
                    'is_external': True,
                    'is_visible': is_visible,
                    'imported_on': timezone.now()
                }
            )


def _login_to_metabase():
    metabase_username = os.environ['HIWAY_METABASE_USERNAME']
    metabase_password = os.environ['HIWAY_METABASE_PASSWORD']

    response = requests.post('https://data.hashedin.com/api/session', 
            json={"username": metabase_username, "password": metabase_password})

    if response.status_code < 200 or response.status_code >= 300:
        raise Exception('Could not login to metabase - ' + str(response))

    return response.json()['id']

def get_projects(token):
    return _fetch_from_metabase(token, 106, Project)

def get_hasher_profiles(token):
    return _fetch_from_metabase(token, 73, HasherProfile)

def _fetch_from_metabase(token, card_id, klass):
    url = METABASE_URL.replace("<<ID>>", str(card_id))
    response = requests.post(url, headers={
        'X-Metabase-Session': token,
        'Content-Type': 'application/json'
    })
    if response.status_code < 200 or response.status_code >= 300:
        raise Exception("Could not fetch response for url " + url + ", got a non-200 status code " + str(response))

    objs = [klass(*r) for r in response.json()['data']['rows']]
    return objs

