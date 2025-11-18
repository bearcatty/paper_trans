## PDF Translation Toolkit

This project now centers on **high‑quality PDF → Chinese translation** powered by a local LM Studio model and an MCP adapter. It extracts text, preserves images, applies multi‑pass LLM QA, and exports either a polished PDF or a Markdown package for downstream editing.

---

### ✨ Core Features
- **End‑to‑end PDF translation** (`pdf_translator.py`) with chunked processing, paragraph awareness, and page metadata.
- **Quality assurance loop**: every chunk is rechecked for mixed languages or prompt artifacts; the model is asked to fix issues automatically.
- **Image & table preservation**: original figures/screenshots are extracted via PyMuPDF and re‑embedded.  
- **Flexible output formats**: choose printable PDF or Markdown + assets folder (with MathJax‑ready formulas).
- **Crash‑safe incremental resume**: translation progress per page/chunk is cached (`*.cache.json`) so you can restart from where it stopped.

---

### 🚀 Quick Start
1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Start LM Studio** with the model you want (default `openai/gpt-oss-20b`) and ensure the local API listens on `http://127.0.0.1:1234`.
3. **Run the translator**
   ```bash
   python pdf_translator.py path/to/input.pdf \
     --format md \
     -o path/to/output.md
   ```
   Options:
   - `--format pdf|md` (default `pdf`)
   - `--chunk-size 2000` (tweak if the model struggles with long paragraphs)
   - `--base-url` / `--model` to point at a different LM Studio endpoint/model.

---

### 📂 Output Layout
- **PDF**: `input_translated.pdf`
- **Markdown**: `input_translated.md` and `input_translated_assets/`  
  - Formulas like `\(...\)` or `\[...\]` are converted to `$...$` / `$$...$$` for Obsidian, VS Code Preview Enhanced, etc.
- **Cache**: `input_translated.<format>.cache.json` (auto‑deleted after a clean run; keep it for resume or remove to retranslate).

---

### 🧪 Recommendations
- Use VS Code + Markdown Preview Enhanced, Obsidian, Typora,或浏览器查看 Markdown 结果以获得最佳渲染效果。
- 若需将 Markdown 再导出为 EPUB/PDF，可借助 Typora、Calibre (`ebook-convert`)、PrinceXML 或 `pandoc`。

---

### 🔧 Other Utilities
- `mcp_server.py`: MCP server that wraps LM Studio’s OpenAI‑compatible API. See [MCP_README.md](MCP_README.md) for standalone usage/tests.
- Legacy scripts like `daily_contacts.py` remain but are no longer the primary focus.

---

### 🤝 Contributing
Issues and PRs are welcome—this toolkit is evolving toward better formatting recovery (tables, formulas) and faster QA cycles. Feel free to adapt it to your own translation workflows.

