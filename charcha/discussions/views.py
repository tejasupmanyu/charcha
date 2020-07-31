import json
import re
import os
import pytz
import datetime
from django.utils import timezone
from uuid import uuid4

from django.http import HttpResponse, JsonResponse
from django.http import HttpResponseRedirect, HttpResponseBadRequest, HttpResponsePermanentRedirect, Http404
from django.views import View 
from django.views.decorators.http import require_http_methods
from django import forms
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import DefaultStorage
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import cache_control

from .models import Post, Comment, Reaction, User, Group, LastSeenOnPost, PostSubscribtion, Tag
from .models import GroupMember, Role
from .models import GchatSpace
from .models import comment_cleaner
from .bot import members as get_members_from_gchat

def get_object_or_404_check_acl(klass, requester, *args, **kwargs):
    'Similar to get_object_or_404, but checks that the user has access to the object that is requested'
    try:
        return klass.objects.for_user(requester).get(*args, **kwargs)
    except klass.DoesNotExist as e:
        raise Http404('No %s matches the given query.' % klass._meta.object_name)

regex = re.compile(r"<h[1-6]>([^<^>]+)</h[1-6]>")
def prepare_html_for_edit(html):
    'Converts all heading tags to h1 because trix only understands h1 tags'
    return re.sub(regex, r"<h1>\1</h1>", html)    

@login_required
def homepage(request):
    sort_by = request.GET.get('sort_by', 'newactivity')
    if sort_by not in ('newactivity', 'recentposts'):
        sort_by = 'newactivity'
    posts = Post.objects.recent_posts(request.user, sort_by=sort_by)
    groups = Group.objects.for_user(request.user).all()
    return render(request, "home.html", context={"posts": posts, "groups": groups, "selected_sort_by": sort_by})

@login_required
def group_home(request, group_id):
    group = get_object_or_404_check_acl(Group, requester=request.user, pk=group_id)
    recent_tags = group.recent_tags()
    sort_by = request.GET.get('sort_by', 'newactivity')
    if sort_by not in ('newactivity', 'recentposts'):
        sort_by = 'newactivity'
    posts = Post.objects.recent_posts(request.user, group=group, sort_by=sort_by)
    return render(request, "home.html", context={"posts": posts, "group": group, "recent_tags": recent_tags, "selected_sort_by": sort_by})

@login_required
def set_user_timezone(request):
    if request.method == 'POST':
        request.user.tzname = request.POST['timezone']
        request.user.save()
    
    return redirect(reverse('myprofile', args=[]))


