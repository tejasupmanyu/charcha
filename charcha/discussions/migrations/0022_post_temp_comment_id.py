# Generated by Django 3.0.7 on 2020-07-09 12:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0021_post_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='temp_comment_id',
            field=models.IntegerField(default=0),
        ),
    ]
