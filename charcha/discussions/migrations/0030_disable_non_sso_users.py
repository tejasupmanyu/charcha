from django.db import migrations, models

# Disable accounts that were created using username + password authentication
DISABLE_NON_SSO_USERS = """
    UPDATE users 
    SET is_active = false, username = username || '.deleted' 
    WHERE id IN ( 
        SELECT u.id FROM users u WHERE NOT EXISTS
            (SELECT 'x' FROM social_auth_usersocialauth sa WHERE sa.user_id = u.id) 
        AND is_staff = false
    );
"""

# These users had created accounts before we had sso using google
# and their usernames before sso were the same as their email
# As a result, when they migrated to SSO, they received auto-generated usernames
# With this, we ensure that username matches email addresses for every active user
UPDATE_USERS_FIX_USERNAME = """
    UPDATE users SET username = %s WHERE email = %s;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('discussions', '0029_fix_prev_migration_issues'),
    ]

    operations = [
        migrations.RunSQL(DISABLE_NON_SSO_USERS),
        migrations.RunSQL([(UPDATE_USERS_FIX_USERNAME, ['vivek.gyaneshwar', 'vivek.gyaneshwar@hashedin.com'])]),
        migrations.RunSQL([(UPDATE_USERS_FIX_USERNAME, ['prajapati.a', 'prajapati.a@hashedin.com'])]),
        migrations.RunSQL([(UPDATE_USERS_FIX_USERNAME, ['vaibhav.singh', 'vaibhav.singh@hashedin.com'])]),
        migrations.RunSQL([(UPDATE_USERS_FIX_USERNAME, ['nagarjun.ms', 'nagarjun.ms@hashedin.com'])]),
        migrations.RunSQL([(UPDATE_USERS_FIX_USERNAME, ['shivam.k', 'shivam.k@hashedin.com'])]),
        migrations.RunSQL([(UPDATE_USERS_FIX_USERNAME, ['rahul.raj', 'rahul.raj@hashedin.com'])]),
    ]

