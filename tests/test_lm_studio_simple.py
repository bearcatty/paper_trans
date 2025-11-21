#!/usr/bin/env python
"""
简单的 LM Studio 测试脚本
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pdf_translator.mcp_server import LMStudioClient

async def main():
    """测试 LM Studio 连接和功能"""
    print("=" * 60)
    print("LM Studio 功能测试")
    print("=" * 60)
    
    # 创建客户端
    client = LMStudioClient(
        base_url="http://127.0.0.1:1234",
        model="openai/gpt-oss-20b"
    )
    
    try:
        # 测试1: 列出模型
        print("\n[测试1] 列出可用模型")
        print("-" * 60)
        models = await client.list_models()
        if "data" in models:
            print(f"找到 {len(models['data'])} 个模型:")
            for model_info in models["data"]:
                print(f"  ✓ {model_info.get('id', 'N/A')}")
        else:
            print(f"响应: {models}")
        
        # 测试2: 聊天完成
        print("\n[测试2] 聊天完成测试")
        print("-" * 60)
        print("问题: 你好，请用一句话介绍Python编程语言。")
        response = await client.chat_completion(
            messages=[
                {"role": "user", "content": "你好，请用一句话介绍Python编程语言。"}
            ],
            temperature=0.7,
            max_tokens=100
        )
        if "choices" in response and len(response["choices"]) > 0:
            content = response["choices"][0].get("message", {}).get("content", "")
            print(f"回答: {content}")
        else:
            print(f"完整响应: {response}")
        
        # 测试3: 文本完成
        print("\n[测试3] 文本完成测试")
        print("-" * 60)
        print("提示: Python是一种")
        response = await client.completion(
            prompt="Python是一种",
            temperature=0.7,
            max_tokens=50
        )
        if "choices" in response and len(response["choices"]) > 0:
            text = response["choices"][0].get("text", "")
            print(f"完成: {text}")
        else:
            print(f"完整响应: {response}")
        
        print("\n" + "=" * 60)
        print("✓ 所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())

