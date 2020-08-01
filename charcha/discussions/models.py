from collections import defaultdict
import re
from itertools import chain
from django.db import connection
from django.utils import timezone
from django.db.utils import IntegrityError
from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import F, Q, Prefetch, OuterRef, Subquery, Count, Exists
from django.urls import reverse
from .bot import notify_space
from bleach.sanitizer import Cleaner
from django.core.exceptions import PermissionDenied
from django.db import transaction

import re

comment_cleaner = Cleaner(
    tags=['a', 'b', 'em', 'i', 'strong', 'span'
    ],
    attributes={
        "a": ("href", "name", "target", "title", "id", "rel", "data-trix-attachment",),
        "span": ("data-user-id", "class"),
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
            "span": ("class", "data-user-id"),
        },
    strip=False
)
regex = re.compile(r"<h[1-6]>([^<^>]+)</h[1-6]>")

def clean_and_normalize_html(html):
    html = cleaner.clean(html)
    return re.sub(regex, r"<h3>\1</h3>", html)

def extract_mentions(html, exclude=None):
    """
    :param html: normalized html text
    :param exclude: list of user ids to exclude
    :return: User list of mentions
    """
    if not exclude:
        exclude = []

    regex = r'data-user-id="(\d+)">'
    matches = re.finditer(regex, html, re.MULTILINE | re.IGNORECASE)
    mentions = set()
    for match in matches:
        for group in match.groups():
            mentions.add(group)
    users = User.objects.filter(id__in=mentions).exclude(id__in=exclude)
    return users

def send_notification_on_mentions(post_or_comment):
    '''Notifies users if they were mentioned in the post or comment. 
    Returns a set of user ids that were notified
    This can be used to prevent duplicate notifications for the same event
    '''
    users = extract_mentions(post_or_comment.html)
    if not users:
        return {}
    
    pc = post_or_comment
    is_comment = False
    is_child_post = False

    if hasattr(pc, 'post'):
        is_comment = True
        post = pc.post
    else:
        post = pc

    if post.parent_post:
        is_child_post = True
        parent_post = post.parent_post
    else:
        parent_post = post
    
    url_suffix = ""
    if is_comment:
        url_suffix = "#comment-" + str(pc.id)
    elif is_child_post:
        url_suffix = "#post-" + str(pc.id)

    event = {
        "heading": "You were mentioned",
        "sub_heading": "by " + pc.author.username,
        "image": pc.author.avatar,
        "line1": parent_post.title,
        "line2": pc.html,
        "link": SERVER_URL + reverse("post", args=[parent_post.id, parent_post.slug]) + url_suffix,
        "link_title": "Open"
    }
    
    # actually notify the users
    for user in users:
        notify_space(user.gchat_space, event)
    
    # return the set of users that were notified
    return set([u.id for u in users])

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

class User(AbstractUser):
    """Our custom user model with a score"""
    class Meta:
        db_table = "users"

    score = models.IntegerField(default=0)
    avatar = models.URLField(max_length=1000, default=None, null=True)
    band = models.CharField(max_length=5, default=None, null=True)
    designation = models.CharField(max_length=100, default=None, null=True)
    employee_id = models.CharField(max_length=10, default=None, null=True)
    joining_date = models.DateField(null=True, default=None)
    
    # This field maps a charcha user to a google hangouts user
    gchat_primary_key = models.CharField(max_length=100, default=None, blank=True, null=True)
    
    # If the user has added charcha bot, then this field stores the unique space id
    gchat_space = models.CharField(max_length=50, default=None, blank=True, null=True)
    tzname = models.CharField(max_length=50, default='Asia/Kolkata')

class GchatSpace(models.Model):
    class Meta:
        db_table = "gchat_spaces"

    name = models.CharField(max_length=100)
    space = models.CharField(max_length=50)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class GroupsManager(models.Manager):
    def for_user(self, user):
        # Return a queryset that only returns groups the user has access to
        return Group.objects\
            .filter(Q(Exists(GroupMember.objects.only('id').filter(group=OuterRef('pk'), user=user))) | Q(group_type=Group.OPEN))\
            .filter(is_deleted=False)

