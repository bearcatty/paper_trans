#!/usr/bin/env python
"""
使用LM Studio MCP客户端的示例
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pdf_translator.mcp_server import LMStudioClient


async def example_chat():
    """聊天示例"""
    client = LMStudioClient()
    
    try:
        # 多轮对话
        messages = [
            {"role": "system", "content": "你是一个有用的AI助手。"},
            {"role": "user", "content": "什么是机器学习？"}
        ]
        
        response = await client.chat_completion(messages=messages)
        
        if "choices" in response:
            assistant_message = response["choices"][0]["message"]["content"]
            print("助手:", assistant_message)
            
            # 继续对话
            messages.append({"role": "assistant", "content": assistant_message})
            messages.append({"role": "user", "content": "能给我一个简单的例子吗？"})
            
            response = await client.chat_completion(messages=messages)
            if "choices" in response:
                print("\n助手:", response["choices"][0]["message"]["content"])
    
    finally:
        await client.close()


async def example_completion():
    """文本完成示例"""
    client = LMStudioClient()
    
    try:
        prompt = "人工智能的发展历史可以追溯到"
        response = await client.completion(prompt=prompt, max_tokens=100)
        
        if "choices" in response:
            completed_text = response["choices"][0]["text"]
            print(f"完成文本: {prompt}{completed_text}")
    
    finally:
        await client.close()


if __name__ == "__main__":
    print("=" * 50)
    print("示例1: 聊天完成")
    print("=" * 50)
    asyncio.run(example_chat())
    
    print("\n" + "=" * 50)
    print("示例2: 文本完成")
    print("=" * 50)
    asyncio.run(example_completion())

