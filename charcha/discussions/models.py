from collections import defaultdict

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.urls import reverse
from charcha.teams.bot import notify_space
from charcha.teams.models import Team
from bleach.sanitizer import Cleaner
from django.core.exceptions import PermissionDenied
from django.db import transaction

import re

cleaner = Cleaner(
    tags=['a', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'strong', 'ul',
        'h1', 'h2', 'h3', 'p', 'br', 'sub', 'sup', 'hr',
        'div', 'figure', 'figcaption', 'img', 'span', 'del', 'pre', 'img',
    ],
    attributes={
            "a": ("href", "name", "target", "title", "id", "rel", "data-trix-attachment",),
            "figure": ("class", "data-trix-attachment", "data-trix-content-type", "data-trix-attributes"),
            "figcaption": ("class", ),
            "img": ("width", "height", 'src'),
            "span": ("class", ),
        },
    strip=False
)
regex = re.compile(r"<h[1-6]>([^<^>]+)</h[1-6]>")

def clean_and_normalize_html(html):
    html = cleaner.clean(html)
    return re.sub(regex, r"<h3>\1</h3>", html)


# TODO: Read this from settings 
SERVER_URL = "https://charcha.hashedin.com"

UPVOTE = 1
DOWNVOTE = 2
FLAG = 3

def save_avatar(backend, strategy, details, response, user=None, *args, **kwargs):
    'Called as part of social authentication login process'
    if backend.name == 'google-oauth2':
        url = response.get('picture', None)
        if not url:
            image = response.get('image', {})
            url = image.get('url', None)
        user.avatar = url
        user.save()

def associate_gchat_user(backend, strategy, details, response, user=None, *args, **kwargs):
    '''Called as part of social authentication login process
        We try to match the user logging in to an existing gchat user
    '''
    class CharchaRollback(Exception):
        'An exception to indicate the transaction should be rollbacked'
        pass

    from django.db import connection
    with connection.cursor() as cursor:
        try:
            with transaction.atomic():
                cursor.execute("""
                    WITH user_with_merge_key as (
                        SELECT u.id as id, u.email, replace(substring(u.email, 0, position('@' in u.email)), '.', '') as merge_key 
                        FROM users u JOIN social_auth_usersocialauth sa on u.id = sa.user_id
                        WHERE u.email != ''
                    )
                    UPDATE gchat_users g
                    SET user_id = um.id
                    FROM user_with_merge_key um 
                    WHERE replace(lower(g.display_name), ' ', '') = um.merge_key
                    AND g.user_id is null AND um.id = %s;
                """, [user.id])
                if cursor.rowcount > 1:
                    # Because we are matching on name, it is possible different users have the same name
                    # So if we update multiple records in gchat_users table, something is wrong
                    # In that case, we raise an exception so django does a rollback
                    raise CharchaRollback()
        except CharchaRollback:
            # We only raised the exception to trigger django's rollback mechanism
            pass

def update_gchat_space(email, space_id):
    try:
        user = User.objects.get(email=email)
        user.gchat_space = space_id
        user.save()
        return True
    except User.DoesNotExist as e:
        return False

class PostWithCustomGet:
    def get(*args, **kwargs):
        return Post.objects.get(*args, **kwargs)

class CommentWithCustomGet:
    def get(*args, **kwargs):
        return Comment.objects.get(*args, **kwargs)

class User(AbstractUser):
    """Our custom user model with a score"""
    class Meta:
        db_table = "users"

    score = models.IntegerField(default=0)
    avatar = models.URLField(max_length=1000, default=None, null=True)
    
    # If the user has added charcha bot, then this field stores the unique space id
    gchat_space = models.CharField(max_length=50, default=None, null=True)


class Vote(models.Model):
    class Meta:
        db_table = "votes"
        index_together = [
            ["content_type", "object_id"],
        ]

    # The following 3 fields represent the Comment or Post
    # on which a vote has been cast
    # See Generic Relations in Django's documentation
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    type_of_vote = models.IntegerField(
        choices = (
            (UPVOTE, 'Upvote'),
            (DOWNVOTE, 'Downvote'),
            (FLAG, 'Flag'),
        ))
    submission_time = models.DateTimeField(auto_now_add=True)

