from django.db import models
from django.conf import settings

class GchatUser(models.Model):
    '''
    A user imported from google hangouts chat group "announcements". 
    Everyone in hashedin is part of this group
    
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

    class Meta:
        db_table = "gchat_users"
        index_together = [
            ["key",],
        ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, default=None)
    # Maps to name in google hangout's model
    # See https://developers.google.com/hangouts/chat/reference/rest/v1/User
    key = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)

class TeamManager(models.Manager):
    def my_teams(self, user):
        return Team.objects.all()

class Team(models.Model):
    'A Team is created by adding charcha bot to a room or private message in google chat'
    class Meta:
        db_table = "teams"

    objects = TeamManager()
    name = models.CharField(max_length=100)
    gchat_space = models.CharField(max_length=50, default=None, null=True)

    def __str__(self):
        return self.name

class TeamMember(models.Model):
    class Meta:
        db_table = "team_members"
        index_together = [
            ["user",],
            ["gchat_user",],
        ]
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    gchat_user = models.ForeignKey(GchatUser, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, default=None)

