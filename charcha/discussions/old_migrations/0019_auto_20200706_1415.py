# We are migrating from nested comments to linear comments, effectively making wbs redundant
# As part of this migration, we are rewriting the html to allow an even narrower set of tags

from django.db import migrations, models
from bleach.sanitizer import Cleaner

comment_cleaner = Cleaner(
    tags=['a', 'b', 'em', 'i', 'strong',
    ],
    attributes={
        "a": ("href", "name", "target", "title", "id", "rel", "data-trix-attachment",),
    },
    strip=True
)

def clean_comment_html(apps, schema_editor):
    '''We are converting post.team, a 1:many relationhip to post.teams, a many:many relationship
    So before we delete post.team, we need to copy the value to post.teams field
    '''
    Comment = apps.get_model("discussions", "Comment")

    comment_objs = []
    for comment in Comment.objects.raw("select id, html from comments where length(wbs) >= 10;"):
        comment.html = comment_cleaner.clean(comment.html)
    Comment.objects.bulk_update(comment_objs, fields=['html'], batch_size=100)

class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0018_auto_20200706_1356'),
    ]

    operations = [
        migrations.RunPython(clean_comment_html),
    ]
