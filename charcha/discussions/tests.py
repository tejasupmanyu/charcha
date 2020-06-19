from contextlib import contextmanager
from collections import defaultdict
from django.test import TestCase
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from .models import Post, Vote, Comment, User
from . import models

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

class DiscussionTests(TestCase):
    def setUp(self):
        self._create_users()
        
    def _create_users(self):
        self.ramesh = User.objects.create_user(
            username="ramesh", password="top_secret", gchat_space="ramesh")
        self.amit = User.objects.create_user(
            username="amit", password="top_secret", gchat_space="amit")
        self.swetha = User.objects.create_user(
            username="swetha", password="top_secret", gchat_space="swetha")
        self.anamika = AnonymousUser()

    def new_discussion(self, user, title):
        post = Post(title=title,
            html="Does not matter",
            author=user)
        post.save()
        return post
    
    def test_I_cant_vote_for_me(self):
        post = self.new_discussion(self.ramesh, "Ramesh's Biography")
        self.assertEquals(post.upvotes, 0)
        post.upvote(self.ramesh)
        post = Post.objects.get(pk=post.id)
        self.assertEquals(post.upvotes, 0)

    def test_double_voting(self):
        post = self.new_discussion(self.ramesh, "Ramesh's Biography")
        self.assertEquals(post.upvotes, 0)
        post.upvote(self.amit)
        post = Post.objects.get(pk=post.id)
        self.assertEquals(post.upvotes, 1)
        post.upvote(self.amit)
        post = Post.objects.get(pk=post.id)
        self.assertEquals(post.upvotes, 1)

    def test_voting_on_home_page(self):
        # Ramesh starts a discussion
        post = self.new_discussion(self.ramesh, "Ramesh's Biography")

        # Then Anamika views home page
        posts = Post.objects.recent_posts_with_my_votes()
        self.assertEquals(len(posts), 1)
        post = posts.first()
        self.assertEquals(post.upvotes, 0)
        self.assertEquals(post.downvotes, 0)

        # Amit upvotes the post
        post.upvote(self.amit)

        # Home page as seen by Amit
        post = Post.objects.recent_posts_with_my_votes(self.amit).first()
        self.assertTrue(post.is_upvoted)
        self.assertFalse(post.is_downvoted)
        self.assertEquals(post.upvotes, 1)
        self.assertEquals(post.downvotes, 0)

        # Swetha downvotes
        post.downvote(self.swetha)

        # Home page as seen by Swetha
        post = Post.objects.recent_posts_with_my_votes(self.swetha).first()
        self.assertFalse(post.is_upvoted)
        self.assertTrue(post.is_downvoted)
        self.assertEquals(post.upvotes, 1)
        self.assertEquals(post.downvotes, 1)
        
        # Amit undo's his vote
        post.undo_vote(self.amit)

        # Home page as seen by Amit
        post = Post.objects.recent_posts_with_my_votes(self.amit).first()
        self.assertFalse(post.is_upvoted)
        self.assertFalse(post.is_downvoted)
        self.assertEquals(post.upvotes, 0)
        self.assertEquals(post.downvotes, 1)

    def test_comments_ordering(self):
        _c1 = "See my Biography!"
        _c2 = "Dude, this is terrible!"
        _c3 = "Why write your biography when you haven't achieved a thing!"
        _c4 = "Seriously, that's all you have to say?"

        post = self.new_discussion(self.ramesh, "Ramesh's Biography")
        self.assertEquals(post.num_comments, 0)

        rameshs_comment = post.add_comment(_c1, self.ramesh)
        amits_comment = rameshs_comment.reply(_c2, self.amit)
        swethas_comment = rameshs_comment.reply(_c3, self.swetha)
        rameshs_response = amits_comment.reply(_c4, self.ramesh)

        comments = [c.html for c in 
                    Comment.objects.best_ones_first(post.id, self.ramesh.id)]

        self.assertEquals(comments, [_c1, _c2, _c4, _c3])

        # check if num_comments in post object is updated
        post = Post.objects.get(pk=post.id)
        self.assertEquals(post.num_comments, 4)

    def test_cannot_edit_someone_elses_comment(self):
        post = self.new_discussion(self.ramesh, "Can I edit someone else's comment?")
        post.edit_post("this is the new title", "this is the new body", self.ramesh)
        with self.assertRaises(PermissionDenied):
            post.edit_post("Amit trying to edit Ramesh's post", "this is the new body", self.amit)

        # Reload post object to confirm it got saved
        post = Post.objects.get(id=post.id)
        self.assertEqual(post.title, "this is the new title")
        self.assertEqual(post.html, "this is the new body")

        rameshs_comment = post.add_comment("I think it should not be possible", self.ramesh)
        rameshs_comment.edit_comment("EDIT; I should be able to edit my own comment", self.ramesh)
        with self.assertRaises(PermissionDenied):
            rameshs_comment.edit_comment("Amit trying to edit Ramesh's comment", self.amit)
        
        # Reload comment object to confirm it got saved
        rameshs_comment = Comment.objects.get(id=rameshs_comment.id)
        self.assertEqual(rameshs_comment.html, "EDIT; I should be able to edit my own comment")

    def test_notifications(self):
        with record_notifications() as notifications:
            # Expect a single notification to broadcast when a new post is created
            post = self.new_discussion(self.ramesh, "Ramesh's Biography")
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
