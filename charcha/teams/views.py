import json
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from charcha.discussions.models import update_gchat_space
from .models import Team
from .bot import members
from django.http import HttpResponse, JsonResponse

# This function does not depend on request / response objects
# Ideally, it should have been in models.py
# But we don't want a dependency from models.py to bot.py
# So as a workaround, we put this in views.py instead
def sync_team(space, room_name):
    team_members = members(space)
    team_members = [(g["member"]["name"], g["member"]["displayName"]) for g in team_members]
    
    # Private direct messages between 3 or more people is an anonymous room without a name
    # In that case, we create the room name from the names of the members
    if not room_name:
        room_name = ", ".join([t[1] for t in team_members])
        room_name = room_name[:95]
    
    team = Team.objects.upsert(space, room_name)
    team.sync_team_members(team_members)

