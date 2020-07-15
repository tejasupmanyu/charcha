from collections import defaultdict
import re

from django.utils import timezone
from django.db.utils import IntegrityError
from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import F, Q, Prefetch, OuterRef, Subquery
from django.urls import reverse
from charcha.teams.bot import notify_space
from bleach.sanitizer import Cleaner
from django.core.exceptions import PermissionDenied
from django.db import transaction

import re

comment_cleaner = Cleaner(
    tags=['a', 'b', 'em', 'i', 'strong',
    ],
    attributes={
        "a": ("href", "name", "target", "title", "id", "rel", "data-trix-attachment",),
    },
    strip=True
)
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
    from django.db import connection
    with connection.cursor() as cursor:
        try:
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
        except IntegrityError:
            # Because we are matching on name, it is possible different users have the same name
            # So if we update multiple records in gchat_users table, something is wrong
            # In such a case, we simply don't update the database, but let the user login
            pass

def update_gchat_space(email, space_id):
    try:
        user = User.objects.get(email=email)
        user.gchat_space = space_id
        user.save()
        return True
    except User.DoesNotExist as e:
        return False

class User(AbstractUser):
    """Our custom user model with a score"""
    class Meta:
        db_table = "users"

    score = models.IntegerField(default=0)
    avatar = models.URLField(max_length=1000, default=None, null=True)
    
    # If the user has added charcha bot, then this field stores the unique space id
    gchat_space = models.CharField(max_length=50, default=None, null=True)
    tzname = models.CharField(max_length=50, default='Asia/Kolkata')

