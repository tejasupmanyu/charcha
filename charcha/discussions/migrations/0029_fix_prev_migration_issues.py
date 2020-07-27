from django.db import migrations, models

UPDATE_REACTION_SUMMARY = """
    WITH post_reaction_summary as (
        SELECT post_id, reaction, count(*) as count 
        FROM reactions 
        GROUP BY post_id, reaction
    )
    UPDATE posts as p
    SET reaction_summary = reaction_summary || jsonb_build_object(reaction, count)
    FROM post_reaction_summary prs
    WHERE prs.post_id = p.id and reaction = %s;
"""
class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0028_auto_20200726_1229'),
    ]

    operations = [
        migrations.RunSQL([(UPDATE_REACTION_SUMMARY, ['👍'])]),
        migrations.RunSQL([(UPDATE_REACTION_SUMMARY, ['👎'])]),
    ]

