import requests
import json

def call_webhook(raw_body):
    r = requests.post("http://localhost:8000/chatbot", json=json.loads(raw_body))
    print(r.content)

def add_user(space, user_pk, user_display_name, email):
    body = """
    {
        "type": "ADDED_TO_SPACE",
        "eventTime": "2017-03-02T19:02:59.910959Z",
        "space": {
            "name": "<<SPACE>>",
            "displayName": "Sripathi Krishnan",
            "type": "DM"
        },
        "user": {
            "name": "<<USER_PK>>",
            "displayName": "<<USER_NAME>>",
            "avatarUrl": "https://lh3.googleusercontent.com/.../photo.jpg",
            "email": "<<EMAIL>>"
        }
    }
    """

    body = body\
        .replace("<<SPACE>>", space)\
        .replace('<<USER_PK>>', user_pk)\
        .replace('<<USER_NAME>>', user_display_name)\
        .replace('<<EMAIL>>', email)
    call_webhook(body)

def remove_user(space, user_pk, user_display_name, email):
    body = """
    {
        "type": "REMOVED_FROM_SPACE",
        "eventTime": "2017-03-02T19:02:59.910959Z",
        "space": {
            "name": "<<SPACE>>",
            "displayName": "Sripathi Krishnan",
            "type": "DM"
        },
        "user": {
            "name": "<<USER_PK>>",
            "displayName": "<<USER_NAME>>",
            "avatarUrl": "https://lh3.googleusercontent.com/.../photo.jpg",
            "email": "<<EMAIL>>"
        }
    }
    """

    body = body\
        .replace("<<SPACE>>", space)\
        .replace('<<USER_PK>>', user_pk)\
        .replace('<<USER_NAME>>', user_display_name)\
        .replace('<<EMAIL>>', email)
    call_webhook(body)

def add_room(space, room_name):
    body = """
    {
        "type": "ADDED_TO_SPACE",
        "eventTime": "2017-03-02T19:02:59.910959Z",
        "space": {
            "name": "<<SPACE>>",
            "displayName": "<<ROOM_NAME>>",
            "type": "ROOM"
        },
        "user": {
            "name": "<<USER_PK>",
            "displayName": "<<USER_NAME>>",
            "avatarUrl": "https://lh3.googleusercontent.com/.../photo.jpg",
            "email": "chuck@example.com"
        }
    }
    """

    body = body.replace("<<SPACE>>", space).replace('<<ROOM_NAME>>', room_name)
    call_webhook(body)

def remove_from_room(space):
    body = """
    {
        "type": "REMOVED_FROM_SPACE",
        "eventTime": "2017-03-02T19:02:59.910959Z",
        "space": {
            "name": "<<SPACE>>",
            "type": "ROOM"
        },
        "user": {
            "name": "users/12345678901234567890",
            "displayName": "Chuck Norris",
            "avatarUrl": "https://lh3.googleusercontent.com/.../photo.jpg",
            "email": "chuck@example.com"
        }
    }
    """    
    body = body.replace("<<SPACE>>", space)
    call_webhook(body)

if __name__ == "__main__":
    #add_room('spaces/abcd', "abcd - Dance")
    #remove_from_room('spaces/abcd')
    add_user('space/user-private-space', 'users/107907793061583143858', "Sripathi Krishnan", "sripathi.krishnan@hashedin.com")
    #remove_user('space/user-private-space', 'users/107907793061583143858', "Sripathi Krishnan", "sripathi.krishnan@hashedin.com")