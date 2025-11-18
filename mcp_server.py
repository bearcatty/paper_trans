#!/usr/bin/env python
"""
MCP Server for LM Studio
封装LM Studio API调用，提供统一的模型服务接口
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    Tool,
    TextContent,
)

# 配置
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "openai/gpt-oss-20b")
DEFAULT_TIMEOUT = 120.0  # 秒

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建MCP服务器实例
server = Server("lm-studio-mcp-server")


class LMStudioClient:
    """LM Studio API客户端"""
    
    def __init__(self, base_url: str = LM_STUDIO_BASE_URL, model: str = LM_STUDIO_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
    
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """
        调用聊天完成API
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数，控制随机性
            max_tokens: 最大token数
            stream: 是否流式返回
        
        Returns:
            API响应字典
        """
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stream:
            payload["stream"] = True
        
        logger.info(f"Calling LM Studio API: {url} with model {self.model}")
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling LM Studio: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling LM Studio: {e}")
            raise
    
    async def completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        调用文本完成API（兼容OpenAI格式）
        
        Args:
            prompt: 输入提示
            temperature: 温度参数
            max_tokens: 最大token数
        
        Returns:
            API响应字典
        """
        url = f"{self.base_url}/v1/completions"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        logger.info(f"Calling LM Studio completion API: {url}")
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling LM Studio: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling LM Studio: {e}")
            raise
    
    async def list_models(self) -> dict[str, Any]:
        """列出可用的模型"""
        url = f"{self.base_url}/v1/models"
        logger.info(f"Listing models from: {url}")
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error listing models: {e}")
            raise
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()


# 全局客户端实例
lm_client: Optional[LMStudioClient] = None


def get_client() -> LMStudioClient:
    """获取或创建LM Studio客户端实例"""
    global lm_client
    if lm_client is None:
        base_url = os.getenv("LM_STUDIO_BASE_URL", LM_STUDIO_BASE_URL)
        model = os.getenv("LM_STUDIO_MODEL", LM_STUDIO_MODEL)
        lm_client = LMStudioClient(base_url=base_url, model=model)
    return lm_client


@server.list_tools()
async def list_tools(request: ListToolsRequest) -> ListToolsResult:
    """列出可用的工具"""
    tools = [
        Tool(
            name="chat_completion",
            description="调用LM Studio进行聊天完成。输入消息列表，返回模型回复。",
            inputSchema={
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                "content": {"type": "string"},
                            },
                            "required": ["role", "content"],
                        },
                        "description": "消息列表，格式为 [{\"role\": \"user\", \"content\": \"...\"}]",
                    },
                    "temperature": {
                        "type": "number",
                        "default": 0.7,
                        "description": "温度参数，控制输出的随机性 (0-2)",
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "最大生成token数",
                    },
                },
                "required": ["messages"],
            },
        ),
        Tool(
            name="text_completion",
            description="调用LM Studio进行文本完成。输入提示文本，返回模型生成的文本。",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "输入提示文本",
                    },
                    "temperature": {
                        "type": "number",
                        "default": 0.7,
                        "description": "温度参数，控制输出的随机性 (0-2)",
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "最大生成token数",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="list_models",
            description="列出LM Studio服务器上可用的模型列表",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]
    return ListToolsResult(tools=tools)


@server.call_tool()
async def call_tool(request: CallToolRequest) -> CallToolResult:
    """调用工具"""
    client = get_client()
    
    try:
        if request.name == "chat_completion":
            messages = request.arguments.get("messages", [])
            temperature = request.arguments.get("temperature", 0.7)
            max_tokens = request.arguments.get("max_tokens")
            
            result = await client.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            # 提取回复内容
            content = ""
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0].get("message", {}).get("content", "")
            
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(result, ensure_ascii=False, indent=2),
                    )
                ],
                isError=False,
            )
        
        elif request.name == "text_completion":
            prompt = request.arguments.get("prompt", "")
            temperature = request.arguments.get("temperature", 0.7)
            max_tokens = request.arguments.get("max_tokens")
            
            result = await client.completion(
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(result, ensure_ascii=False, indent=2),
                    )
                ],
                isError=False,
            )
        
        elif request.name == "list_models":
            result = await client.list_models()
            
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(result, ensure_ascii=False, indent=2),
                    )
                ],
                isError=False,
            )
        
        else:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"Unknown tool: {request.name}",
                    )
                ],
                isError=True,
            )
    
    except Exception as e:
        logger.error(f"Error calling tool {request.name}: {e}", exc_info=True)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Error: {str(e)}",
                )
            ],
            isError=True,
        )


async def main():
    """主函数：启动MCP服务器"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())

