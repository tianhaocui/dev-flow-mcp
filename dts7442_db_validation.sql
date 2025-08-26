-- 验证 #1: 
DESCRIBE messages;

-- 验证 #2: 
SHOW CREATE TABLE messages;

-- 验证 #3: 
SELECT * FROM messages WHERE at_users IS NOT NULL LIMIT 10;

-- 验证 #4: 

            SELECT 
                message_id,
                JSON_EXTRACT(at_users, '$[*].userId') as user_ids,
                JSON_EXTRACT(at_users, '$[*].relationType') as relation_types,
                JSON_LENGTH(at_users) as at_count
            FROM messages 
            WHERE at_users IS NOT NULL;
            

-- 验证 #5: 

            SELECT 
                COUNT(*) as total_messages,
                COUNT(CASE WHEN at_users IS NOT NULL THEN 1 END) as messages_with_at,
                AVG(JSON_LENGTH(at_users)) as avg_at_count
            FROM messages;
            

-- 验证 #6: 

            SELECT message_id, at_users 
            FROM messages 
            WHERE at_users IS NOT NULL 
            AND JSON_VALID(at_users) = 0;  -- 检查无效JSON
            

