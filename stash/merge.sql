-- Update user_id in gchat_users
WITH user_with_merge_key as (
    SELECT u.id as id, u.email, replace(substring(u.email, 0, position('@' in u.email)), '.', '') as merge_key 
    FROM users u JOIN social_auth_usersocialauth sa on u.id = sa.user_id
    WHERE u.email != ''
),
gchat_users_with_same_name as (
    select g.display_name from gchat_users g group by g.display_name having count(*) > 1
)
UPDATE gchat_users g
SET user_id = um.id
FROM user_with_merge_key um 
WHERE replace(lower(g.display_name), ' ', '') = um.merge_key
AND g.user_id is null and g.display_name not in (
  SELECT display_name from gchat_users_with_same_name
);

-- gchat_users that are associated to a charcha user
SELECT g.display_name, u.email 
FROM gchat_users g join users u on g.user_id = u.id

-- This query shows unassociated users and several possible matches
-- Select the match that makes most sense, and copy the entire line as an update statement
WITH orphan_users as (
    SELECT u.id, u.email, u.last_login
    FROM users u join social_auth_usersocialauth sa on u.id = sa.user_id
    WHERE NOT EXISTS (select 'x' from gchat_users g where g.user_id = u.id)
), user_name_tokens as (
    SELECT u.id, s.token as token
    FROM users u, unnest(string_to_array(substring(u.email, 0, position('@' in u.email)), '.')) s(token)
    WHERE length(s.token) > 3
)
SELECT DISTINCT '/*', ou.email as email, g.display_name as gchat_display_name, ou.last_login, 
'*/ UPDATE gchat_users set user_id = ' || ou.id || ' WHERE id = ' || g.id || ';'
FROM gchat_users g, orphan_users ou JOIN user_name_tokens unt on ou.id = unt.id
WHERE lower(g.display_name) like '%' || unt.token || '%'
ORDER by ou.last_login DESC;


-- Posts I am allowed to see, along with author details and all teams the post belongs to
WITH post_teams as (
    SELECT tp.post_id as post_id, json_agg(t.*) as teams
    FROM team_posts tp JOIN (SELECT id, name FROM teams) t on tp.team_id = t.id
    GROUP BY tp.post_id
)
SELECT p.id, p.title, 
    p.upvotes, p.downvotes, p.flags,
    (p.upvotes - p.downvotes) as score, 
    p.title, p.html, p.submission_time, p.num_comments, 
    json_build_object('id', a.id, 'username', a.username) as author,
    pt.teams 
FROM posts p JOIN users a on p.author_id = a.id
    JOIN post_teams pt on p.id = pt.post_id
WHERE EXISTS (
    SELECT 'x' FROM team_posts tp JOIN team_members tm ON tp.team_id = tm.team_id
    WHERE tm.gchat_user_id = (select g.id from gchat_users g where g.user_id = 1) 
    and tp.post_id = p.id
)
ORDER BY p.submission_time DESC
LIMIT 100;


-- Can I view this post?
SELECT 'x' FROM posts p
WHERE EXISTS (
    SELECT 'x' FROM team_posts tp JOIN team_members tm on tp.team_id = tm.team_id
        WHERE tp.post_id = p.id AND tm.gchat_user_id = (
            SELECT id from gchat_users where user_id = 1
        )
)
AND p.id = 133;




SELECT t.name as "Team Name", g.display_name as "Gchat Name", u.email as "Email"


-- Active users in  this team in last 7 days
WITH last_activity as (
  SELECT rs.team_id, rs.user_id, max(rs.submission_time) as last_activity FROM (
    SELECT tp.team_id, p.author_id as user_id, p.submission_time
    FROM team_posts tp JOIN posts p on tp.post_id = p.id
    WHERE p.submission_time > 'now'::timestamp - '7 days'::interval
    UNION ALL
    SELECT tp.team_id, c.author_id as user_id, c.submission_time
    FROM team_posts tp JOIN posts p on tp.post_id = p.id
        JOIN comments c on p.id = c.post_id
    WHERE c.submission_time > 'now'::timestamp - '7 days'::interval
  ) rs
  GROUP BY rs.team_id, rs.user_id
)
SELECT u.id as user_id, u.username as username, 
u.first_name || ' ' || u.last_name as display_name, u.avatar as avatar
FROM last_activity la JOIN users u on la.user_id = u.id
WHERE la.team_id = 2
ORDER BY la.last_activity DESC;
