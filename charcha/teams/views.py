import json
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from charcha.discussions.models import update_gchat_space
from .models import Team
from .bot import members

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
            room_name = event['space']['displayName']
            team_members = members(space)
            team_members = [(g["member"]["name"], g["member"]["displayName"]) for g in team_members]
            team = Team.objects.upsert(space, room_name)
            team.sync_team_members(team_members)
            text = "Done! I have created a new team in charcha. \
                You can now have private discussions in charcha, and only members of this room will be able to participate."

    elif event['type'] == 'REMOVED_FROM_SPACE':
        if event['space']['type'] == 'DM':
            email = event['user']['email']
            update_gchat_space(email, None)
    elif event['type'] == 'MESSAGE':
        text = "This is a one way street. I will completely ignore anything you type."

    if text:
        return JsonResponse({"text": text})
    else:
        return HttpResponse("OK")
