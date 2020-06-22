import unittest
from django.test import TestCase
from charcha.discussions.tests import BaseDiscussionTests
from .models import Team
from .views import sync_team as sync_team_view

def to_sync_format(members):
    return [(m.username, m.username) for m in members]

class TeamSynchronizationTests(BaseDiscussionTests):
    def assertTeamHasUsers(self, team, users):
        for user in users:
            self.assertTrue(team.members.filter(gchat_user__user__id=user.id).exists())

    def assertTeamDoesNotHaveUsers(self, team, users):
        for user in users:
            self.assertFalse(team.members.filter(gchat_user__user__id=user.id).exists())
                
    def test_team_sync(self):
        team = Team.objects.create(name="teamname", gchat_space="spaces/teamname")
        self.assertEqual(len(team.members.all()), 0)

        team.sync_team_members(to_sync_format([self.amit]))
        self.assertTeamHasUsers(team, [self.amit])

        team.sync_team_members(to_sync_format([self.amit, self.ramesh]))
        self.assertTeamHasUsers(team, [self.amit, self.ramesh])

        team.sync_team_members(to_sync_format([self.amit, self.swetha]))
        self.assertEqual(len(team.members.all()), 2)
        self.assertTeamHasUsers(team, [self.amit, self.swetha])
        self.assertTeamDoesNotHaveUsers(team, [self.ramesh])

    @unittest.skip
    def test_team_sync_view(self):
        'This test actually calls google APIs, so skipping it'
        sync_team_view("spaces/AAAAHNB6wZ0", 'leadership')
        team = Team.objects.get(name="leadership")
        for m in team.members.all():
            print(m.gchat_user.display_name)