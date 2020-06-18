from itertools import chain
from django.db import models
from django.conf import settings
from django.db import connection, transaction

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
        indexes = [
            models.Index(fields=["key",]),
        ]
        constraints = [
            models.UniqueConstraint(fields=['key',], name="gchat_user_unique_key")
        ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, default=None)
    # Maps to name in google hangout's model
    # See https://developers.google.com/hangouts/chat/reference/rest/v1/User
    key = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)



class TeamManager(models.Manager):
    def my_teams(self, user):
        return Team.objects.all()
    
    def upsert(self, space, name):
        team, created = Team.objects.update_or_create(gchat_space=space, defaults={"name": name})
        return team

class Team(models.Model):
    'A Team is created by adding charcha bot to a room or private message in google chat'
    class Meta:
        db_table = "teams"
        indexes = [
            models.Index(fields=['gchat_space'])
        ]
        constraints = [
            models.UniqueConstraint(fields=['gchat_space',], name="team_unique_gchat_space")
        ]

    objects = TeamManager()
    name = models.CharField(max_length=100)
    gchat_space = models.CharField(max_length=50, default=None, null=True)

    @transaction.atomic
    def sync_team_members(self, members):
        # memers is a list of (key, display_name) tuples
        insert_query = "INSERT INTO incoming_members(key, display_name) VALUES " + ",".join(["(%s, %s)"] * len(members))
        insert_bind_params = list(chain.from_iterable(members))
        with connection.cursor() as c:
            c.execute("""
                CREATE TEMPORARY TABLE incoming_members
                    (key varchar(100), display_name varchar(100)) 
                ON COMMIT DROP;
            """)
            c.execute(insert_query, insert_bind_params)
            c.execute("""
                INSERT INTO gchat_users(key, display_name)
                SELECT key, display_name FROM incoming_members
                ON CONFLICT ON CONSTRAINT gchat_user_unique_key DO NOTHING;
            """)
            c.execute("""
                INSERT INTO team_members(team_id, gchat_user_id)
                SELECT %s, g.id
                FROM gchat_users g JOIN incoming_members im on g.key = im.key
                ON CONFLICT ON CONSTRAINT team_member_unique_gchat_user DO NOTHING;
            """, [self.id])

            c.execute("""
                DELETE FROM team_members t
                WHERE t.team_id = %s AND NOT EXISTS (
                    SELECT 'x' from gchat_users g join incoming_members im on g.key = im.key
                    WHERE g.id = t.gchat_user_id
                );
            """, [self.id])

    def __str__(self):
        return self.name

class TeamMember(models.Model):
    class Meta:
        db_table = "team_members"
        indexes = [
            models.Index(fields=["gchat_user",]),
        ]
        constraints = [
            models.UniqueConstraint(fields=['team', 'gchat_user',], name="team_member_unique_gchat_user")
        ]
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    gchat_user = models.ForeignKey(GchatUser, on_delete=models.PROTECT)
    