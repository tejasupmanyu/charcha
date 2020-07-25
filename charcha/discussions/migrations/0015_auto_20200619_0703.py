# Generated manually to migrate post.team to post.teams 
# i.e. move from 1:many to many:many relationship

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0014_auto_20200619_0603'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='post',
            name='team',
        ),
    ]
