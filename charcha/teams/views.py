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

@require_http_methods(['POST'])
@csrf_exempt
def google_chatbot(request):
    event = json.loads(request.body)
    text = None
    if event['type'] == 'ADDED_TO_SPACE':
        if event['space']['type'] == 'DM':
            space_id = event['space']['name']
            email = event['user']['email']
            user_exists = update_gchat_space(email, space_id)
            if user_exists:
                text = "From now on, I will notify you of any updates in the discussions you participate."
            else:
                text = """You haven't logged in to charcha yet. Please do the following:        

                1. Remove charcha bot 
                2. Go to https://charcha.hashedin.com and login with your @hashedin.com email address
                3. Then come back and add charcha bot once again
                """
        elif event['space']['type'] == 'ROOM':
            space = event['space']['name']
            # room name can be None for DMs between multiple people
            room_name = event['space'].get('displayName', None)
            sync_team(space, room_name)
            text = "Done! I have created a new team in charcha. \
                You can now have private discussions in charcha, and only members of this room will be able to participate."

    elif event['type'] == 'REMOVED_FROM_SPACE':
        if event['space']['type'] == 'DM':
            email = event['user']['email']
            update_gchat_space(email, None)
    elif event['type'] == 'MESSAGE':
        if event['space']['type'] == 'DM':
            text = "This is a one way street. I will completely ignore anything you type."
        elif event['space']['type'] == 'ROOM':
            if 'synchronize' in event['message']['argumentText']:
                space = event['space']['name']
                room_name = event['space']['displayName']
                sync_team(space, room_name)
                text = "Done, I have synchronized team members with Charcha"
            else:
                text = "Sorry, I don't understand your message. Try @charcha synchronize"
    if text:
        return JsonResponse({"text": text})
    else:
        return HttpResponse("OK")
