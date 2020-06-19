# Generated manually to migrate post.team to post.teams 
# i.e. move from 1:many to many:many relationship

from django.db import migrations, models
import django.db.models.deletion

def insert_into_teamposts(apps, schema_editor):
    '''We are converting post.team, a 1:many relationhip to post.teams, a many:many relationship
    So before we delete post.team, we need to copy the value to post.teams field
    '''
    Post = apps.get_model("discussions", "Post")
    TeamPosts = apps.get_model("discussions", "TeamPosts")

    teampost_objs = []
    for post in Post.objects.all():
        team_post = TeamPosts(post=post, team=post.team)
        teampost_objs.append(team_post)
    TeamPosts.objects.bulk_create(teampost_objs, batch_size=100)

class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0014_auto_20200619_0603'),
    ]

    operations = [
        migrations.RunPython(insert_into_teamposts),
        migrations.RemoveField(
            model_name='post',
            name='team',
        ),
    ]
