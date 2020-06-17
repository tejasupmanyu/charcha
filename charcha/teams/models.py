from django.db import models

class GchatUser(models.Model):
    '''
    A user imported from google hangouts chat. 
    Where possible, the gchat user is associated to a charcha user.

    Ideally, google chat users should be the same as charcha users, but there are some challenges

    1. Google Hangouts API does not expose email, it only provides a display name. 
        So we have to use the display name to try and match to users within Charcha
        This matching is obviously not fool-proof. 
    2. Google Hangouts only exposes current employees. Charcha may have users that are no longer employees.
        In this case, ideally we should deactivate the corresponding charcha user, if possible.
    3. Charcha can create users using django's password based authentication. 
        These users were allowed in the past, but no are longer supported.
        Another use case is charcha admin users - which are not necessarily gchat users
    
    So charcha users and gchat users are two sets, with a significant overlap - 
    but they are not subsets of each other

    The important thing is to map the users wherever possible. 
    The teams functionality depends on this mapping being accurate
    '''

    