class VotableManager(models.Manager):
    def get(self, *args, **kwargs):
        if 'requester' not in kwargs:
            raise PermissionDenied("requester not provided")
        requester = kwargs.pop('requester')
        obj = super().get(*args, **kwargs)
        obj.check_view_permission(requester)
        return obj

class Votable(models.Model):
    """ An object on which people would want to vote
        Post and Comment are concrete classes
    """
    class Meta:
        abstract = True

    votes = GenericRelation(Vote)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    # denormalization to save database queries
    # flags = count of votes of type "Flag"
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    flags = models.IntegerField(default=0)

    def upvote(self, user):
        self.check_view_permission(user)
        self._vote(user, UPVOTE)

    def downvote(self, user):
        self.check_view_permission(user)
        self._vote(user, DOWNVOTE)

    def flag(self, user):
        self.check_view_permission(user)
        self._vote(user, FLAG)

    def unflag(self, user):
        self.check_view_permission(user)
        raise Exception("not yet implemented")

    def undo_vote(self, user):
        self.check_view_permission(user)
        content_type = ContentType.objects.get_for_model(self)
        votes = Vote.objects.filter(
            content_type=content_type.id,
            object_id=self.id, type_of_vote__in=(UPVOTE, DOWNVOTE),
            voter=user)

        upvotes = 0
        downvotes = 0
        for v in votes:
            if v.type_of_vote == UPVOTE:
                upvotes = upvotes + 1
            elif v.type_of_vote == DOWNVOTE:
                downvotes = downvotes + 1
            else:
                raise Exception("Invalid state, logic bug in undo_vote")
            v.delete()

        self.upvotes = F('upvotes') - upvotes
        self.downvotes = F('downvotes') - downvotes
        self.save(update_fields=["upvotes", "downvotes"])

        # Increment/Decrement the score of author
        self.author.score = F('score') - upvotes + downvotes
        self.author.save(update_fields=["score"])

    def _vote(self, user, type_of_vote):
        content_type = ContentType.objects.get_for_model(self)
        if self._already_voted(user, content_type, type_of_vote):
            return
        if self._voting_for_myself(user):
            return

        # First, save the vote
        vote = Vote(content_object=self, 
                    voter=user,
                    type_of_vote=type_of_vote)
        vote.save()

        score_delta = 0
        # Next, update our denormalized columns
        if type_of_vote == FLAG:
            self.flags = F('flags') + 1
        elif type_of_vote == UPVOTE:
            self.upvotes = F('upvotes') + 1
            score_delta = 1
        elif type_of_vote == DOWNVOTE:
            self.downvotes = F('downvotes') + 1
            score_delta = -1
        else:
            raise Exception("Invalid type of vote " + type_of_vote)
        self.save(update_fields=["upvotes", "downvotes", "flags"])

        # Increment/Decrement the score of author
        self.author.score = F('score') + score_delta
        self.author.save(update_fields=["score"])

    def _voting_for_myself(self, user):
        return self.author.id == user.id

    def _already_voted(self, user, content_type, type_of_vote):
        return Vote.objects.filter(
            content_type=content_type.id,
            object_id=self.id,\
            voter=user, type_of_vote=type_of_vote)\
            .exists()

