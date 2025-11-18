## Research Intelligence Automation

This repository contains a Python workflow for collecting public contact information of leading large-model researchers (e.g., DeepSeek, Anthropic, Google Brain, Tsinghua, PKU) from openly available sources such as arXiv.

### Key Features
- Queries arXiv’s API for the latest submissions in configurable categories (default: LLM-related areas).
- Attempts to extract author emails from arXiv metadata and linked public pages.
- Normalizes and deduplicates contacts before persisting them to `research_contacts.csv`.
- Designed to run daily via cron or any scheduler.

### Quick Start
1. Create and activate a virtual environment.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the daily pipeline (example: look back 2 days, dry run disabled):
   ```
   python daily_contacts.py --past-days 2 --csv-path research_contacts.csv
   ```

### Scheduling with Cron
Add a cron entry (runs every day at 03:00):
```
0 3 * * * /usr/bin/env bash -lc 'cd /Users/bytedance/work/author_parser && /usr/bin/env python daily_contacts.py --csv-path /Users/bytedance/work/author_parser/research_contacts.csv >> /Users/bytedance/work/author_parser/cron.log 2>&1'
```

### Configuration Highlights
- `--categories`: comma-separated arXiv categories to monitor (defaults cover LLM research).
- `--target-keywords`: organization keywords that help prioritize relevant authors.
- `--dry-run`: processes data without touching the CSV for debugging.
- `--max-results` and `--request-interval`: rate limiting controls to stay polite with public endpoints.

### Limitations & Next Steps
- Public arXiv pages rarely expose emails directly; the scraper only records what is openly available.
- You can extend `source_discovery.py` (future module) to ingest institution directories, lab pages, or social profiles that expose contact info.
- Consider integrating with a database plus notification system once the CSV workflow stabilizes.

### Repository Layout
- `daily_contacts.py`: Main pipeline script.
- `requirements.txt`: Python dependencies.
- `tests/`: Unit tests covering parsers and utilities.
- `mcp_server.py`: MCP server for LM Studio API (see [MCP_README.md](MCP_README.md) for details).

### LM Studio MCP Server

This repository includes an MCP (Model Context Protocol) server that wraps LM Studio's API for local LLM interactions. See [MCP_README.md](MCP_README.md) for detailed documentation.

Quick start:
```bash
# Install dependencies
pip install -r requirements.txt

# Run the MCP server
python mcp_server.py

# Or test the client directly
python test_mcp_client.py
```

