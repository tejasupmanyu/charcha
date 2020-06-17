from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from .models import Post, Comment, Vote, Favourite, User

class UserAdmin(admin.ModelAdmin):
    fields = ('username', 'gchat_space', 'score', 'email', 'is_active', 'is_staff')
    readonly_fields = ('username', )

class PostAdmin(admin.ModelAdmin):
    list_display = ('title', )
    fields = ('title', 'url', 'html', 'author', 'num_comments',
        'upvotes', 'downvotes', 'flags')
    readonly_fields = ('num_comments', 'author')
    
class CommentAdmin(admin.ModelAdmin):
    list_display = ('submission_time', 'post', 'wbs', 'author', 'html')
    fields = ('post', 'parent_comment', 'author', 
        'html', 'wbs', 'upvotes', 'downvotes', 'flags')
    readonly_fields = ('post', 'parent_comment', 'wbs', 'author')

class VoteAdmin(admin.ModelAdmin):
    list_display = ('content_object', 'voter', 'type_of_vote', 'submission_time')

class FavouriteAdmin(admin.ModelAdmin):
    pass

admin.site.register(User, UserAdmin)
admin.site.register(Post, PostAdmin)
admin.site.register(Comment, CommentAdmin)
admin.site.register(Vote, VoteAdmin)
admin.site.register(Favourite, FavouriteAdmin)
