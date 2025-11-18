# PDF翻译工具使用说明

这个工具使用LM Studio MCP服务将PDF文件从英文翻译成中文，并可输出新的PDF或Markdown文档。

## 功能特性

- ✅ 自动提取PDF文件中的文本内容
- ✅ 智能分块处理长文本，避免超出模型token限制
- ✅ 使用LM Studio本地大模型进行翻译
- ✅ 保留原文中的图表/表格图像并插入译文
- ✅ 可选择输出PDF或Markdown（便于二次排版）
- ✅ 翻译完成后自动触发 LLM 质量审校与修复
- ✅ 保持原文格式和结构
- ✅ 生成新的中文PDF文件
- ✅ 断点续译，翻译进度自动缓存

## 安装依赖

首先确保已安装所有依赖：

```bash
pip install -r requirements.txt
```

主要依赖包括：
- `PyMuPDF` (fitz) - 用于PDF文本提取
- `reportlab` - 用于生成新的PDF文件
- `mcp` - MCP协议支持
- `httpx` - HTTP客户端

## 使用前准备

1. **启动LM Studio服务器**
   - 打开LM Studio应用
   - 加载模型（默认：`openai/gpt-oss-20b`）
   - 启动本地服务器（默认地址：http://127.0.0.1:1234）

2. **配置环境变量（可选）**
   ```bash
   export LM_STUDIO_BASE_URL="http://127.0.0.1:1234"
   export LM_STUDIO_MODEL="openai/gpt-oss-20b"
   ```

## 使用方法

### 基本用法

```bash
python pdf_translator.py input.pdf
```

这会将 `input.pdf` 翻译成中文，并生成 `input_translated.pdf` 文件。

### 指定输出文件

```bash
python pdf_translator.py input.pdf -o output.pdf
```

### 生成 Markdown

```bash
python pdf_translator.py input.pdf --format md
```

这会在同目录生成 `input_translated.md` 与 `input_translated_assets/` 图像目录，方便在笔记或知识库中继续编辑。

### 自定义LM Studio配置

```bash
python pdf_translator.py input.pdf \
  --base-url http://127.0.0.1:1234 \
  --model your-model-name
```

### 调整翻译块大小

如果遇到翻译质量问题，可以调整块大小：

```bash
python pdf_translator.py input.pdf --chunk-size 1500
```

较小的块大小可以提高翻译质量，但会增加API调用次数。

### 断点续译

翻译时会在输出目录生成 `*_translated.<格式>.cache.json` 文件，记录每一页、每个块的翻译进度。脚本再次运行同一输入/输出文件时，会自动从缓存恢复并跳过已完成的部分。翻译成功生成最终文档后，缓存会被自动删除；若希望重新翻译，可手动删除该缓存文件。

### 图表与表格保留

- PyMuPDF 会提取每页中的原始位图（包括图表、表格快照等），译文 PDF 在对应页尾插入这些图像以保留可视化信息。
- 图表/表格标题、脚注等文本会与正文一起翻译，确保说明信息同步更新。
- 目前仍无法对矢量表格进行结构化重建，如需后续编辑，可参考译文中的说明并回到原文查阅。

### 智能质量审校

- 每个文本块翻译完成后，脚本会运行启发式检查（例如英文占比、是否未翻译、是否带提示词）。
- 若检测到问题，会再调用一次 LLM 进行针对性修复，最多尝试 3 次，确保最终输出为纯中文、结构清晰。
- 若仍未完全消除问题，日志中会给出警告，方便手动复查。

## 参数说明

- `input_pdf`: 输入的PDF文件路径（必需）
- `-o, --output`: 输出文件路径（可选，根据 `--format` 自动补齐扩展名）
- `--base-url`: LM Studio服务器地址（默认：http://127.0.0.1:1234）
- `--model`: 使用的模型名称（默认：openai/gpt-oss-20b）
- `--chunk-size`: 翻译块大小，单位字符（默认：2000）
- `--format`: 输出格式，`pdf` 或 `md`（默认：pdf）

## 工作流程

1. **提取文本**：使用PyMuPDF从PDF中提取所有页面的文本内容
2. **分块处理**：将长文本智能分割成适合翻译的块
3. **翻译**：使用LM Studio API逐块翻译文本
4. **生成文档**：根据 `--format` 生成 PDF 或 Markdown，Markdown 会同步导出所有图像资源

## 注意事项

1. **中文字体支持**：工具会尝试自动检测和注册系统中文字体。如果PDF中中文显示异常，可能需要手动安装中文字体。

2. **翻译质量**：翻译质量取决于使用的模型。建议使用支持中英文翻译的模型。

3. **处理时间**：翻译时间取决于PDF大小和模型速度。大文件可能需要较长时间。

4. **格式保持**：工具会尽量保持原文的段落结构，但复杂的排版（如表格、图片等）可能无法完全保留。

5. **API限流**：工具在翻译块之间添加了延迟，避免API限流。如果遇到限流问题，可以增加延迟时间。

6. **缓存文件**：若翻译被中断，可保留缓存文件以便下次续传；若要重新翻译，请删除对应的 `*.cache.json`。

7. **图像数量**：当单页包含大量图像时，译文页尾（PDF）或 Markdown 将顺序插入所有图像，可能导致篇幅增加。可根据需要手动删减。
8. **Markdown 资源目录**：生成 Markdown 时会在同级目录创建 `<文件名>_assets/`，路径会自动清理空格和特殊字符。移动 Markdown 文件时别忘了同时移动该目录。

## 示例

```bash
# 翻译一个PDF文件
python pdf_translator.py document.pdf

# 指定输出文件名
python pdf_translator.py document.pdf -o 翻译后的文档.pdf

# 使用自定义模型
python pdf_translator.py document.pdf --model deepseek-chat
```

## 故障排除

### 问题：无法连接到LM Studio

**解决方案**：
- 确保LM Studio服务器正在运行
- 检查服务器地址和端口是否正确
- 确认防火墙没有阻止连接

### 问题：PDF中中文显示为方块

**解决方案**：
- 安装中文字体（如PingFang、SimSun等）
- 工具会自动尝试注册常见的中文字体路径

### 问题：翻译结果不准确

**解决方案**：
- 尝试使用更好的模型
- 减小 `--chunk-size` 参数值
- 检查原始PDF文本提取是否完整
- 删除旧的缓存文件后重新运行，确保不使用过期结果

### 问题：处理大文件时内存不足

**解决方案**：
- 减小 `--chunk-size` 参数值
- 分批处理PDF文件

## 技术细节

- **文本提取**：使用PyMuPDF的`get_text()`方法提取文本
- **分块策略**：优先按段落分割，长段落按句子分割
- **翻译API**：使用LM Studio的OpenAI兼容API
- **PDF生成**：使用reportlab生成新的PDF文件

## 许可证

与主项目保持一致。

