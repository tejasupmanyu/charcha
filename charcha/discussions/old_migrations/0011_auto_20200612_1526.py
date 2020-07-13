# Manually created to convert markdown into html in the database

from django.db import migrations, models
import markdown2

def markdown_to_html(apps, schema_editor):
    '''In a previous migration, we renamed the database column from text to html
        ... but the value was still a markdown
        With this migration, we bulk update the column so that it stores HTML only
    '''
    Comment = apps.get_model("discussions", "Comment")
    Post = apps.get_model("discussions", "Post")

    comment_objs = []
    for comment in Comment.objects.all():
        comment.html = markdown2.markdown(comment.html, 
            safe_mode="escape", 
            extras=["fenced-code-blocks"])
        comment_objs.append(comment)
    Comment.objects.bulk_update(comment_objs, ['html'], batch_size=100)

    post_objs = []
    for post in Post.objects.all():
        post.html = markdown2.markdown(post.html, 
            safe_mode="escape", 
            extras=["fenced-code-blocks"])
        post_objs.append(post)
    Post.objects.bulk_update(post_objs, ['html'], batch_size=100)


class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0010_auto_20200612_0717'),
    ]

    operations = [
        migrations.RunPython(markdown_to_html),
    ]
