import unittest
from contextlib import contextmanager
from django.test import Client
from collections import defaultdict
from django.test import TransactionTestCase, TestCase
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from .models import Post, Vote, Comment, User, TeamPosts
from . import models
from charcha.teams.models import GchatUser, Team, TeamMember

# Tests should not send out a notification
models.notify_space = lambda s, e: None

@contextmanager
def record_notifications():
    notifications = defaultdict(list)
    def notify_space(space_id, event):
        notifications[space_id].append(event)
    
    original_notify_space = models.notify_space
    
    try:
        models.notify_space = notify_space
        yield notifications
    finally:
        models.notify_space = original_notify_space

def _create_user(username):
    user = User.objects.create_user(
        username=username, password="top_secret", 
        email=username + "@hashedin.com", gchat_space=username)
    GchatUser(user=user, key=username, display_name=username).save()
    return user

def _create_team(teamname, members):
    def to_sync_format(members):
        return [(m, m) for m in members]

    team = Team(name=teamname, gchat_space=teamname)
    team.save()
    team.sync_team_members(to_sync_format(members))
    return team

class BaseDiscussionTests(TransactionTestCase):
    def setUp(self):
        self._create_users()
        self._create_teams()

    def _create_users(self):
        self.ramesh = _create_user("ramesh")
        self.amit = _create_user("amit")
        self.swetha = _create_user("swetha")
        self.mark = _create_user("mark")
        self.martin = _create_user("martin")
        self.ekta = _create_user("ekta")
        self.ejaz = _create_user("ejaz")

    def _create_teams(self):
        earthlings = ["ekta", "ejaz"]
        martians = ["mark", "martin"]
        everyone = ["ramesh", "amit", "swetha"]
        everyone.extend(martians)
        everyone.extend(earthlings)
        self.earthlings = _create_team("earthlings", earthlings)
        self.universe = _create_team("universe", everyone)
        self.martians = _create_team("martians", martians)

    def new_discussion(self, author, title, team):
        post = Post(title=title,
            html="Does not matter",
            author=author)
        post = Post.objects.new_post(author, post, [team])
        return post

