#!/usr/bin/env python
"""
测试LM Studio MCP客户端的简单示例
"""
import asyncio
import os
import sys

# 添加当前目录到路径
# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pdf_translator.mcp_server import LMStudioClient


async def test_client():
    """测试LM Studio客户端"""
    # 从环境变量或使用默认值
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
    model = os.getenv("LM_STUDIO_MODEL", "openai/gpt-oss-20b")
    
    print(f"连接到LM Studio: {base_url}")
    print(f"使用模型: {model}")
    print("-" * 50)
    
    client = LMStudioClient(base_url=base_url, model=model)
    
    try:
        # 测试1: 列出可用模型
        print("\n[测试1] 列出可用模型...")
        try:
            models = await client.list_models()
            print("可用模型:")
            if "data" in models:
                for model_info in models["data"]:
                    print(f"  - {model_info.get('id', 'N/A')}")
            else:
                print(f"响应: {models}")
        except Exception as e:
            print(f"错误: {e}")
        
        # 测试2: 聊天完成
        print("\n[测试2] 聊天完成...")
        try:
            response = await client.chat_completion(
                messages=[
                    {"role": "user", "content": "你好，请用一句话介绍Python编程语言。"}
                ],
                temperature=0.7,
                max_tokens=100
            )
            print("响应:")
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
                print(f"  内容: {content}")
            else:
                print(f"  完整响应: {response}")
        except Exception as e:
            print(f"错误: {e}")
        
        # 测试3: 文本完成
        print("\n[测试3] 文本完成...")
        try:
            response = await client.completion(
                prompt="Python是一种",
                temperature=0.7,
                max_tokens=50
            )
            print("响应:")
            if "choices" in response and len(response["choices"]) > 0:
                text = response["choices"][0].get("text", "")
                print(f"  文本: {text}")
            else:
                print(f"  完整响应: {response}")
        except Exception as e:
            print(f"错误: {e}")
        
    finally:
        await client.close()
        print("\n" + "-" * 50)
        print("测试完成")


if __name__ == "__main__":
    print("LM Studio MCP客户端测试")
    print("=" * 50)
    asyncio.run(test_client())

