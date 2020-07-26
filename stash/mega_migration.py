def create_roles_and_permissions(apps, schema_editor):
    Role = apps.get_model("discussions", "Role")
    Permission = apps.get_model("discussions", "Permission")

    administrator = Role.objects.create(name="administrator")
    moderator = Role.objects.create(name="moderator")
    member = Role.objects.create(name="member")
    guest = Role.objects.create(name="guest")

UPDATE_GCHAT_KEY_IN_USER = """
    UPDATE users as u
    SET gchat_primary_key = gu.key
    FROM gchat_users as gu
    WHERE gu.user_id = u.id
"""

MIGRATE_TEAMS_TO_GROUPS = """
    INSERT INTO groups(name, group_type, purpose, description, is_deleted, emails)
    SELECT name, 1, description, about, false, array[]::varchar[] FROM TEAMS
"""

MIGRATE_TEAM_MEMBERS_TO_GROUP_MEMBERS = """
    INSERT INTO group_members(group_id, user_id, role_id)
    SELECT g.id, u.id, 3
    FROM team_members tm JOIN teams t on tm.team_id = t.id
        JOIN groups g on g.name = t.name
        JOIN gchat_users gu on tm.gchat_user_id = gu.id
        JOIN users u on gu.user_id = u.id
"""

MIGRATE_TEAM_TO_GCHAT_SPACES = """
    INSERT INTO gchat_spaces(name, space, is_deleted)
    SELECT name, gchat_space, false FROM teams
"""

MIGRATE_TEAM_TO_GROUP_GCHAT_SPACES = """
    INSERT INTO group_gchat_spaces(group_id, gchat_space_id, notify, sync_members)
    SELECT g.id, gs.id, true, true
    FROM teams t JOIN groups g on t.name = g.name
    JOIN gchat_spaces gs on t.name = gs.name
"""

UPDATE_POSTS_SET_GROUP = """
    UPDATE posts as p
    SET group_id = g.id
    FROM groups g, teams t, team_posts tp
    WHERE p.id = tp.post_id AND tp.team_id = t.id
    AND t.name = g.name
"""

UPDATE_GROUP_FOR_CHILD_POSTS = """
    UPDATE posts as child
    SET group_id = parent.group_id
    FROM posts parent 
    WHERE child.parent_post_id = parent.id
"""

UPDATE_POSTS_SET_IS_DELETED = """
    UPDATE posts set is_deleted = false
"""

UPDATE_POSTS_SET_SLUG = """
    UPDATE posts set slug = '' where slug is null
"""

UPDATE_POSTS_SET_SCORE = """
    UPDATE posts as p
    SET score = upvotes - downvotes
"""

UPDATE_POSTS_SET_REACTION_SUMMARY = """
    UPDATE posts
    SET reaction_summary = jsonb_build_object('👍', upvotes, '👎', downvotes)
    WHERE parent_post_id is null
"""

SUBSCRIBE_AUTHORS = """
    INSERT INTO post_subscriptions(post_id, user_id, notify_on)
    SELECT p1.id, p1.author_id, 2
    FROM posts p1 
    WHERE p1.parent_post_id is null
    UNION ALL
    SELECT p2.parent_post_id, p2.author_id, 1
    FROM posts p2
    WHERE p2.parent_post_id is not null
"""


UPDATE_POSTS_SET_LAST_MODIFIED_AND_DEFAULT_LAST_ACTIVITY = """
    UPDATE posts SET last_modified = submission_time, last_activity = submission_time
"""

UPDATE_POSTS_SET_LAST_ACTIVITY = """
    WITH post_last_activity as (
        SELECT rs.post_id, max(rs.last_activity) as last_activity
        FROM
        (
            SELECT COALESCE(p.parent_post_id, p.id) as post_id, p.submission_time as last_activity
            FROM posts p
            UNION ALL
            SELECT COALESCE(p.parent_post_id, p.id) as post_id, c.submission_time as last_activity
            FROM comments c join posts p on c.post_id = p.id
        ) rs
        GROUP BY rs.post_id
    )
    UPDATE posts 
    SET last_activity = pla.last_activity
    FROM post_last_activity pla
    WHERE pla.post_id = id
"""

UPDATE_POSTS_SET_LAST_ACTIVITY_FOR_CHILD_POSTS = """
    UPDATE posts as child_post
    SET last_activity = parent.last_activity
    FROM posts parent
    WHERE child_post.parent_post_id = parent.id
"""


MIGRATE_VOTES_TO_REACTIONS = """
    INSERT INTO reactions(post_id, author_id, reaction, submission_time)
    SELECT v.object_id, v.voter_id, 
        CASE v.type_of_vote WHEN 1 THEN '👍' WHEN 2 THEN '👎' END, 
        v.submission_time
    FROM votes v
    WHERE v.content_type_id = 8;
"""