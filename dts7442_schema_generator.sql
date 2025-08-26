-- DTS-7442 数据库表结构生成器
-- 为WebSocket群消息@功能设计的表结构

-- 1. 创建消息表（如果不存在）
CREATE TABLE IF NOT EXISTS `messages` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `message_id` VARCHAR(64) NOT NULL UNIQUE COMMENT '消息唯一标识',
    `group_id` VARCHAR(64) NOT NULL COMMENT '群组ID',
    `sender_id` VARCHAR(64) NOT NULL COMMENT '发送者ID', 
    `content` TEXT NOT NULL COMMENT '消息内容',
    `message_type` VARCHAR(32) NOT NULL DEFAULT 'text' COMMENT '消息类型',
    `at_users` JSON NULL COMMENT '@用户列表，List<UserRelation>',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_group_id` (`group_id`),
    INDEX `idx_sender_id` (`sender_id`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='群消息表-支持@功能';

-- 2. 创建@通知表（用于追踪通知状态）
CREATE TABLE IF NOT EXISTS `message_notifications` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `message_id` VARCHAR(64) NOT NULL COMMENT '消息ID',
    `target_user_id` VARCHAR(64) NOT NULL COMMENT '被@的用户ID',
    `relation_type` VARCHAR(32) NOT NULL DEFAULT 'mention' COMMENT '关系类型',
    `notification_status` ENUM('pending', 'sent', 'read', 'failed') NOT NULL DEFAULT 'pending',
    `sent_at` TIMESTAMP NULL COMMENT '推送时间',
    `read_at` TIMESTAMP NULL COMMENT '阅读时间',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_message_id` (`message_id`),
    INDEX `idx_target_user_id` (`target_user_id`),
    INDEX `idx_status` (`notification_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='@通知状态追踪表';

-- 3. 示例数据插入（用于测试）
INSERT INTO `messages` (`message_id`, `group_id`, `sender_id`, `content`, `message_type`, `at_users`) VALUES
('msg001', 'group_test', 'user_sender', '大家好！@user001 @user002 请查看这个问题', 'text', 
 JSON_ARRAY(
     JSON_OBJECT('userId', 'user001', 'relationType', 'mention', 'timestamp', NOW()),
     JSON_OBJECT('userId', 'user002', 'relationType', 'mention', 'timestamp', NOW())
 )),
('msg002', 'group_test', 'user_sender', '测试空@列表', 'text', JSON_ARRAY()),
('msg003', 'group_test', 'user_sender', '普通消息无@', 'text', NULL);

-- 4. 测试查询语句
SELECT 'DTS-7442 测试查询集合' as test_suite;

-- 4.1 验证@用户数据结构
SELECT 
    message_id,
    content,
    JSON_EXTRACT(at_users, '$[*].userId') as mentioned_users,
    JSON_LENGTH(at_users) as mention_count
FROM messages 
WHERE at_users IS NOT NULL AND JSON_LENGTH(at_users) > 0;

-- 4.2 统计@功能使用情况  
SELECT 
    COUNT(*) as total_messages,
    COUNT(CASE WHEN at_users IS NOT NULL AND JSON_LENGTH(at_users) > 0 THEN 1 END) as messages_with_mentions,
    ROUND(
        COUNT(CASE WHEN at_users IS NOT NULL AND JSON_LENGTH(at_users) > 0 THEN 1 END) * 100.0 / COUNT(*), 
        2
    ) as mention_usage_percentage
FROM messages;

-- 4.3 检查数据完整性
SELECT 
    message_id,
    'Invalid JSON' as issue
FROM messages 
WHERE at_users IS NOT NULL AND JSON_VALID(at_users) = 0
UNION ALL
SELECT 
    message_id,
    'Empty userId' as issue  
FROM messages 
WHERE JSON_SEARCH(at_users, 'one', '') IS NOT NULL;

-- 4.4 性能测试查询
SELECT 
    message_id,
    group_id,
    JSON_EXTRACT(at_users, '$[*].userId') as users
FROM messages 
WHERE JSON_CONTAINS(at_users, JSON_OBJECT('userId', 'user001'))
LIMIT 100;

-- 5. 清理测试数据（可选执行）
-- DELETE FROM messages WHERE message_id IN ('msg001', 'msg002', 'msg003');
