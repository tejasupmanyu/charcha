from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.homepage, name="home"),
    url(r'^discuss/(?P<post_id>\d+)/$', views.DiscussionView.as_view(), name="discussion"),
    url(r'^post/(?P<post_id>\d+)/edit$', views.EditDiscussion.as_view(), name="edit-discussion"),
    url(r'^start-discussion/$', views.StartDiscussionView.as_view(), name="start-discussion"),
    
    url(r'^profile/me/$', views.myprofile, name="myprofile"),
    url(r'^profile/(.*)/$', views.profile, name="profile"),
    
    url(r'^comments/(?P<id>\d+)/reply$', views.ReplyToComment.as_view(), name="reply_to_comment"),
    url(r'^comments/(?P<id>\d+)/edit$', views.EditComment.as_view(), name="edit_comment"),

    url(r'^api/posts/(?P<post_id>\d+)/upvote$', views.upvote_post, name="upvote_post"),
    url(r'^api/posts/(?P<post_id>\d+)/downvote$', views.downvote_post, name="downvote_post"),
    url(r'^api/posts/(?P<post_id>\d+)/undovote$', views.undo_vote_on_post, name="undo_vote_on_post"),

    url(r'^api/comments/(?P<comment_id>\d+)/upvote$', views.upvote_comment, name="upvote_comment"),
    url(r'^api/comments/(?P<comment_id>\d+)/downvote$', views.downvote_comment, name="downvote_comment"),
    url(r'^api/comments/(?P<comment_id>\d+)/undovote$', views.undo_vote_on_comment, name="undo_vote_on_comment"),

    url(r'^api/upload$', views.FileUploadView.as_view(), name="upload-files"),

]