class DiscussionTests(BaseDiscussionTests):
    def test_I_cant_vote_for_me(self):
        post = self.new_discussion(self.ramesh, "Ramesh's Biography", self.universe)
        self.assertEquals(post.upvotes, 0)
        post.upvote(self.ramesh)
        post = Post.objects.get(pk=post.id, requester=self.ramesh)
        self.assertEquals(post.upvotes, 0)

    def test_double_voting(self):
        post = self.new_discussion(self.ramesh, "Ramesh's Biography", self.universe)
        self.assertEquals(post.upvotes, 0)
        post.upvote(self.amit)
        post = Post.objects.get(pk=post.id, requester=self.amit)
        self.assertEquals(post.upvotes, 1)
        post.upvote(self.amit)
        post = Post.objects.get(pk=post.id, requester=self.amit)
        self.assertEquals(post.upvotes, 1)

    def test_voting_on_home_page(self):
        # Ramesh starts a discussion
        post = self.new_discussion(self.ramesh, "Ramesh's Biography", self.universe)

        # Amit upvotes the post
        post.upvote(self.amit)

        # Home page as seen by Amit
        post = Post.objects.recent_posts_with_my_votes(self.amit)[0]
        self.assertTrue(post.is_upvoted)
        self.assertFalse(post.is_downvoted)
        self.assertEquals(post.upvotes, 1)
        self.assertEquals(post.downvotes, 0)

        # Swetha downvotes
        post.downvote(self.swetha)

        # Home page as seen by Swetha
        post = Post.objects.recent_posts_with_my_votes(self.swetha)[0]
        self.assertFalse(post.is_upvoted)
        self.assertTrue(post.is_downvoted)
        self.assertEquals(post.upvotes, 1)
        self.assertEquals(post.downvotes, 1)
        
        # Amit undo's his vote
        post.undo_vote(self.amit)

        # Home page as seen by Amit
        post = Post.objects.recent_posts_with_my_votes(self.amit)[0]
        self.assertFalse(post.is_upvoted)
        self.assertFalse(post.is_downvoted)
        self.assertEquals(post.upvotes, 0)
        self.assertEquals(post.downvotes, 1)

    def test_comments_ordering(self):
        _c1 = "See my Biography!"
        _c2 = "Dude, this is terrible!"
        _c3 = "Why write your biography when you haven't achieved a thing!"
        _c4 = "Seriously, that's all you have to say?"

        post = self.new_discussion(self.ramesh, "Ramesh's Biography", self.universe)
        self.assertEquals(post.num_comments, 0)

        rameshs_comment = post.add_comment(_c1, self.ramesh)
        amits_comment = rameshs_comment.reply(_c2, self.amit)
        swethas_comment = rameshs_comment.reply(_c3, self.swetha)
        rameshs_response = amits_comment.reply(_c4, self.ramesh)

        comments = [c.html for c in 
                    Comment.objects.best_ones_first(post, self.ramesh)]

        self.assertEquals(comments, [_c1, _c2, _c4, _c3])

        # check if num_comments in post object is updated
        post = Post.objects.get(pk=post.id, requester=self.ramesh)
        self.assertEquals(post.num_comments, 4)

    def test_cannot_edit_someone_elses_comment(self):
        post = self.new_discussion(self.ramesh, "Can I edit someone else's comment?", self.universe)
        post.edit_post("this is the new title", "this is the new body", self.ramesh)
        with self.assertRaises(PermissionDenied):
            post.edit_post("Amit trying to edit Ramesh's post", "this is the new body", self.amit)

        # Reload post object to confirm it got saved
        post = Post.objects.get(id=post.id, requester=self.ramesh)
        self.assertEqual(post.title, "this is the new title")
        self.assertEqual(post.html, "this is the new body")

        rameshs_comment = post.add_comment("I think it should not be possible", self.ramesh)
        rameshs_comment.edit_comment("EDIT; I should be able to edit my own comment", self.ramesh)
        with self.assertRaises(PermissionDenied):
            rameshs_comment.edit_comment("Amit trying to edit Ramesh's comment", self.amit)
        
        # Reload comment object to confirm it got saved
        rameshs_comment = Comment.objects.get(id=rameshs_comment.id, requester=self.ramesh)
        self.assertEqual(rameshs_comment.html, "EDIT; I should be able to edit my own comment")

    def test_notifications(self):
        with record_notifications() as notifications:
            # Expect a single notification to broadcast when a new post is created
            post = self.new_discussion(self.ramesh, "Ramesh's Biography", self.universe)
            self.assertEqual(len(notifications), 1, msg="Broadcast Message")
            
            # No private notifications as of now
            self.assertEqual(len(notifications['ramesh']), 0, msg="No private message on new discussion")
            self.assertEqual(len(notifications['amit']), 0, msg="No private message on new discussion")
            self.assertEqual(len(notifications['swetha']), 0, msg="No private message on new discussion")

            # Upvotes don't result in a notification
            # but the person who upvoted gets added to the watchers list
            post.upvote(self.amit)

            # Swetha adds a comment, which triggers private notifications
            swethas_comment = post.add_comment("See my biography as well!", self.swetha)

            # Ramesh and Amit get a private notification
            # Swetha doesn't, because she was the one who commented
            self.assertEqual(len(notifications['ramesh']), 1, msg="Discussion author must get private notification")
            self.assertEqual(len(notifications['amit']), 1, msg="People who upvote must get a private notifcation")
            self.assertEqual(len(notifications['swetha']), 0, 
                    msg="Author of comment must not get notified about her own comment")