class GchatUser(models.Model):
    '''
    A user imported from google chat
    
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
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, default=None, related_name="gchat_user")
    # Maps to name in google hangout's model
    # See https://developers.google.com/hangouts/chat/reference/rest/v1/User
    key = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)

class GchatSpace(models.Model):
    class Meta:
        db_table = "gchat_spaces"
    name = models.CharField(max_length=100)
    space = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class GroupsManager(models.Manager):
    def for_user(self, user):
        return Group.objects.filter(Q(members=user) | Q(group_type=Group.OPEN))

class Group(models.Model):
    OPEN = 0
    CLOSED = 1
    SECRET = 2

    class Meta:
        db_table = "groups"
    
    objects = GroupsManager()
    name = models.CharField(max_length=30, help_text="Name of the group")
    group_type = models.IntegerField(
        choices = (
            (OPEN, 'Open'),
            (CLOSED, 'Closed'),
            (SECRET, 'Secret'),
        ),
        help_text="Closed groups can be seen on the listing page and request an invitation, but only members can see the posts. Secret groups don't show up on the listing page.")
    is_deleted = models.BooleanField(default=False)
    purpose = models.CharField(max_length=200, help_text="A 1 or 2 sentence explaining the purpose of this group")
    description = models.TextField(max_length=4096, help_text="A larger description that can contain links, charter or any other text to better describe the group")
    members = models.ManyToManyField(User, verbose_name="Members of this group", through='GroupMember', related_name="mygroups", help_text="Members of this group")
    gchat_spaces = models.ManyToManyField(GchatSpace, verbose_name="Google chat rooms associated with this group", through='GroupGchatSpace', help_text="Associate this group to one or more gchat rooms. This has two purposes - 1) to automatically import members from the gchat room, and 2) to notify the gchat room when a new post is added")
    emails = ArrayField(models.EmailField(), size=8, help_text="Mailing list address for this group")

    @classmethod
    def get(klass, id, user):
        # Alternative get method to ensure user only sees Posts they have access to
        return klass.objects.get(Q(members=user) | Q(group_type=Group.OPEN), pk=id)

    def _slugify(self, title):
        slug = title.lower()
        slug = re.sub("[^0-9a-zA-Z-]+", " ", slug)
        slug = slug.strip()
        slug = re.sub("\s+", "-", slug)
        return slug

    def new_post(self, author, post):
        post.author = author
        post.slug = self._slugify(post.title)
        post.group = self

        now = timezone.now()
        post.last_modified = now
        post.save()

        self._on_new_post(post)
        return post

    def _on_new_post(self, post):
        event = {
            "heading": "New Discussion",
            "sub_heading": "by " + post.author.username,
            "image": post.author.avatar,
            "line1": post.title,
            "line2": post.html[:150],
            "link": SERVER_URL + reverse("post", args=[post.id, post.slug]),
            "link_title": "View Discussion"
        }
        for gchat_space in self.gchat_spaces.all():
            space_id = gchat_space.space
            notify_space(space_id, event)

    def __str__(self):
        return self.name
    
class GroupGchatSpace(models.Model):
    class Meta:
        db_table = "group_gchat_spaces"
        verbose_name = "Chat Room"
    
    group = models.ForeignKey(Group, on_delete=models.PROTECT)
    gchat_space = models.ForeignKey(GchatSpace, verbose_name="Room Name", on_delete=models.PROTECT)
    notify = models.BooleanField(default=True, help_text="Notify the chat room whenever a new post is created in this charcha group")
    sync_members = models.BooleanField(default=True, help_text="Automatically sync chat room members with this charcha group")
    
class Role(models.Model):
    'Roles are - administrator, moderator, member, guest'
    class Meta:
        db_table = "roles"
    name = models.CharField(max_length=20)
    permissions = models.ManyToManyField('Permission', through='RolePermission', related_name="roles")
    
    def permissons_csv(self):
        'Only for display purposes in django admin'
        return ", ".join([p.name for p in self.permissions.all()])

    def __str__(self):
        return self.name

class Permission(models.Model):
    class Meta:
        db_table = 'permissions'
    name = models.CharField(max_length=20)
    description = models.CharField(max_length=200)

    def __str__(self):
        return self.name

class RolePermission(models.Model):
    class Meta:
        db_table = "role_permissions"
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT)

class GroupMember(models.Model):
    class Meta:
        db_table = 'group_members'
    group = models.ForeignKey(Group, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

class PostsManager(models.Manager):
    def for_user(self, user):
        return Post.objects.filter(Q(group__members=user) | Q(group__group_type=Group.OPEN))

    def get_post_details(self, post_id, user):
        # Get the post and all child posts in a single query
        # The first object is the parent post
        # Subsequent objects are child posts, sorted by submission_time in ascending order
        post_and_child_posts = list(Post.objects\
            .select_related("author")\
            .select_related("group")\
            .prefetch_related(Prefetch("comments", queryset=Comment.objects.select_related("author")))\
            .annotate(lastseen_timestamp=Subquery(LastSeenOnPost.objects.filter(post=OuterRef('pk'), user=user).only('seen').values('seen')[:1]))\
            .filter(
                Q(id = post_id) | Q(parent_post__id = post_id)
            )\
            .order_by(F('parent_post').desc(nulls_first=True), "submission_time"))
        
        parent_post = post_and_child_posts[0]
        child_posts = post_and_child_posts[1:]
        
        for post in post_and_child_posts:
            if post.lastseen_timestamp is None:
                post.is_read = False
                post.has_unread_children = True
                continue
            
            if post.last_modified > post.lastseen_timestamp:
                post.is_read = False
            else:
                post.is_read = True
            
            if post.last_activity > post.lastseen_timestamp:
                post.has_unread_children = True
            else:
                post.has_unread_children = False
            
            for comment in post.comments.all():
                if not post.lastseen_timestamp:
                    comment.is_read = False
                    post.has_unread_children = True
                elif comment.submission_time > post.lastseen_timestamp:
                    comment.is_read = False
                    post.has_unread_children = True
                else:
                    comment.is_read = True
        
        for post in child_posts:
            if not post.is_read or post.has_unread_children:
                parent_post.has_unread_children = True
                print('set has_unread_children on parent_post' )
        
        return (parent_post, child_posts)

    def recent_posts(self, user, group=None, sort_by='recentposts'):
        posts = Post.objects\
            .select_related('author')\
            .select_related('group')\
            .annotate(lastseen_timestamp=Subquery(LastSeenOnPost.objects.filter(post=OuterRef('pk'), user=user).only('seen').values('seen')[:1]))\
            .filter(
                Q(group__members=user) | Q(group__group_type=Group.OPEN), 
                parent_post=None
            )
        if group:
            posts = posts.filter(group=group)
        
        if sort_by == 'recentposts':
            posts = posts.order_by("-submission_time")
        else:
            posts = posts.order_by("-last_activity")
        
        for post in posts:
            if post.lastseen_timestamp is None:
                post.is_read = False
            elif post.last_activity > post.lastseen_timestamp:
                post.is_read = False
            else:
                post.is_read = True
        return posts

    def vote_type_to_string(self, vote_type):
        mapping = {
            UPVOTE: "upvote",
            DOWNVOTE: "downvote",
            FLAG: "flag"
        }
        return mapping[vote_type]

class Post(models.Model):
    DISCUSSION = 0
    QUESTION = 1
    FEEDBACK = 2
    ANNOUNCEMENT = 3
    RESPONSE = 16
    ANSWER = 17
    _POST_TYPES = {
        "discussion": DISCUSSION,
        "announcement": ANNOUNCEMENT,
        "question": QUESTION,
        "feedback": FEEDBACK,
        "response": RESPONSE,
        "answer": ANSWER
    }
    
    @staticmethod
    def get_top_level_post_types():
        return [POST.DISCUSSION, Post.QUESTION, Post.FEEDBACK, Post.ANNOUNCEMENT]

    @staticmethod
    def get_post_type(post_type_str):
        post_type = Post._POST_TYPES.get(post_type_str.lower(), None)
        if post_type is None:
            raise Exception("Invalid Post Type - " + str(post_type_str))
        return post_type

    @property
    def post_type_for_display(self):
        for post_type, _id in Post._POST_TYPES.items():
            if self.post_type == _id:
                return post_type
        return None

    class Meta:
        db_table = "posts"
        index_together = [
            ["submission_time",],
        ]
    
    objects = PostsManager()
    group = models.ForeignKey(Group, on_delete=models.PROTECT)
    title = models.CharField(max_length=120, blank=True)
    slug = models.CharField(max_length=120, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submission_time = models.DateTimeField(auto_now_add=True)

    # When this post was last modified
    last_modified = models.DateTimeField(auto_now=True)

    # activity includes new sub-post, new comment, or edits to sub-post / comment
    last_activity = models.DateTimeField(auto_now=True)

    parent_post = models.ForeignKey(
        'self', 
        null=True,
        blank=True,
        on_delete=models.PROTECT, default=None)
    post_type = models.IntegerField(
        choices = (
            (DISCUSSION, 'Discussion'),
            (QUESTION, 'Question'),
            (FEEDBACK, 'Feedback'),
            (ANNOUNCEMENT, 'Announcement'),
            (RESPONSE, 'Response'),
            (ANSWER, 'Answer'),
        ),
        default=DISCUSSION)
    html = models.TextField(blank=True, max_length=8192)
    is_deleted = models.BooleanField(default=False)
    sticky = models.BooleanField(default=False)
    accepted_answer = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    num_comments = models.IntegerField(default=0)
    score = models.IntegerField(default=0)
    last_seen = models.ManyToManyField(User, through='LastSeenOnPost', related_name='last_seen')

    def new_child_post(self, author, post):
        post.author = author
        post.parent_post = self
        post.group = self.group

        now = timezone.now()
        post.last_modified = now
        post.save()

        self.last_activity = now
        self.save(update_fields=["last_activity"])

        return post

    def upvote(self, user):
        self.check_view_permission(user)
        self._vote(user, UPVOTE)

    def downvote(self, user):
        self.check_view_permission(user)
        self._vote(user, DOWNVOTE)

    def _undo_vote(self, user):
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
                raise Exception("Invalid state, logic bug in _undo_vote")
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
            self._undo_vote(user)
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

    def save(self, *args, **kwargs):
        self.html = clean_and_normalize_html(self.html)
        is_create = False
        if not self.pk:
            is_create = True
        super().save(*args, **kwargs)  # Call the "real" save() method.

    def get_absolute_url(self):
        return "/discuss/%i/" % self.id

    def edit_post(self, title, html, author):
        self.title = title
        self.html = html
        now = timezone.now()
        self.last_modified = now
        self.save()

        if self.parent_post:
            self.parent_post.last_activity = now
            self.parent_post.save(update_fields=["last_activity"])

    def add_comment(self, html, author):
        now = timezone.now()

        comment = Comment()
        comment.html = html
        comment.post = self
        comment.author = author
        comment.last_modified = now
        comment.save()
        
        self.last_activity = now
        self.num_comments = F('num_comments') + 1
        self.save(update_fields=["num_comments", "last_activity"])

        if self.parent_post:
            self.parent_post.last_activity = now
            self.parent_post.save(update_fields=["last_activity"])

        return comment

    def watchers(self):
        return []

    def __str__(self):
        if self.title:
            return self.title
        elif self.html:
            return self.html[:120]
        else:
            return "Post id = " + str(self.id)

class Reaction(models.Model):
    class Meta:
        db_table = "reactions"
        index_together = [
            ["post", "author"],
        ]

    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name='reactions')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    # A reaction is a unicode emoji
    reaction = models.CharField(max_length=1)
    submission_time = models.DateTimeField(auto_now_add=True)

class PostMembers(models.Model):
    'Only in case you want to share a post with someone who is a guest in the group'
    class Meta:
        db_table = "post_members"
    
    post = models.ForeignKey(Group, on_delete=models.PROTECT)
    member = models.ForeignKey(User, on_delete=models.PROTECT)

class CommentsManager(models.Manager):
    def for_user(self, user):
        return Comment.objects.filter(Q(post__group__members=user) | Q(post__group__group_type=Group.OPEN))

class Comment(models.Model):
    class Meta:
        db_table = "comments"
    
    objects = CommentsManager()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name="comments")
    html = models.TextField(max_length=8192)
    submission_time = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        self.html = comment_cleaner.clean(self.html)
        super().save(*args, **kwargs)

    def edit(self, html, author):
        now = timezone.now()
        self.html = html
        self.last_modified = now
        self.save()
        
        self.post.last_activity = now
        self.post.save(update_fields=["last_activity"])

        if self.post.parent_post:
            self.post.parent_post.last_activity = now
            self.post.parent_post.save(update_fields=["last_activity"])

        return self

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

class Favourite(models.Model):
    class Meta:
        # Yes, I use Queen's english
        db_table = "favourites"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    post = models.ForeignKey(Post, on_delete=models.PROTECT)
    favourited_on = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

class LastSeenOnPostManager(models.Manager):
    def upsert(self, user, post_id, timestamp):
        post = Post.objects.for_user(user).get(pk=post_id)
        LastSeenOnPost.objects.update_or_create(user=user, post=post, defaults={'seen': timestamp})
        

class LastSeenOnPost(models.Model):
    class Meta:
        db_table = "last_seen_on_post"
        indexes = [
            models.Index(name="lastseenonpostindx_user_post", fields=['user', 'post'])
        ]
        constraints = [
            models.UniqueConstraint(name="lastseenonpost_unique_user_post", fields=['user', 'post'])
        ]
    
    objects = LastSeenOnPostManager()
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    post = models.ForeignKey(Post, on_delete=models.PROTECT)
    seen = models.DateTimeField(auto_now=True)

    