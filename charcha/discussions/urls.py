from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.homepage, name="home"),
    url(r'^discuss/(?P<post_id>\d+)/$', views.PostView.as_view(), name="post_old"),
    url(r'^posts/(?P<post_id>\d+)/$', views.PostView.as_view(), name="post_optional_slug"),
    url(r'^posts/(?P<post_id>\d+)/(?P<slug>[a-zA-Z0-9-]+)/$', views.PostView.as_view(), name="post"),
    url(r'^teams/(?P<team_id>\d+)/new/(?P<post_type>\w+)/$', views.NewPostView.as_view(), name="new-post"),
    url(r'^post/(?P<post_id>\d+)/edit$', views.EditPostView.as_view(), name="edit-discussion"),
    
    url(r'^profile/me/$', views.myprofile, name="myprofile"),
    url(r'^profile/(?P<userid>\d+)/$', views.profile, name="profile"),
    
    url(r'^comments/(?P<id>\d+)/reply$', views.ReplyToComment.as_view(), name="reply_to_comment"),
    url(r'^comments/(?P<id>\d+)/edit$', views.EditComment.as_view(), name="edit_comment"),

    url(r'^api/posts/(?P<post_id>\d+)/upvote$', views.upvote_post, name="upvote_post"),
    url(r'^api/posts/(?P<post_id>\d+)/downvote$', views.downvote_post, name="downvote_post"),

    url(r'^api/comments/(?P<comment_id>\d+)/upvote$', views.upvote_comment, name="upvote_comment"),
    url(r'^api/comments/(?P<comment_id>\d+)/downvote$', views.downvote_comment, name="downvote_comment"),

    url(r'^api/upload$', views.FileUploadView.as_view(), name="upload-files"),

    url(r'^teams/(?P<team_id>\d+)/$', views.team_home, name="team_home"),

]