class Group(models.Model):
    OPEN = 0
    CLOSED = 1
    SECRET = 2

    class Meta:
        db_table = "groups"
    
    objects = GroupsManager()
    name = models.CharField(max_length=100, help_text="A unique name for this group")
    group_type = models.IntegerField(
        default=CLOSED,
        choices = (
            (OPEN, 'Open'),
            (CLOSED, 'Closed'),
            (SECRET, 'Secret'),
        ),
        help_text="<li><strong>Public groups</strong> are accessible to any logged in user belonging to HashedIn</li><li><strong>Closed groups</strong> are only accessible to members, but non-members can request to join</li><li><strong>Secret groups</strong> are only visible to its members</li>")
    is_deleted = models.BooleanField(default=False)
    purpose = models.CharField(max_length=200, blank=True, help_text="A 1 or 2 sentence explaining the purpose of this group")
    description = models.TextField(max_length=4096, blank=True, help_text="A larger description that can contain links, charter or any other text to better describe the group")
    members = models.ManyToManyField(User, blank=True,verbose_name="Group Members", through='GroupMember', related_name="mygroups", help_text="Additional members to include in this group")
    gchat_space = models.ForeignKey(GchatSpace, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Google Chat Room", help_text="Charcha will regularly import members from this chat room. By default, each member will have the role 'member'. You can override the role for any member in the group settings screen.")

    @classmethod
    def get(klass, id, user):
        # Alternative get method to ensure user only sees Posts they have access to
        return klass.objects.get(Q(Exists(GroupMember.objects.only('id').filter(group=OuterRef('pk'), user=user))) | Q(group_type=Group.OPEN), pk=id)

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

        self._send_new_post_notifications(post)
        PostSubscribtion.objects.subscribe(post, author, PostSubscribtion.NEW_POSTS_AND_REPLIES_ONLY)

        return post

    def recent_tags(self, period=30):
        tags_with_counts = Tag.objects\
            .filter(posts__group=self)\
            .values('id', 'name', 'fqn')\
            .annotate(count=Count('fqn'))\
            .order_by('-count')
        return list(tags_with_counts)

    @transaction.atomic
    def synchronize_gchat_members(self, members):
        role_member = Role.objects.get(name='member')
        # memers is a list of (key, display_name) tuples
        insert_query = "INSERT INTO incoming_members(key, display_name) VALUES " + ",".join(["(%s, %s)"] * len(members))
        insert_bind_params = list(chain.from_iterable(members))
        with connection.cursor() as c:
            c.execute("""
                CREATE TEMPORARY TABLE incoming_members
                    (key varchar(100), display_name varchar(100), status varchar(10)) 
                ON COMMIT DROP;
            """)
            c.execute(insert_query, insert_bind_params)
            c.execute("""
                UPDATE incoming_members as im
                SET status = 'existing'
                FROM group_members gm, users u
                WHERE im.key = u.gchat_primary_key and u.id = gm.user_id 
                and gm.group_id = %s 
            """, [self.id])
            c.execute("""
                UPDATE incoming_members as im
                SET status = 'new'
                FROM users u
                WHERE u.gchat_primary_key = im.key
                AND NOT EXISTS (SELECT 'x' 
                    FROM group_members gm WHERE gm.group_id = %s
                    AND gm.user_id = u.id
                    AND gm.added_from_gchat = true
                )
            """, [self.id])

            c.execute("""
                INSERT INTO group_members(group_id, user_id, role_id, added_from_gchat)
                SELECT %s, u.id, %s, true
                FROM incoming_members im JOIN users u
                on im.key = u.gchat_primary_key
                and im.status = 'new'
            """, [self.id, role_member.id])
                

    def _send_new_post_notifications(self, post):
        send_notification_on_mentions(post)
        event = {
            "heading": "New Discussion",
            "sub_heading": "by " + post.author.username,
            "image": post.author.avatar,
            "line1": post.title,
            "line2": post.html,
            "link": SERVER_URL + reverse("post", args=[post.id, post.slug]),
            "link_title": "View Discussion"
        }

        # If original post, then notify gchat spaces associated with this group
        if post.parent_post:
            raise Exception("Did not expect a child post to be created from a group!")
    
        if not self.gchat_space.is_deleted:
            space_id = self.gchat_space.space
            notify_space(space_id, event)

    def get_permissions(self, user):
        permissions = []
        try:
            member = GroupMember.objects.select_related("role").get(group=self, user=user)
            user_role = member.role
        except GroupMember.DoesNotExist:
            return permissions
        
        if user_role.name == 'administrator':
            permissions.extend(["can_assign_roles", "can_edit_group_details", "can_view_group_details"])
        elif user_role.name == 'moderator':
            permissions.extend(["can_assign_roles", "can_edit_group_details", "can_view_group_details"])
        elif user_role.name == 'member':
            permissions.extend(["can_edit_group_details", "can_view_group_details"])

        return permissions
    def check_permission(self, user, permission):
        try:
            member = GroupMember.objects.select_related("role").get(group=self, user=user)
            user_role = member.role
        except GroupMember.DoesNotExist:
            raise PermissionDenied("User " + str(user) + " does not have permission " + permission + " in group " + str(self))
        
        if permission == 'can_assign_roles':
            if user_role.name in ('administrator', 'moderator'):
                return True
        elif permission == 'can_edit_group_details':
            if user_role.name in ('administrator', 'moderator', 'member'):
                return True
        raise PermissionDenied("User " + str(user) + " does not have permission " + permission + " in group " + str(self))

    def __str__(self):
        return self.name

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
    added_from_gchat = models.BooleanField()

class PostsManager(models.Manager):
    def for_user(self, user):
        return Post.objects.filter(Q(Exists(GroupMember.objects.only('id').filter(group=OuterRef('group'), user=user))) | Q(group__group_type=Group.OPEN))

    def get_post_details(self, post_id, user):
        parent_post = Post.objects\
            .select_related("author")\
            .prefetch_related(Prefetch("comments", queryset=Comment.objects.select_related("author").filter(is_deleted=False).order_by('submission_time')))\
            .select_related("group")\
            .prefetch_related("tags")\
            .annotate(lastseen_timestamp=Subquery(LastSeenOnPost.objects.filter(post=OuterRef('pk'), user=user).only('seen').values('seen')[:1]))\
            .annotate(my_subscription=Subquery(PostSubscribtion.objects.filter(post=OuterRef('pk'), user=user).only('notify_on').values('notify_on')[:1]))\
            .get(pk=post_id)
        
        child_posts = list(Post.objects\
            .select_related("author")\
            .prefetch_related(Prefetch("comments", queryset=Comment.objects.select_related("author").filter(is_deleted=False).order_by('submission_time')))\
            .annotate(lastseen_timestamp=Subquery(LastSeenOnPost.objects.filter(post=OuterRef('pk'), user=user).only('seen').values('seen')[:1]))\
            .filter(parent_post__id = post_id)\
            .order_by("submission_time"))
        
        post_and_child_posts = [parent_post]
        post_and_child_posts.extend(child_posts)

        for post in post_and_child_posts:
            # For the time being, add an upvotes field so that the UI doesn't have to change
            if '👍' in post.reaction_summary:
                post.upvotes = post.reaction_summary['👍']
            else:
                post.upvotes = 0
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
        
        return (parent_post, child_posts)

    def get_post_list(self, user, tag=None, group=None, sort_by='recentposts'):
        posts = Post.objects\
            .select_related('author')\
            .select_related('group')\
            .annotate(lastseen_timestamp=Subquery(LastSeenOnPost.objects.filter(post=OuterRef('pk'), user=user).only('seen').values('seen')[:1]))\
            .filter(
                Q(Exists(GroupMember.objects.only('id').filter(group=OuterRef('group'), user=user))) | Q(group__group_type=Group.OPEN), 
                parent_post=None
            )
        if group:
            posts = posts.filter(group=group)
        if tag:
            posts = posts.filter(Q(Exists(PostTag.objects.only('id').filter(post=OuterRef('pk'), tag=tag))))

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
    title = models.CharField(max_length=120, blank=True, null=True)
    slug = models.CharField(max_length=120, blank=True, null=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    submission_time = models.DateTimeField(auto_now_add=True)

    # When this post was last modified
    last_modified = models.DateTimeField(auto_now=True)

    # activity includes new sub-post, new comment, or edits to sub-post / comment
    # we use auto_now_add because there are times we want to update the post without updating last_activity
    # for example, when posts are upvoted / downvoted, we don't want to update last_activity
    last_activity = models.DateTimeField(auto_now_add=True)

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
    html = models.TextField(max_length=16384)
    is_deleted = models.BooleanField(default=False)
    sticky = models.BooleanField(default=False)
    accepted_answer = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    num_comments = models.IntegerField(default=0)
    reaction_summary = JSONField(default=dict)
    score = models.IntegerField(default=0)
    last_seen = models.ManyToManyField(User, through='LastSeenOnPost', related_name='last_seen')
    tags = models.ManyToManyField('Tag', through='PostTag', related_name='posts', blank=True)
    subscriptions = models.ManyToManyField(User, through='PostSubscribtion', related_name='subscriptions', blank=True)

    def new_child_post(self, author, post):
        post.author = author
        post.parent_post = self
        post.group = self.group

        now = timezone.now()
        post.last_modified = now
        post.save()

        self.last_activity = now
        self.save(update_fields=["last_activity"])

        self._send_new_child_post_notifications(post)
        PostSubscribtion.objects.subscribe(self, author, PostSubscribtion.REPLIES_ONLY)
        return post

    def _send_new_child_post_notifications(self, post):
        already_notified_users = send_notification_on_mentions(post)

        # Remember, self is the parent post
        # post is the child post that newly got created

        event = {
            "heading": "New Response",
            "sub_heading": "by " + post.author.username,
            "image": post.author.avatar,
            "line1": self.title,
            "line2": post.html,
            "link": SERVER_URL + reverse("post", args=[self.id, self.slug]) + "#post-" + str(post.id),
            "link_title": "View Response"
        }

        for subscription in PostSubscribtion.objects.filter(post=self).all():
            # If user hasn't added charcha bot, skip notification
            if not subscription.user.gchat_space:
                continue
            
            # If users have a @mention in the post, they would have already received a notification
            # So do not send another notification
            if subscription.user.id in already_notified_users:
                continue

            # Don't send notifications to the author
            if subscription.user == post.author:
                continue

            send_notification = False

            # Send notification to users who have subscribed to all notifications or new posts
            if subscription.notify_on in (PostSubscribtion.ALL_NOTIFICATIONS, PostSubscribtion.NEW_POSTS_AND_REPLIES_ONLY):
                send_notification = True
            # If user preference is REPLIES_ONLY, then check if this user is the author of the parent post
            elif subscription.notify_on in (PostSubscribtion.REPLIES_ONLY, ):
                if subscription.user == self.author:
                    send_notification = True
            
            if send_notification:
                space_id = subscription.user.gchat_space
                notify_space(space_id, event)


    def upvote(self, user):
        return self.react(user, '👍')
        

    def downvote(self, user):
        return self.react(user, '👎')

    def react(self, user, reaction_emoji):
        SCORE_FOR_REACTION = {
            '👍': 1,
            '👎': -1,
            '😀': 1,
        }
        if reaction_emoji not in SCORE_FOR_REACTION:
            return

        if self._voting_for_myself(user):
            return
        
        score_delta = SCORE_FOR_REACTION[reaction_emoji]

        # If this user had previously reacted on this post, then "undo" the reaction by deleting it
        num_rows, _ = Reaction.objects.filter(post=self, author=user, reaction=reaction_emoji).delete()
        if num_rows > 0:
            # The user had previously reacted on this post..
            score_delta = score_delta * -1
        else:
            Reaction.objects.create(post=self, author=user, reaction=reaction_emoji)
        
        # This does have a race condition, but it is fine for now.
        if reaction_emoji in self.reaction_summary:
            self.reaction_summary[reaction_emoji] += score_delta
        else:
            self.reaction_summary[reaction_emoji] = score_delta
        self.save(update_fields=["reaction_summary"])

        # Increment/Decrement the score of author
        self.author.score = F('score') + score_delta
        self.author.save(update_fields=["score"])

        self.refresh_from_db(fields=['reaction_summary'])
        return self.reaction_summary[reaction_emoji]

    def _voting_for_myself(self, user):
        return self.author.id == user.id

    def save(self, *args, **kwargs):
        self.html = clean_and_normalize_html(self.html)
        is_create = False
        if not self.pk:
            is_create = True
        super().save(*args, **kwargs)  # Call the "real" save() method.

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

        if self.parent_post:
            parent_post = self.parent_post
        else:
            parent_post = self

        self._send_notifications_on_new_comment(parent_post, comment)
        
        # Is it necessary to subscribe people who comment?
        # Right now, we don't auto-subscribe people who just comment 
        # PostSubscribtion.objects.subscribe(parent_post, author, PostSubscribtion.REPLIES_ONLY)
        return comment

    def _send_notifications_on_new_comment(self, parent_post, comment):
        already_notified_users = send_notification_on_mentions(comment)
        event = {
            "heading": "New Comment",
            "sub_heading": "by " + comment.author.username,
            "image": comment.author.avatar,
            "line1": parent_post.title,
            "line2": comment.html,
            "link": SERVER_URL + reverse("post", args=[parent_post.id, parent_post.slug]) + "#comment-" + str(comment.id),
            "link_title": "View Comment"
        }
        
        for subscription in PostSubscribtion.objects.filter(post=parent_post).all():
            # If user hasn't added charcha bot, skip notification
            if not subscription.user.gchat_space:
                continue

            # If users have a @mention in the comment, they would have already received a notification
            # So do not send another notification
            if subscription.user.id in already_notified_users:
                continue

            # Don't send notifications to the author
            if subscription.user == comment.author:
                continue

            send_notification = False

            # Send notification to users who have subscribed to all notifications or new posts
            if subscription.notify_on in (PostSubscribtion.ALL_NOTIFICATIONS, ):
                send_notification = True
            # If user preference is REPLIES_ONLY, then check if this user is the author of the post to which this comment is being added
            elif subscription.notify_on in (PostSubscribtion.REPLIES_ONLY, PostSubscribtion.NEW_POSTS_AND_REPLIES_ONLY):
                if subscription.user == self.author:
                    send_notification = True
            
            if send_notification:
                space_id = subscription.user.gchat_space
                notify_space(space_id, event)

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
        return Comment.objects\
            .filter(Q(Exists(GroupMember.objects.only('id').filter(group=OuterRef('post__group'), user=user))) | Q(post__group__group_type=Group.OPEN))\
            .filter(is_deleted=False)

class Comment(models.Model):
    class Meta:
        db_table = "comments"
    
    objects = CommentsManager()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    post = models.ForeignKey(Post, on_delete=models.PROTECT, related_name="comments")
    html = models.TextField(max_length=256)
    submission_time = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
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

class TagManager(models.Manager):
    def for_user(self, user):
        # Tags are visible to all users
        return Tag.objects.all()

class Tag(models.Model):
    class Meta:
        db_table = "tags"
        indexes = [
            models.Index(fields=["ext_id",]),
            models.Index(fields=["name", ]),
        ]
        constraints = [
            models.UniqueConstraint(fields=['parent', 'name'], name="tag_unique_name_within_parent")
        ]
    
    objects = TagManager()
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, default=None)

    # fqn is fully qualified name, and is redundnat
    # it combines parent.name as well as name into a single string
    fqn = models.CharField(max_length=200)
    is_external = models.BooleanField(default=False)
    imported_on = models.DateTimeField(null=True, default=None)
    ext_id = models.CharField(null=True, max_length=40)
    ext_link = models.URLField(null=True, blank=True)
    is_visible = models.BooleanField(default=True)
    # Adhoc attributes that describe this tag
    # must be toplevel key=value pair, nested objects are not supported
    attributes = JSONField(default=dict)
    def __str__(self):
        return self.fqn

class PostTag(models.Model):
    class Meta:
        db_table = "post_tags"
    
    post = models.ForeignKey(Post, on_delete=models.PROTECT)
    tag = models.ForeignKey(Tag, on_delete=models.PROTECT)
    tagged_on = models.DateTimeField(auto_now_add=True)

class PostSubscribtionManager(models.Manager):
    def subscribe(self, post, user, notify_on):
        PostSubscribtion.objects.update_or_create(post=post, user=user, defaults={'notify_on': notify_on})

class PostSubscribtion(models.Model):
    MUTE = 0
    REPLIES_ONLY = 1
    NEW_POSTS_AND_REPLIES_ONLY = 2
    ALL_NOTIFICATIONS = 3
    
    _NOTIFY_ON_CHOICES = (
        (MUTE, "Mute"),
        (REPLIES_ONLY, "Replies Only"),
        (NEW_POSTS_AND_REPLIES_ONLY, "New Posts and Replies Only"),
        (ALL_NOTIFICATIONS, "All Notifications"),
    )

    @staticmethod
    def notify_on_choices():
        return PostSubscribtion._NOTIFY_ON_CHOICES
    
    class Meta:
        db_table = "post_subscriptions"

    objects = PostSubscribtionManager()
    post = models.ForeignKey(Post, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    notify_on = models.IntegerField(choices=_NOTIFY_ON_CHOICES)
