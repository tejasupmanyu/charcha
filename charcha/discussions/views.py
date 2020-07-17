import json
import re
import os
import pytz
import datetime
from django.utils import timezone
from uuid import uuid4

from django.http import HttpResponse, JsonResponse
from django.http import HttpResponseRedirect, HttpResponseBadRequest, HttpResponsePermanentRedirect
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

from .models import Post, Comment, Reaction, User, Group, LastSeenOnPost
from .models import update_gchat_space


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
    return render(request, "home.html", context={"posts": posts, "groups": [], "selected_sort_by": sort_by})

@login_required
def group_home(request, group_id):
    group = get_object_or_404_check_acl(Group, requester=request.user, pk=group_id)
    # active_members = team.active_team_members()
    sort_by = request.GET.get('sort_by', 'newactivity')
    if sort_by not in ('newactivity', 'recentposts'):
        sort_by = 'newactivity'
    posts = Post.objects.recent_posts(request.user, group=group, sort_by=sort_by)
    return render(request, "home.html", context={"posts": posts, "group": group, "selected_sort_by": sort_by})

@login_required
def set_user_timezone(request):
    if request.method == 'POST':
        request.user.tzname = request.POST['timezone']
        request.user.save()
    
    return redirect(reverse('myprofile', args=[]))

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['html']
        labels = {
            'html': 'Your Comment',
        }
        widgets = {'html': forms.HiddenInput()}

class PostView(LoginRequiredMixin, View):
    def get(self, request, post_id, slug=None):
        post, child_posts = Post.objects.get_post_details(post_id, 
                    request.user)
        if not slug or post.slug != slug:
            post_url = reverse('post', args=[post.id, post.slug])
            return HttpResponsePermanentRedirect(post_url)

        form = CommentForm()
        context = {"post": post, "child_posts": child_posts, "form": form, "SERVER_TIME_ISO": timezone.now().isoformat()}
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
    post.upvote(request.user)
    post.refresh_from_db()
    return HttpResponse(post.upvotes)

@login_required
@require_http_methods(['POST'])
def downvote_post(request, post_id):
    post = get_object_or_404_check_acl(Post, pk=post_id, requester=request.user)
    post.downvote(request.user)
    post.refresh_from_db()
    return HttpResponse(post.downvotes)

@login_required
@require_http_methods(['POST'])
def upvote_comment(request, comment_id):
    comment = get_object_or_404_check_acl(Comment, pk=comment_id, requester=request.user)
    comment.upvote(request.user)
    comment.refresh_from_db()
    return HttpResponse(comment.upvotes)

@login_required
@require_http_methods(['POST'])
def downvote_comment(request, comment_id):
    comment = get_object_or_404_check_acl(Comment, pk=comment_id, requester=request.user)
    comment.downvote(request.user)
    comment.refresh_from_db()
    return HttpResponse(comment.downvotes)

@login_required
@require_http_methods(['POST'])
def update_post_last_seen_at(request, post_id):
    last_seen_str = request.POST['last_seen']
    last_seen = datetime.datetime.fromisoformat(last_seen_str)
    LastSeenOnPost.objects.upsert(request.user, post_id, last_seen)
    return HttpResponse('OK')

@login_required
def myprofile(request):
    return render(request, "profile.html", context={"user": request.user, 'timezones': pytz.common_timezones})

@login_required
def profile(request, userid):
    user = get_object_or_404(User, pk=userid)
    return render(request, "profile.html", context={"user": user })

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