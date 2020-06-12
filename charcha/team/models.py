from django.db import models
from django.conf import settings

ADMIN = 1
MEMBER = 2
GUEST = 3

class TeamManager(models.Manager):
    def get_my_teams(self, user):
        public_teams = Team.objects.filter(is_public=True)
        private_teams = Team.objects.filter(members__user=user)

        my_teams = public_teams.union(private_teams)
        return my_teams

class Team(models.Model):
    'A Team organizes a users, channels and discussions'
    class Meta:
        db_table = 'teams'

    objects = TeamManager()
    name = models.CharField(max_length=120)

    # If a team is public, all users have access it to it
    # also, we will not explicity define TeamMember's for this team
    is_public = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class TeamMember(models.Model):
    'Mapping between Team and a User'
    class Meta:
        db_table = 'team_members'
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.IntegerField(choices = (
        (ADMIN, 'Admin'),
        (MEMBER, 'Member'),
        (GUEST, 'Guest'),
    ))
