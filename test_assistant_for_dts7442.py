#!/usr/bin/env python3
"""
DTS-7442 WebSocket @功能测试辅助工具
专门为群消息@功能设计的智能测试生成器
"""

import json
import random
import string
from typing import List, Dict, Any
from datetime import datetime

class UserRelation:
    """模拟 com.bx.implatform.dto.UserRelation"""
    def __init__(self, user_id: str, relation_type: str = "mention"):
        self.userId = user_id
        self.relationType = relation_type  # mention, reply, etc.
        self.timestamp = datetime.now().isoformat()

class WebSocketAtTestGenerator:
    """WebSocket @功能测试用例生成器"""
    
    def __init__(self):
        self.test_users = [
            "user001", "user002", "user003", "admin001", 
            "test_user", "guest001", "manager001", "dev001"
        ]
    
    def generate_test_data(self) -> Dict[str, Any]:
        """生成各种测试场景的数据"""
        
        test_scenarios = {
            "正常场景": {
                "single_user": self._create_message_with_at([self.test_users[0]]),
                "multiple_users": self._create_message_with_at(self.test_users[:3]),
                "max_users": self._create_message_with_at(self.test_users)
            },
            
            "边界测试": {
                "empty_at_list": self._create_message_with_at([]),
                "duplicate_users": self._create_message_with_at([self.test_users[0], self.test_users[0]]),
                "invalid_user_id": self._create_message_with_at(["", "null", "undefined"])
            },
            
            "异常场景": {
                "null_at_users": self._create_message_with_at(None),
                "wrong_data_type": {
                    "messageId": self._generate_id(),
                    "content": "测试消息",
                    "atUsers": "not_a_list"  # 错误的数据类型
                },
                "oversized_list": self._create_message_with_at([f"user{i}" for i in range(1000)])
            }
        }
        
        return test_scenarios
    
    def _create_message_with_at(self, user_ids: List[str] = None) -> Dict[str, Any]:
        """创建包含@用户的消息"""
        if user_ids is None:
            at_users = None
        else:
            at_users = [
                {
                    "userId": uid,
                    "relationType": "mention",
                    "timestamp": datetime.now().isoformat()
                } for uid in user_ids if uid  # 过滤空字符串
            ]
        
        return {
            "messageId": self._generate_id(),
            "groupId": "group_" + self._generate_id(),
            "senderId": "sender_" + self._generate_id(),
            "content": f"这是一条测试消息 {datetime.now()}",
            "atUsers": at_users,
            "messageType": "text",
            "timestamp": datetime.now().isoformat()
        }
    
    def _generate_id(self) -> str:
        """生成随机ID"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    def generate_websocket_test_script(self) -> str:
        """生成WebSocket测试脚本"""
        
        script = """
# WebSocket @功能测试脚本
# 针对 DTS-7442: websocket群消息增加@功能并存储

import websockets
import asyncio
import json
from datetime import datetime

class WebSocketAtTester:
    def __init__(self, ws_url="ws://localhost:8080/chat"):
        self.ws_url = ws_url
        self.connection = None
    
    async def connect(self):
        self.connection = await websockets.connect(self.ws_url)
        print(f"✅ 连接到 {self.ws_url}")
    
    async def send_message_with_at(self, message_data):
        \"\"\"发送带@的消息\"\"\"
        if not self.connection:
            await self.connect()
        
        await self.connection.send(json.dumps(message_data))
        print(f"📤 发送消息: {message_data['content']}")
        print(f"👥 @用户: {[u['userId'] for u in message_data.get('atUsers', [])]}")
        
        # 等待响应
        response = await self.connection.recv()
        return json.loads(response)
    
    async def test_scenarios(self):
        \"\"\"执行所有测试场景\"\"\"
        test_data = """ + json.dumps(self.generate_test_data(), indent=8) + """
        
        results = {}
        
        for category, scenarios in test_data.items():
            print(f"\\n🧪 测试类别: {category}")
            results[category] = {}
            
            for scenario_name, message_data in scenarios.items():
                try:
                    print(f"  🔬 执行: {scenario_name}")
                    response = await self.send_message_with_at(message_data)
                    results[category][scenario_name] = {
                        "success": True,
                        "response": response,
                        "message": "测试通过"
                    }
                    print(f"    ✅ 成功")
                except Exception as e:
                    results[category][scenario_name] = {
                        "success": False,
                        "error": str(e),
                        "message": f"测试失败: {e}"
                    }
                    print(f"    ❌ 失败: {e}")
        
        return results

