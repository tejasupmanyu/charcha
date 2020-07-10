from django.db import migrations, models

def top_level_comments_to_posts(apps, schema_editor):
    Post = apps.get_model("discussions", "Post")
    Comment = apps.get_model("discussions", "Comment")

    top_level_comments = Comment.objects.raw("select * from comments where length(wbs) = 5")
    post_objs = []
    comment_objs = []

    for comment in top_level_comments:
        post = Post()
        post.parent_post = comment.post
        post.html = comment.html
        post.author = comment.author
        post.upvotes = comment.upvotes
        post.downvotes = comment.downvotes
        post.submission_time = comment.submission_time
        post.temp_comment_id = comment.id
        post_objs.append(post)
    
    Post.objects.bulk_create(post_objs, batch_size=100)

POINT_NESTED_COMMENTS_TO_NEWLY_CREATED_POST = """
    UPDATE comments as child_comment
    SET post_id = p.id
    FROM comments as parent_comment, posts as p
    WHERE child_comment.post_id = parent_comment.post_id
    AND substring(child_comment.wbs, 1, 5) = parent_comment.wbs
    AND length(child_comment.wbs) > 5
    AND parent_comment.id = p.temp_comment_id;
"""

SOFT_DELETE_ALL_PARENT_COMMENTS = """
    UPDATE comments as c
    SET post_id = 1
    WHERE length(wbs) = 5 and exists (
        SELECT 'x' FROM posts p where p.temp_comment_id = c.id
    )
"""

class Migration(migrations.Migration):
    dependencies = [
        ('discussions', '0023_auto_20200709_1246'),
    ]

    operations = [
        migrations.RunPython(top_level_comments_to_posts),
        migrations.RunSQL(POINT_NESTED_COMMENTS_TO_NEWLY_CREATED_POST),
        migrations.RunSQL(SOFT_DELETE_ALL_PARENT_COMMENTS),
    ]
