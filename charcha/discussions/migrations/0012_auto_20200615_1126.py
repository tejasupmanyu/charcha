# Manually created to convert all heading tags to h3

from django.db import migrations, models
import re
regex = re.compile(r"<h[1-6]>([^<^>]+)</h[1-6]>")

def normalize_headings(html):
    return re.sub(regex, r"<h3>\1</h3>", html)

def normalize_posts_and_comments(apps, schema_editor):
    '''In a previous migration, we renamed the database column from text to html
        ... but the value was still a markdown
        With this migration, we bulk update the column so that it stores HTML only
    '''
    Comment = apps.get_model("discussions", "Comment")
    Post = apps.get_model("discussions", "Post")

    comment_objs = []
    for comment in Comment.objects.all():
        comment.html = normalize_headings(comment.html)
        comment_objs.append(comment)
    Comment.objects.bulk_update(comment_objs, ['html'], batch_size=100)

    post_objs = []
    for post in Post.objects.all():
        post.html = normalize_headings(post.html)
        post_objs.append(post)
    Post.objects.bulk_update(post_objs, ['html'], batch_size=100)


class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0011_auto_20200612_1526'),
    ]

    operations = [
        migrations.RunPython(normalize_posts_and_comments),
    ]