# 使用示例
async def main():
    tester = WebSocketAtTester()
    try:
        results = await tester.test_scenarios()
        
        # 生成测试报告
        print("\\n📊 测试报告总结:")
        total_tests = sum(len(scenarios) for scenarios in results.values())
        passed_tests = sum(
            sum(1 for result in scenarios.values() if result.get('success'))
            for scenarios in results.values()
        )
        
        print(f"总测试数: {total_tests}")
        print(f"通过: {passed_tests}")
        print(f"失败: {total_tests - passed_tests}")
        print(f"成功率: {passed_tests/total_tests*100:.1f}%")
        
        # 保存详细报告
        with open('websocket_at_test_report.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("\\n📄 详细报告已保存到 websocket_at_test_report.json")
        
    finally:
        if tester.connection:
            await tester.connection.close()

if __name__ == "__main__":
    asyncio.run(main())
"""
        return script
    
    def generate_database_validation_sql(self) -> List[str]:
        """生成数据库验证SQL"""
        
        sqls = [
            # 检查表结构
            "DESCRIBE messages;",
            "SHOW CREATE TABLE messages;",
            
            # 检查atUsers字段
            "SELECT * FROM messages WHERE at_users IS NOT NULL LIMIT 10;",
            
            # 验证JSON数据结构
            """
            SELECT 
                message_id,
                JSON_EXTRACT(at_users, '$[*].userId') as user_ids,
                JSON_EXTRACT(at_users, '$[*].relationType') as relation_types,
                JSON_LENGTH(at_users) as at_count
            FROM messages 
            WHERE at_users IS NOT NULL;
            """,
            
            # 统计@功能使用情况
            """
            SELECT 
                COUNT(*) as total_messages,
                COUNT(CASE WHEN at_users IS NOT NULL THEN 1 END) as messages_with_at,
                AVG(JSON_LENGTH(at_users)) as avg_at_count
            FROM messages;
            """,
            
            # 检查数据完整性
            """
            SELECT message_id, at_users 
            FROM messages 
            WHERE at_users IS NOT NULL 
            AND JSON_VALID(at_users) = 0;  -- 检查无效JSON
            """
        ]
        
        return sqls

def main():
    """生成测试辅助工具"""
    generator = WebSocketAtTestGenerator()
    
    print("🎯 DTS-7442 WebSocket @功能测试辅助工具")
    print("=" * 50)
    
    # 1. 生成测试数据
    print("📋 1. 生成测试数据...")
    test_data = generator.generate_test_data()
    with open('dts7442_test_data.json', 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)
    print("✅ 测试数据已保存到 dts7442_test_data.json")
    
    # 2. 生成WebSocket测试脚本
    print("📋 2. 生成WebSocket测试脚本...")
    script = generator.generate_websocket_test_script()
    with open('websocket_at_test.py', 'w', encoding='utf-8') as f:
        f.write(script)
    print("✅ WebSocket测试脚本已保存到 websocket_at_test.py")
    
    # 3. 生成数据库验证SQL
    print("📋 3. 生成数据库验证SQL...")
    sqls = generator.generate_database_validation_sql()
    with open('dts7442_db_validation.sql', 'w', encoding='utf-8') as f:
        for i, sql in enumerate(sqls, 1):
            f.write(f"-- 验证 #{i}: \n{sql}\n\n")
    print("✅ 数据库验证SQL已保存到 dts7442_db_validation.sql")
    
    print("\n🎉 测试辅助工具生成完成!")
    print("📁 生成的文件:")
    print("  - dts7442_test_data.json (测试数据)")
    print("  - websocket_at_test.py (WebSocket测试脚本)")
    print("  - dts7442_db_validation.sql (数据库验证SQL)")

if __name__ == "__main__":
    main()