class HtmlFieldWithMentions(forms.CharField):
    '''Field that cleans out the html before validations are performed
    
    @mentions create a lot of html markup which is ultimately stripped,
    but they cause django forms to issue length validation errors
    So this field strips out unwanted markup before the validator kicks in
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        return comment_cleaner.clean(value)

class CommentForm(forms.ModelForm):
    html = HtmlFieldWithMentions(max_length=256, widget=forms.HiddenInput())
    class Meta:
        model = Comment
        fields = ['html']
        labels = {
            'html': 'Your Comment',
        }

class PostView(LoginRequiredMixin, View):
    def get(self, request, post_id, slug=None):
        post, child_posts = Post.objects.get_post_details(post_id, 
                    request.user)
        if not slug or post.slug != slug:
            post_url = reverse('post', args=[post.id, post.slug])
            return HttpResponsePermanentRedirect(post_url)

        form = CommentForm()
        context = {
            "post": post, 
            "child_posts": child_posts, 
            "form": form, 
            "SERVER_TIME_ISO": timezone.now().isoformat(),
            "notification_choices": PostSubscribtion.notify_on_choices(),
        }
        return render(request, "post.html", context=context)

class AddEditComment(LoginRequiredMixin, View):
    def get(self, request, id=None, post_id=None):
        if post_id:
            post = Post.objects.for_user(request.user).get(pk=post_id)
            comment = Comment()
        elif id:
            post = None
            comment = Comment.objects.for_user(request.user).get(pk=id)

        form = CommentForm(instance=comment)
        context = {"post": post, "form": form}
        return render(request, "add-edit-comment.html", context=context)

    def post(self, request, id=None, post_id=None):
        if post_id:
            post = Post.objects.for_user(request.user).get(pk=post_id)
            comment = Comment()
        elif id:
            comment = Comment.objects.for_user(request.user).select_related("post").get(pk=id)
            post = comment.post

        form = CommentForm(request.POST)
        if not form.is_valid():
            context = {"post": post, "form": form}
            return render(request, "add-edit-comment.html", context=context)

        if post_id:
            comment = post.add_comment(form.cleaned_data['html'], request.user)
        elif id:
            comment = comment.edit(form.cleaned_data['html'], request.user)
        
        if post.parent_post:
            post_url = reverse('post', args=[post.parent_post.id, post.parent_post.slug])
            post_url = post_url + "#post-" + str(post.id)
        else:
            post_url = reverse('post', args=[post.id, post.slug])
        return HttpResponseRedirect(post_url)

class NewPostForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'tags' in self.fields:
            self.fields['tags'].queryset = Tag.objects.filter(is_visible=True).all()

    class Meta:
        model = Post
        fields = ['title', 'html', 'tags']
        labels = {
            'title': 'Title',
            'html': 'Details',
            'tags': 'Tags',
        }
        widgets = {
            'html': forms.HiddenInput()
        }

    def clean(self):
        cleaned_data = super(NewPostForm, self).clean()
        html = cleaned_data.get("html")
        if not html:
            raise forms.ValidationError(
                "HTML cannot be empty"
            )
        return cleaned_data

class NewPostView(LoginRequiredMixin, View):
    def get(self, request, post_type, group_id=None, parent_post_id = None):
        if parent_post_id:
            parent_post = Post.objects.for_user(request.user).select_related('group').get(pk=parent_post_id)
            group = parent_post.group
        elif group_id:
            group = Group.objects.for_user(request.user)\
                .get(pk=group_id)
            parent_post = None
        else:
            raise Exception("group_id and parent_post_id are both None, at least 1 must be provided")
        
        post_type_id = Post.get_post_type(post_type)

        if post_type == "discussion":
            post_type_for_display = "Start a Discussion"
        elif post_type == "question":
            post_type_for_display = "Ask a Question"
        elif post_type == "feedback":
            post_type_for_display = "Request Feedback"
        elif post_type == "announcement":
            post_type_for_display = "New Announcment"
        elif post_type == "response":
            post_type_for_display = "Post a Response"
        elif post_type == "answer":
            post_type_for_display = "Post an Answer"
        else:
            raise Exception("Invalid Post Type")
        form = NewPostForm()
        return render(request, "new-post.html", 
            context={
                "form": form, 
                "post_type_for_display": post_type_for_display, 
                "parent_post": parent_post, 
                "group": group
            }
        )

    def post(self, request, post_type, group_id=None, parent_post_id = None):
        if parent_post_id:
            parent_post = Post.objects\
                .for_user(request.user)\
                .select_related('group')\
                .get(pk=parent_post_id)
            group = parent_post.group
        elif group_id:
            group = Group.objects.for_user(request.user)\
                .get(pk=group_id)
            parent_post = None
        else:
            raise Exception("group_id and parent_post_id are both None, at least 1 must be provided")

        form = NewPostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.post_type = Post.get_post_type(post_type)
            if parent_post:
                post = parent_post.new_child_post(request.user, post)
                new_post_url = reverse('post', args=[parent_post.id, parent_post.slug]) + "#post-" + str(post.id)
            elif group:
                post = group.new_post(request.user, post)
                new_post_url = reverse('post', args=[post.id, post.slug])
            else:
                raise Exception("One of parent_post or group should be non-None")

            # now save the tags
            form.save_m2m()
            return HttpResponseRedirect(new_post_url)
        else:
            return render(request, "new-post.html", context={"form": form})

class EditPostForm(NewPostForm):
    class Meta:
        model = Post
        fields = ['title', 'html', 'tags']
        widgets = {'html': forms.HiddenInput()}

class EditChildPostForm(EditPostForm):
    class Meta:
        model = Post
        fields = ['html']
        widgets = {'html': forms.HiddenInput()}

class EditPostView(LoginRequiredMixin, View):
    def get(self, request, **kwargs):
        post = get_object_or_404_check_acl(Post, pk=kwargs['post_id'], requester=request.user)
        post.html = prepare_html_for_edit(post.html)
        if post.parent_post:
            form = EditChildPostForm(instance=post)
        else:
            form = EditPostForm(instance=post)    
        context = {"form": form}
        return render(request, "edit-post.html", context=context)

    def post(self, request, **kwargs):
        post = get_object_or_404_check_acl(Post, pk=kwargs['post_id'], requester=request.user)
        form = EditPostForm(request.POST, instance=post)

        if not form.is_valid():
            context = {"form": form}
            return render(request, "edit-post.html", context=context)
        else:
            form.save(commit=False)
            post.edit_post(form.cleaned_data['title'], form.cleaned_data['html'], request.user)
            form.save_m2m()
        
        if post.parent_post:
            parent_post_url = reverse('post', args=[post.parent_post.id, post.parent_post.slug])
            post_url = parent_post_url + "#post-" + str(post.id)
        else:
            post_url = reverse('post', args=[post.id, post.slug])

        
        return HttpResponseRedirect(post_url)

@login_required
@require_http_methods(['POST'])
def upvote_post(request, post_id):
    post = get_object_or_404_check_acl(Post, pk=post_id, requester=request.user)
    upvotes = post.upvote(request.user)
    return HttpResponse(upvotes)

@login_required
@require_http_methods(['POST'])
def downvote_post(request, post_id):
    post = get_object_or_404_check_acl(Post, pk=post_id, requester=request.user)
    downvotes = post.downvote(request.user)
    return HttpResponse(downvotes)

@login_required
@require_http_methods(['POST'])
def update_post_last_seen_at(request, post_id):
    last_seen_str = request.POST['last_seen']
    last_seen = datetime.datetime.fromisoformat(last_seen_str)
    LastSeenOnPost.objects.upsert(request.user, post_id, last_seen)
    return HttpResponse('OK')

@login_required
@require_http_methods(['POST'])
def subscribe_to_post(request, post_id):
    post = get_object_or_404_check_acl(Post, request.user, pk=post_id)
    notify_on = int(request.POST['subscription'])
    PostSubscribtion.objects.subscribe(post, request.user, notify_on)
    return redirect(reverse('post', args=[post.id, post.slug]))

@login_required
def myprofile(request):
    return render(request, "profile.html", context={"user": request.user, 'timezones': pytz.common_timezones})

@login_required
def profile(request, userid):
    user = get_object_or_404(User, pk=userid)
    return render(request, "profile.html", context={"user": user, 'timezones': pytz.common_timezones })

@login_required
@cache_control(private=True, max_age=3600)
def get_users(request):
    users = User.objects.only("username", "id").all()
    return JsonResponse([{"username": x.username, "id": x.id} for x in users], safe=False)

class FileUploadView(LoginRequiredMixin, View):
    def post(self, request, **kwargs):
        file_obj = request.FILES.get('file')
        filename = request.POST['key']
        extension = filename.split(".")[-1].lower()
        if extension not in ('png', 'jpeg', 'jpg', 'svg', 'gif'):
            return HttpResponseBadRequest("Files of type " + extension + " are not supported")
        
        # TODO: Add validation here e.g. file size/type check
        # TODO: Potentially resize image

        # organize a path for the file in bucket
        file_path = '{uuid}/{userid}.{extension}'.\
            format(userid=request.user.id, 
            uuid=uuid4(), extension=extension)
        
        media_storage = DefaultStorage()
        media_storage.save(file_path, file_obj)
        file_url = media_storage.url(file_path)

        # The file url contains a signature, which expires in a few hours
        # In our case, we have made the S3 file public for anyone who has the url
        # Which means, the file is accessible without the signature
        # So we simply strip out the signature from the url - i.e. everything after the ?

        file_url = file_url.split('?')[0]
        
        return JsonResponse({
            'message': 'OK',
            'fileUrl': file_url,
        })

@require_http_methods(['POST'])
@csrf_exempt
def google_chatbot(request):
    event = json.loads(request.body)
    text = None
    if event['type'] == 'ADDED_TO_SPACE':
        if event['space']['type'] == 'DM':
            space_id = event['space']['name']
            email = event['user']['email']
            gchat_user_pk = event['user']['name']
            
            user_exists = User.objects.filter(email=email).update(gchat_primary_key=gchat_user_pk, gchat_space=space_id)
            
            if user_exists:
                text = "From now on, I will notify you of any updates in the discussions you participate."
            else:
                text = """You haven't logged in to charcha yet. Please do the following:
                    1. Remove charcha bot 
                    2. Go to https://charcha.hashedin.com and login with your @hashedin.com email address
                    3. Then come back and add charcha bot once again
                    """
        elif event['space']['type'] == 'ROOM':
            space = event['space']['name']
            # room name can be None for DMs between multiple people
            room_name = event['space'].get('displayName', None)
            if not room_name:
                text = "Sorry, group messages are not supported in Charcha"
            else:
                GchatSpace.objects.update_or_create(space=space, defaults={"name": room_name, "is_deleted": False})
                text = "Charcha bot added!\nP.S. Automatic group creation from google chate is disabled. Instead, login to Charcha and a create a new group."

    elif event['type'] == 'REMOVED_FROM_SPACE':
        if event['space']['type'] == 'DM':
            email = event['user']['email']
            User.objects.filter(email=email).update(gchat_space=None)
        elif event['space']['type'] == 'ROOM':
            space = event['space']['name']
            GchatSpace.objects.filter(space=space).update(is_deleted=True)
    elif event['type'] == 'MESSAGE':
        if event['space']['type'] == 'DM':
            text = "This is a one way street. I will completely ignore anything you type."
        elif event['space']['type'] == 'ROOM':
            # if 'synchronize' in event['message']['argumentText']:
            #     space = event['space']['name']
            #     sync_group(space, room_name)
            #     text = "Done, I have synchronized team members with Charcha"
            # else:
            #    text = "Sorry, I don't understand your message. Try @charcha synchronize"
            text = "Synchronize is temporarily disabled"
    if text:
        return JsonResponse({"text": text})
    else:
        return HttpResponse("OK")

@login_required
@require_http_methods(['POST'])
def sync_members_with_gchat(request, group_id):
    group = get_object_or_404_check_acl(Group, request.user, pk=group_id)
    redirect_url = reverse('edit_group', args=[group_id])
    gchat_space = group.gchat_space.space
    if not gchat_space:
        return redirect(redirect_url)

    gchat_members = get_members_from_gchat(gchat_space)
    members = []
    for member in gchat_members:
        gchat_pk = member['member']['name']
        display_name = member['member']['displayName']
        members.append([gchat_pk, display_name])
    
    group.synchronize_gchat_members(members)
    return redirect(redirect_url)

class NewGroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'group_type', 'members', 'purpose', 'description']
        widgets = {'group_type': forms.RadioSelect()}

class NewGroupView(LoginRequiredMixin, View):
    def get(self, request):
        form = NewGroupForm()
        return render(request, "new-group.html", context={"form": form})
        
    def post(self, request):
        form = NewGroupForm(request.POST)
        if not form.is_valid():
            context = {"form": form}
            return render(request, "new-group.html", context=context)

        group = form.save()
        administrator_role = Role.objects.get(name='administrator')
        member = GroupMember.objects.create(group=group, user=request.user, 
            role=administrator_role, added_from_gchat=False)
        return redirect(reverse('edit_group', args=[group.id]))
        
class EditGroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'group_type', 'purpose', 'description']
        widgets = {'description': forms.HiddenInput(), 'group_type': forms.RadioSelect()}


@require_http_methods(['GET', 'POST'])
@login_required
def edit_group_view(request, group_id):
    group = get_object_or_404_check_acl(Group, requester=request.user, pk=group_id)
    members = GroupMember.objects.select_related("user", "role").filter(group=group).order_by("user__username")
    roles = Role.objects.all()
    my_permissions = group.get_permissions(request.user)
    if request.method == 'GET':
        form = EditGroupForm(instance=group)
    elif request.method == 'POST':
        form = EditGroupForm(request.POST, instance=group)
    context={"form": form, "members": members, "roles": roles, "permissions": my_permissions}
    
    if request.method == 'POST' and form.is_valid():
        group.check_permission(request.user, "can_edit_group_details")
        group = form.save()
        return redirect(reverse('group_home', args=[group.id]))
    
    return render(request, "edit-group.html", context=context)
    
@require_http_methods(['GET', 'POST'])
@login_required
def edit_member_role(request, member_id, role_id):
    member = get_object_or_404(GroupMember, pk=member_id)
    role = get_object_or_404(Role, pk=role_id)    
    member.group.check_permission(request.user, "can_assign_roles")
    member.role = role
    member.save()
    return HttpResponse('OK')
