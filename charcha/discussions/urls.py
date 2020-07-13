from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^$', views.homepage, name="home"),
    
    url(r'^posts/(?P<post_id>\d+)/edit/$', views.EditPostView.as_view(), name="edit-discussion"),
    url(r'^posts/(?P<parent_post_id>\d+)/new/(?P<post_type>\w+)/$', views.NewPostView.as_view(), name="new-child-post"),

    # The following 3 urls are all urls for a post
    # - "post" is the canonical url, and should be preferred when using reverse
    # - "post-old" was used earlier, and only exists so that we can redirect appropriately
    # - "post-optional-slug" is only meant to be used in situations where slug is not available
    #       The view will then redirect to the correct url with the slug
    url(r'^posts/(?P<post_id>\d+)/(?P<slug>[a-zA-Z0-9-]+)/$', views.PostView.as_view(), name="post"),
    url(r'^discuss/(?P<post_id>\d+)/$', views.PostView.as_view(), name="post-old"),
    url(r'^posts/(?P<post_id>\d+)/$', views.PostView.as_view(), name="post-optional-slug"),

    url(r'^groups/(?P<group_id>\d+)/$', views.group_home, name="group_home"),
    url(r'^groups/(?P<group_id>\d+)/new/(?P<post_type>\w+)/$', views.NewPostView.as_view(), name="new-post"),
    
        
    url(r'^profile/me/$', views.myprofile, name="myprofile"),
    url(r'^profile/(?P<userid>\d+)/$', views.profile, name="profile"),
    
    url(r'^comments/(?P<id>\d+)/reply$', views.ReplyToComment.as_view(), name="reply_to_comment"),
    url(r'^comments/(?P<id>\d+)/edit$', views.EditComment.as_view(), name="edit_comment"),

    url(r'^api/posts/(?P<post_id>\d+)/upvote$', views.upvote_post, name="upvote_post"),
    url(r'^api/posts/(?P<post_id>\d+)/downvote$', views.downvote_post, name="downvote_post"),

    url(r'^api/comments/(?P<comment_id>\d+)/upvote$', views.upvote_comment, name="upvote_comment"),
    url(r'^api/comments/(?P<comment_id>\d+)/downvote$', views.downvote_comment, name="downvote_comment"),

    url(r'^api/upload$', views.FileUploadView.as_view(), name="upload-files"),

]