class SecurityTests(BaseDiscussionTests):
    def assertPostListEquals(self, actual_posts, expected_posts):
        a = set()
        e = set()
        for p in actual_posts:
            a.add(p.id)
        for p in expected_posts:
            e.add(p.id)
        return a == e

    def test_cannot_create_post_in_team_you_dont_belong(self):
        with self.assertRaises(PermissionDenied):
            self.new_discussion(self.ramesh, "Ramesh is not a martian", self.martians)

    def test_homepage_security(self):
        'I should only see posts from teams I belong'
        blue_post = self.new_discussion(self.ekta, "Earth is blue", self.earthlings)
        red_post = self.new_discussion(self.martin, "Mars is red", self.martians)
        universal_post = self.new_discussion(self.ramesh, "Big bang theory is false", self.universe)

        ekta_homepage = Post.objects.recent_posts_with_my_votes(self.ekta)
        self.assertPostListEquals(ekta_homepage, [blue_post, universal_post])

        martin_homepage = Post.objects.recent_posts_with_my_votes(self.martin)
        self.assertPostListEquals(martin_homepage, [red_post, universal_post])
        
        ramesh_homepage = Post.objects.recent_posts_with_my_votes(self.ramesh)
        self.assertPostListEquals(ramesh_homepage, [universal_post])

        with self.assertRaises(Exception):
            anonymous_posts = Post.objects.recent_posts_with_my_votes(AnonymousUser())

    def test_only_team_members_can_view_post(self):
        post = self.new_discussion(self.martin, "Post related to Mars", self.martians)
        Post.objects.get(id=post.id, requester=self.mark)
        for user in [self.ramesh, self.amit, self.swetha]:
            with self.assertRaises(PermissionDenied):
                Post.objects.get(id=post.id, requester=user)

    def test_only_team_members_can_comment(self):
        post = self.new_discussion(self.martin, "Post related to Mars", self.martians)
        c = post.add_comment("Mars is red", self.mark)
        self.assertEqual(c.html, "Mars is red")
        for user in [self.ramesh, self.amit, self.swetha]:
            with self.assertRaises(PermissionDenied):
                c = post.add_comment("Non-Martians cannot comment", user)
        
    def test_only_team_members_can_view_comments(self):
        post = self.new_discussion(self.martin, "Post related to Mars", self.martians)
        post.add_comment("Mars is red", self.mark)
        post.add_comment("Mars comes after earth", self.martin)

        # Martin and Mark should see both the comments
        for user in [self.mark, self.martin]:
            self.assertEqual(len(Comment.objects.best_ones_first(post, user)), 2)
        
        # Non-martians shouldn't see any comments
        for user in [self.ramesh, self.amit, self.swetha]:
            with self.assertRaises(PermissionDenied):
                Comment.objects.best_ones_first(post, user)
    
    def test_only_team_members_can_vote(self):
        post = self.new_discussion(self.martin, "Post related to Mars", self.martians)
        comment = post.add_comment("Mars is red", self.mark)

        for user in [self.mark, self.martin]:
            post.upvote(user)
            post.undo_vote(user)
            post.downvote(user)
            comment.upvote(user)
            comment.downvote(user)
            comment.downvote(user)
        
        for user in [self.ramesh, self.amit, self.swetha]:
            with self.assertRaises(PermissionDenied):
                post.upvote(user)
            with self.assertRaises(PermissionDenied):
                post.undo_vote(user)
            with self.assertRaises(PermissionDenied):
                post.downvote(user)
            with self.assertRaises(PermissionDenied):
                comment.upvote(user)
            with self.assertRaises(PermissionDenied):
                comment.downvote(user)
            with self.assertRaises(PermissionDenied):
                comment.downvote(user)
    
    def test_only_author_can_edit(self):
        post_by_martin = self.new_discussion(self.martin, "Post related to Mars", self.martians)
        comment_by_mark = post_by_martin.add_comment("Mars is red", self.mark)

        post_by_martin.edit_post("Edited title", "Edited body", self.martin)
        for user in [self.mark, self.ramesh, self.amit, self.swetha]:
            with self.assertRaises(PermissionDenied):
                post_by_martin.edit_post("Edited title #2", "Edited body #2", user)
        
        comment_by_mark.edit_comment("Edited Comment", self.mark)
        for user in [self.martin, self.ramesh, self.amit, self.swetha]:
            with self.assertRaises(PermissionDenied):
                comment_by_mark.edit_comment("Edited Comment #2", user)
        
