#!/usr/bin/env python
"""
直接测试 MCP 服务器的功能
"""
import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_mcp_server():
    """测试 MCP 服务器"""
    server_params = StdioServerParameters(
        command="python",
        args=["/Users/bytedance/work/author_parser/mcp_server.py"],
        env={
            "LM_STUDIO_BASE_URL": "http://127.0.0.1:1234",
            "LM_STUDIO_MODEL": "openai/gpt-oss-20b"
        }
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化
            await session.initialize()
            
            # 测试1: 列出工具
            print("=" * 50)
            print("测试1: 列出可用工具")
            print("=" * 50)
            tools = await session.list_tools()
            print(f"可用工具数量: {len(tools.tools)}")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # 测试2: 调用聊天完成
            print("\n" + "=" * 50)
            print("测试2: 聊天完成")
            print("=" * 50)
            result = await session.call_tool(
                "chat_completion",
                arguments={
                    "messages": [
                        {"role": "user", "content": "你好，请用一句话介绍Python编程语言。"}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 100
                }
            )
            print("响应:")
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
                    else:
                        print(json.dumps(content, indent=2, ensure_ascii=False))
            
            # 测试3: 调用文本完成
            print("\n" + "=" * 50)
            print("测试3: 文本完成")
            print("=" * 50)
            result = await session.call_tool(
                "text_completion",
                arguments={
                    "prompt": "Python是一种",
                    "temperature": 0.7,
                    "max_tokens": 50
                }
            )
            print("响应:")
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
                    else:
                        print(json.dumps(content, indent=2, ensure_ascii=False))
            
            # 测试4: 列出模型
            print("\n" + "=" * 50)
            print("测试4: 列出模型")
            print("=" * 50)
            result = await session.call_tool(
                "list_models",
                arguments={}
            )
            print("响应:")
            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
                    else:
                        print(json.dumps(content, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    print("MCP 服务器直接测试")
    print("=" * 50)
    try:
        asyncio.run(test_mcp_server())
        print("\n" + "=" * 50)
        print("测试完成！")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

