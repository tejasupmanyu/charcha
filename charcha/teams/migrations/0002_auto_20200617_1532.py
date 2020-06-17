# Manually created to create teams

from django.db import migrations, models

def create_teams(apps, schema_editor):
    Team = apps.get_model("teams", "Team")
    tech = Team(name="tech", gchat_space="spaces/AAAAUvEDvzY")
    tech.save()
    announcements = Team(name="announcements", gchat_space="spaces/AAAAKhcznP4")
    announcements.save()
    random = Team(name="random", gchat_space="spaces/AAAAsBEcPIA")
    random.save()

class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_teams),
    ]
