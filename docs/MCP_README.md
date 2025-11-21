# LM Studio MCP Server

这是一个封装 LM Studio API 的 MCP（Model Context Protocol）服务器，允许你通过标准化的 MCP 协议与本地部署的 LM Studio 模型进行交互。

## 功能特性

- ✅ 封装 LM Studio 的 OpenAI 兼容 API
- ✅ 支持聊天完成（Chat Completion）
- ✅ 支持文本完成（Text Completion）
- ✅ 支持列出可用模型
- ✅ 可配置的服务器地址和模型名称
- ✅ 完整的错误处理和日志记录

## 安装

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 确保 LM Studio 服务器正在运行：
   - 启动 LM Studio 应用
   - 加载模型 `openai/gpt-oss-20b`
   - 启动本地服务器（默认地址：http://127.0.0.1:1234）

## 配置

### 环境变量

可以通过环境变量配置服务器地址和模型：

```bash
export LM_STUDIO_BASE_URL="http://127.0.0.1:1234"
export LM_STUDIO_MODEL="openai/gpt-oss-20b"
```

或者在代码中直接修改 `mcp_server.py` 中的默认值。

### MCP 客户端配置

如果你使用支持 MCP 的客户端（如 Claude Desktop），可以在配置文件中添加：

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "lm-studio": {
      "command": "python",
      "args": [
        "/Users/bytedance/work/author_parser/pdf_translator/mcp_server.py"
      ],
      "env": {
        "LM_STUDIO_BASE_URL": "http://127.0.0.1:1234",
        "LM_STUDIO_MODEL": "openai/gpt-oss-20b"
      }
    }
  }
}
```

## 使用方法

### 1. 直接运行 MCP 服务器

```bash
python -m pdf_translator.mcp_server
```

服务器将通过 stdio 进行通信，这是 MCP 协议的标准方式。

### 2. 在 Python 代码中使用

```python
import asyncio
from pdf_translator.mcp_server import LMStudioClient

async def main():
    client = LMStudioClient(
        base_url="http://127.0.0.1:1234",
        model="openai/gpt-oss-20b"
    )

    # 聊天完成
    response = await client.chat_completion(
        messages=[
            {"role": "user", "content": "你好，请介绍一下自己"}
        ],
        temperature=0.7
    )
    print(response)

    # 文本完成
    response = await client.completion(
        prompt="Python是一种",
        temperature=0.7
    )
    print(response)

    # 列出模型
    models = await client.list_models()
    print(models)

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. 通过 MCP 工具调用

MCP 服务器提供了以下工具：

#### `chat_completion`

进行聊天完成，支持多轮对话。

参数：

- `messages` (必需): 消息列表，格式为 `[{"role": "user", "content": "..."}]`
- `temperature` (可选): 温度参数，默认 0.7
- `max_tokens` (可选): 最大生成 token 数

#### `text_completion`

进行文本完成，适合单次提示。

参数：

- `prompt` (必需): 输入提示文本
- `temperature` (可选): 温度参数，默认 0.7
- `max_tokens` (可选): 最大生成 token 数

#### `list_models`

列出 LM Studio 服务器上可用的模型。

## API 参考

### LMStudioClient

#### `__init__(base_url: str, model: str)`

初始化客户端。

- `base_url`: LM Studio 服务器地址，默认 `http://127.0.0.1:1234`
- `model`: 模型名称，默认 `openai/gpt-oss-20b`

#### `chat_completion(messages, temperature=0.7, max_tokens=None, stream=False)`

调用聊天完成 API。

#### `completion(prompt, temperature=0.7, max_tokens=None)`

调用文本完成 API。

#### `list_models()`

列出可用模型。

#### `close()`

关闭客户端连接。

## 故障排除

### 连接错误

- 确保 LM Studio 服务器正在运行
- 检查服务器地址是否正确（默认：http://127.0.0.1:1234）
- 确认模型已加载

### 模型不存在

- 检查模型名称是否正确
- 使用 `list_models` 工具查看可用模型
- 在 LM Studio 中确认模型已正确加载

### 超时错误

- 增加 `DEFAULT_TIMEOUT` 值（在代码中）
- 检查网络连接
- 确认 LM Studio 服务器响应正常

## 开发

### 项目结构

```
author_parser/
├── pdf_translator/
│   └── mcp_server.py      # MCP服务器主文件
├── data/                  # 数据文件
├── docs/
│   └── MCP_README.md      # 本文档
└── requirements.txt       # Python依赖
```

### 扩展功能

你可以轻松扩展 MCP 服务器以支持更多功能：

1. 添加新的工具：在 `list_tools()` 中添加新的 `Tool` 定义
2. 添加新的 API 方法：在 `LMStudioClient` 类中添加新方法
3. 添加资源：实现 `list_resources()` 和 `read_resource()` 处理器

## 许可证

与主项目保持一致。