class TeamPosts(models.Model):
    'Through model to maintain many-to-many relationship between Post and Team'
    class Meta:
        db_table = "team_posts"
        indexes = [
            models.Index(fields=["team", "post"]),
            models.Index(fields=["post", "team"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=['team', 'post',], name="team_posts_unique_constraint")
        ]    
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    post = models.ForeignKey('Post', on_delete=models.PROTECT)

class PostsManager(VotableManager):
    def new_post(self, author, post, teams):
        if not Team.objects.belongs_to_all_teams(author, teams):
            raise PermissionDenied("User " + str(author.id)  + " does not have access to one or more teams \
                under which this post is being created")

        post.author = author
        post.save()
        for team in teams:
            TeamPosts(post=post, team=team).save()
        post.on_new_post()
        return post

    def get_post_with_my_votes(self, post_id, user):
        post = Post.objects\
            .annotate(score=F('upvotes') - F('downvotes'))\
            .select_related("author").get(pk=post_id)
        post.check_view_permission(user)

        if user and user.is_authenticated:
            content_type = ContentType.objects.get_for_model(Post)
            post_votes = Vote.objects.filter(
                content_type=content_type.id,
                object_id=post_id, type_of_vote__in=(UPVOTE, DOWNVOTE),
                voter=user)

            for v in post_votes:
                if v.type_of_vote == UPVOTE:
                    post.is_upvoted = True
                elif v.type_of_vote == DOWNVOTE:
                    post.is_downvoted = True
        return post

    def recent_posts_with_my_votes(self, user):
        posts = Post.objects.raw("""
            WITH post_teams as (
                SELECT tp.post_id as post_id, json_agg(t.*) as teams
                FROM team_posts tp JOIN (SELECT id, name FROM teams) t on tp.team_id = t.id
                GROUP BY tp.post_id
            )
            SELECT p.id, p.title, 
                p.upvotes, p.downvotes, p.flags,
                (p.upvotes - p.downvotes) as score, 
                p.title, p.html, p.submission_time, p.num_comments, 
                json_build_object('id', a.id, 'username', a.username, 'avatar', a.avatar) as _author,
                pt.teams as teamsobj
            FROM posts p JOIN users a on p.author_id = a.id
                JOIN post_teams pt on p.id = pt.post_id
            WHERE EXISTS (
                SELECT 'x' FROM team_posts tp JOIN team_members tm ON tp.team_id = tm.team_id
                WHERE tm.gchat_user_id = (select g.id from gchat_users g where g.user_id = %s) 
                and tp.post_id = p.id
            )
            ORDER BY p.submission_time DESC
            LIMIT 100;
        """, [user.id])

        # Our query returns author and team objects as dictionary
        # But Django expects them to proper User and Team objects
        # So we do the conversion over here 
        for p in posts:
            p.author = User(**p._author)
            
        posts = self._append_votes_by_user(posts, user)
        return posts

    def _append_votes_by_user(self, posts, user):
        # Returns a dictionary
        # key = postid
        # value = set of votes cast by this user
        # for example set('downvote', 'flag')
        post_ids = [p.id for p in posts]
        post_type = ContentType.objects.get_for_model(Post)
        objects = Vote.objects.\
                    only('object_id', 'type_of_vote').\
                    filter(content_type=post_type.id,
                        object_id__in=post_ids,
                        voter=user)

        votes_by_post = defaultdict(set)
        for obj in objects:
            votes_by_post[obj.object_id].add(obj.type_of_vote)

        for post in posts:
            post.is_upvoted = False
            post.is_downvoted = False
            if UPVOTE in votes_by_post[post.id]:
                post.is_upvoted = True
            elif DOWNVOTE in votes_by_post[post.id]:
                post.is_downvoted = True
            elif FLAG in votes_by_post[post.id]:
                post.is_flagged = True
            
        return posts

    def vote_type_to_string(self, vote_type):
        mapping = {
            UPVOTE: "upvote",
            DOWNVOTE: "downvote",
            FLAG: "flag"
        }
        return mapping[vote_type]

class Post(Votable):
    class Meta:
        db_table = "posts"
        index_together = [
            ["submission_time",],
        ]
    objects = PostsManager()
    title = models.CharField(max_length=120)
    url = models.URLField(blank=True)
    html = models.TextField(blank=True, max_length=8192)
    submission_time = models.DateTimeField(auto_now_add=True)
    teams = models.ManyToManyField(Team, through=TeamPosts, related_name="posts")
    num_comments = models.IntegerField(default=0)

    def can_view(self, user):
        'User can view the post if he belongs to any team(s) the post is a part of'
        result = Post.objects.raw("""
            SELECT p.id FROM posts p
            WHERE EXISTS (
                SELECT 'x' FROM team_posts tp JOIN team_members tm on tp.team_id = tm.team_id
                    WHERE tp.post_id = p.id AND tm.gchat_user_id = (
                        SELECT id from gchat_users where user_id = %s
                    )
            )
            AND p.id = %s;
        """, [user.id, self.id])
        if result:
            return True
        else:
            return False

    def can_edit(self, user):
        return self.author.id == user.id
    
    def check_view_permission(self, user):
        if not self.can_view(user):
            raise PermissionDenied("View denied on post " + str(self.id) + " to user " + str(user.id))
    
    def check_edit_permission(self, user):
        if not self.can_edit(user):
            raise PermissionDenied("Edit denied on post " + str(self.id) + " to user " + str(user.id))

    def save(self, *args, **kwargs):
        self.html = clean_and_normalize_html(self.html)
        is_create = False
        if not self.pk:
            is_create = True
        super().save(*args, **kwargs)  # Call the "real" save() method.

    def get_absolute_url(self):
        return "/discuss/%i/" % self.id

    def edit_post(self, title, html, author):
        self.check_edit_permission(author)
        self.title = title
        self.html = html
        self.save()

    def add_comment(self, html, author):
        # You can add a comment as long as you have view permission on the post
        self.check_view_permission(author)
        comment = Comment()
        comment.html = html
        comment.post = self
        comment.wbs = _find_next_wbs(self)
        comment.author = author
        comment.save()

        self.num_comments = F('num_comments') + 1
        self.save(update_fields=["num_comments"])
        comment.on_new_comment()
        return comment

    def watchers(self):
        post_type = ContentType.objects.get_for_model(Post)
        
        # A post watcher is
        # 1. The author of the post
        # 2. Anyone who has commented on the post
        # 3. Anyone who has voted on the post
        return User.objects.raw("""
                WITH post_participants as (
                    SELECT p.id as postid, p.author_id as userid FROM posts p
                    UNION ALL
                    SELECT c.post_id as postid, c.author_id as userid FROM comments c
                    UNION ALL
                    SELECT v.object_id as postid, v.voter_id as userid FROM votes v
                    WHERE v.content_type_id = %s
                ) 
                SELECT DISTINCT u.id, u.username, u.gchat_space
                FROM users u JOIN post_participants pp on u.id = pp.userid
                WHERE u.gchat_space is not NULL and u.gchat_space != ''
                AND pp.postid = %s
            """, [post_type.id, self.id])

    def on_new_post(self):
        event = {
            "heading": "New Discussion",
            "sub_heading": "by " + self.author.username,
            "image": self.author.avatar,
            "line1": self.title,
            "line2": self.html[:150],
            "link": SERVER_URL + reverse("discussion", args=[self.id]),
            "link_title": "View Discussion"
        }
        for team in self.teams.all():
            space_id = team.gchat_space
            notify_space(space_id, event)

    def __str__(self):
        return self.title

class CommentsManager(VotableManager):
    def best_ones_first(self, post, user):
        post.check_view_permission(user)
        comment_type = ContentType.objects.get_for_model(Comment)
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.id, c.html, u.id, u.username, c.submission_time,
                c.wbs, length(c.wbs)/5 as indent, 
                c.upvotes, c.downvotes, c.flags,
                c.upvotes - c.downvotes as score,
                up.is_upvoted, down.is_downvoted
                FROM comments c 
                INNER JOIN users u on c.author_id = u.id
                LEFT OUTER JOIN (
                    SELECT 1 as is_upvoted, v1.object_id as comment_id
                    FROM votes v1
                    WHERE v1.content_type_id = %s
                    AND type_of_vote = 1
                    AND v1.voter_id = %s
                ) up on c.id = up.comment_id
                LEFT OUTER JOIN (
                    SELECT 1 as is_downvoted, v2.object_id as comment_id
                    FROM votes v2
                    WHERE v2.content_type_id = %s
                    AND type_of_vote = 2
                    AND v2.voter_id = %s
                ) down on c.id = down.comment_id
                WHERE c.post_id = %s
                ORDER BY c.wbs
            """, [comment_type.id, user.id, 
                    comment_type.id, user.id, 
                    post.id])
            
            comments = []
            for row in cursor.fetchall():
                comment = self.model(
                        id = row[0], html = row[1], 
                        submission_time = row[4],
                        wbs = row[5],
                        upvotes = row[7], downvotes=row[8],
                        flags = row[9]
                    )
                author = User(id=row[2], username=row[3])
                comment.author = author
                comment.indent = row[6]
                comment.score = row[10]
                comment.is_upvoted = True if row[11] else False
                comment.is_downvoted = True if row[12] else False
                comments.append(comment)

            return comments

class Comment(Votable):
    class Meta:
        db_table = "comments"
        unique_together = [
            ["post", "wbs"],
        ]
    objects = CommentsManager()

    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name="comments")
    parent_comment = models.ForeignKey(
        'self', 
        null=True, blank=True,
        on_delete=models.PROTECT)
    html = models.TextField(max_length=8192)
    submission_time = models.DateTimeField(auto_now_add=True)

    # wbs helps us to track the comments as a tree
    # Format is .0000.0000.0000.0000.0000.0000
    # This means that:
    # 1. We only allow 9999 comments at each level
    # 2. We allow threaded comments upto 12 levels
    wbs = models.CharField(max_length=60)

    def can_view(self, user):
        'User can view the comment if he can view the parent post'
        return self.post.can_view(user)

    def can_edit(self, user):
        return self.author.id == user.id
    
    def check_view_permission(self, user):
        if not self.can_view(user):
            raise PermissionDenied("View denied on comment " + str(self.id) + " to user " + str(user.id))
    
    def check_edit_permission(self, user):
        if not self.can_edit(user):
            raise PermissionDenied("Edit denied on comment " + str(self.id) + " to user " + str(user.id))
    
    def save(self, *args, **kwargs):
        self.html = clean_and_normalize_html(self.html)
        super().save(*args, **kwargs)

    def reply(self, html, author):
        # You can reply as long as you have view permission on the post
        self.post.check_view_permission(author)
        comment = Comment()
        comment.html = html
        comment.post = self.post
        comment.parent_comment = self
        comment.wbs = _find_next_wbs(self.post, parent_wbs=self.wbs)
        comment.author = author
        comment.save()

        comment.post.num_comments = F('num_comments') + 1
        comment.post.save()
        comment.on_new_comment()
        return comment

    def edit_comment(self, html, author):
        self.check_edit_permission(author)
        self.html = html
        self.save()

    def on_new_comment(self):
        event = {
            "heading": "New Comment",
            "sub_heading": "by " + self.author.username,
            "image": self.author.avatar,
            "line1": self.post.title,
            "line2": self.html[:150],
            "link": SERVER_URL + reverse("discussion", args=[self.post.id]) + "#comment-" + str(self.id),
            "link_title": "View Comment"
        }
        
        for watcher in self.post.watchers():
            if watcher.username == self.author.username:
                continue
            notify_space(watcher.gchat_space, event)

    def __str__(self):
        return self.html

def _find_next_wbs(post, parent_wbs=None):
    if not parent_wbs:
        parent_wbs = ""

    from django.db import connection
    with connection.cursor() as c:
        c.execute("""
            SELECT max(wbs) as wbs from comments 
            WHERE post_id = %s and wbs like %s
            and length(wbs) = %s
            ORDER BY wbs desc
            limit 1
            """,
            [post.id, parent_wbs + ".%", len(parent_wbs) + 5]
        )
        try:
            row = c.fetchone()
            max_wbs = row[0]
        except:
            max_wbs = None

    if not max_wbs:
        return "%s.%s" % (parent_wbs, "0000")
    else:
        first_wbs = max_wbs[:-4]
        last_wbs = max_wbs.split(".")[-1]
        next_wbs = int(last_wbs) + 1
        return first_wbs + '{0:04d}'.format(next_wbs)

class Favourite(models.Model):
    class Meta:
        # Yes, I use Queen's english
        db_table = "favourites"

    # The following 3 fields represent the Comment or Post
    # which has been favourited
    # See Generic Relations in Django's documentation
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    favourited_on = models.DateTimeField(auto_now_add=True)
    deleted_on = models.DateTimeField(blank=True, null=True)
