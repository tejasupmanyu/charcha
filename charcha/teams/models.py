# from itertools import chain
# from django.db import models
# from django.conf import settings
# from django.db import connection, transaction
# from django.contrib.auth import get_user_model
# from django.core.exceptions import PermissionDenied


# class TeamManager(models.Manager):
#     def my_teams(self, user):
#         teams = Team.objects.raw("""
#             SELECT t.id, t.name 
#             FROM teams t join team_members tm on t.id = tm.team_id 
#                 JOIN gchat_users g on tm.gchat_user_id = g.id
#             WHERE g.user_id = %s"""
#         , [user.id])
#         return teams

#     def belongs_to_all_teams(self, user, teams):
#         team_ids = [t.id for t in teams]
#         in_clause = ["%s"] * len(team_ids)
#         in_clause = ",".join(in_clause)

#         my_teams = Team.objects.raw("""
#             SELECT t.id FROM teams t join team_members tm on t.id = tm.team_id
#                 JOIN gchat_users g on tm.gchat_user_id = g.id
#             WHERE g.user_id = %s and t.id in (""" + in_clause + ')'
#         , [user.id] + team_ids)

#         if len(my_teams) != len(team_ids):
#             return False
#         else: 
#             return True

#     def upsert(self, space, name):
#         team, created = Team.objects.update_or_create(gchat_space=space, defaults={"name": name})
#         return team

# class Team(models.Model):
#     'A Team is created by adding charcha bot to a room or private message in google chat'
#     class Meta:
#         db_table = "teams"
#         indexes = [
#             models.Index(fields=['gchat_space'])
#         ]
#         constraints = [
#             models.UniqueConstraint(fields=['gchat_space',], name="team_unique_gchat_space")
#         ]

#     objects = TeamManager()
#     name = models.CharField(max_length=100)
#     description = models.CharField(max_length=200, blank=True)
#     about = models.TextField(max_length=4096, blank=True)
#     gchat_space = models.CharField(max_length=50, default=None, null=True)

#     def can_view(self, user):
#         return Team.objects.belongs_to_all_teams(user, [self])

#     def check_view_permission(self, user):
#         if not self.can_view(user):
#             raise PermissionDenied("View denied on team " + str(self.id) + " to user " + str(user.id))
    
#     def active_team_members(self):
#         return get_user_model().objects.raw("""
#             WITH last_activity as (
#             SELECT rs.team_id, rs.user_id, max(rs.submission_time) as last_activity FROM (
#                 SELECT tp.team_id, p.author_id as user_id, p.submission_time
#                 FROM team_posts tp JOIN posts p on tp.post_id = p.id
#                 WHERE p.submission_time > 'now'::timestamp - '30 days'::interval
#                 UNION ALL
#                 SELECT tp.team_id, c.author_id as user_id, c.submission_time
#                 FROM team_posts tp JOIN posts p on tp.post_id = p.id
#                     JOIN comments c on p.id = c.post_id
#                 WHERE c.submission_time > 'now'::timestamp - '30 days'::interval
#             ) rs
#             GROUP BY rs.team_id, rs.user_id
#             )
#             SELECT u.id, u.username, 
#             u.first_name || ' ' || u.last_name as display_name, u.avatar
#             FROM last_activity la JOIN users u on la.user_id = u.id
#             WHERE la.team_id = %s
#             ORDER BY la.last_activity DESC
#             LIMIT 10;
#         """, [self.id])

#     @transaction.atomic
#     def sync_team_members(self, members):
#         # memers is a list of (key, display_name) tuples
#         insert_query = "INSERT INTO incoming_members(key, display_name) VALUES " + ",".join(["(%s, %s)"] * len(members))
#         insert_bind_params = list(chain.from_iterable(members))
#         with connection.cursor() as c:
#             c.execute("""
#                 CREATE TEMPORARY TABLE incoming_members
#                     (key varchar(100), display_name varchar(100)) 
#                 ON COMMIT DROP;
#             """)
#             c.execute(insert_query, insert_bind_params)
#             c.execute("""
#                 INSERT INTO gchat_users(key, display_name)
#                 SELECT key, display_name FROM incoming_members
#                 ON CONFLICT ON CONSTRAINT gchat_user_unique_key DO NOTHING;
#             """)
#             c.execute("""
#                 INSERT INTO team_members(team_id, gchat_user_id)
#                 SELECT %s, g.id
#                 FROM gchat_users g JOIN incoming_members im on g.key = im.key
#                 ON CONFLICT ON CONSTRAINT team_member_unique_gchat_user DO NOTHING;
#             """, [self.id])

#             c.execute("""
#                 DELETE FROM team_members t
#                 WHERE t.team_id = %s AND NOT EXISTS (
#                     SELECT 'x' from gchat_users g join incoming_members im on g.key = im.key
#                     WHERE g.id = t.gchat_user_id
#                 );
#             """, [self.id])

#     def __str__(self):
#         return self.name

# class TeamMember(models.Model):
#     class Meta:
#         db_table = "team_members"
#         indexes = [
#             models.Index(fields=["gchat_user", "team"]),
#         ]
#         constraints = [
#             models.UniqueConstraint(fields=['team', 'gchat_user',], name="team_member_unique_gchat_user"),
#         ]
#     team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="members")
#     gchat_user = models.ForeignKey(GchatUser, on_delete=models.PROTECT)
    