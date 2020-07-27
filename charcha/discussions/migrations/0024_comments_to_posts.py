from django.db import migrations, models

def top_level_comments_to_posts(apps, schema_editor):
    Post = apps.get_model("discussions", "Post")
    Comment = apps.get_model("discussions", "Comment")

    top_level_comments = Comment.objects.raw("select * from comments where length(wbs) = 5 or length(html) > 256")
    post_objs = []
    comment_objs = []

    for comment in top_level_comments:
        post = Post()
        post.parent_post = comment.post
        post.html = comment.html
        post.author = comment.author
        post.upvotes = comment.upvotes
        post.downvotes = comment.downvotes
        # setting submission_time doesn't really work
        # see COPY_SUBMISSION_TIME below
        post.submission_time = comment.submission_time
        post.temp_comment_id = comment.id
        post_objs.append(post)
    
    Post.objects.bulk_create(post_objs, batch_size=100)

# Post.submission_time has an auto_now set to true
# So when we created the post above, 
# it automatically set the timestamp to now, even though we explicitly tried to set it
# This query does a bulk update to fix the situation
COPY_SUBMISSION_TIME = """
    UPDATE posts as p
    SET submission_time = c.submission_time
    FROM comments as c
    WHERE p.temp_comment_id = c.id;
"""
POINT_NESTED_COMMENTS_TO_NEWLY_CREATED_POST = """
    UPDATE comments as child_comment
    SET post_id = p.id
    FROM comments as parent_comment, posts as p
    WHERE child_comment.post_id = parent_comment.post_id
    AND substring(child_comment.wbs, 1, length(parent_comment.wbs)) = parent_comment.wbs
    AND parent_comment.id = p.temp_comment_id;
"""

COPY_VOTES_TO_NEW_POST = """
    INSERT INTO votes(object_id, type_of_vote, submission_time, content_type_id, voter_id)
    SELECT p.id, v.type_of_vote, v.submission_time, 8, v.voter_id 
    FROM votes v JOIN posts p on v.object_id = p.temp_comment_id and v.content_type_id = 7;
"""

class Migration(migrations.Migration):
    dependencies = [
        ('discussions', '0023_auto_20200709_1246'),
    ]

    operations = [
        migrations.RunPython(top_level_comments_to_posts),
        migrations.RunSQL(COPY_SUBMISSION_TIME),
        migrations.RunSQL(POINT_NESTED_COMMENTS_TO_NEWLY_CREATED_POST),
        migrations.RunSQL(COPY_VOTES_TO_NEW_POST),
    ]
