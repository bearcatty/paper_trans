import argparse
import asyncio
import logging
import os

from .core import PDFTranslator, DEFAULT_BASE_URL, DEFAULT_MODEL, CHUNK_SIZE

logger = logging.getLogger(__name__)

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="PDF翻译工具 - 使用LM Studio将PDF从英文翻译成中文"
    )
    parser.add_argument(
        "input_pdf",
        type=str,
        help="输入的PDF文件路径"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出的Markdown文件路径（默认：输入文件名_translated.md）"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_BASE_URL,
        help=f"LM Studio服务器地址（默认: {DEFAULT_BASE_URL}）"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"使用的模型名称（默认: {DEFAULT_MODEL}）"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help=f"翻译块大小（默认: {CHUNK_SIZE} 字符）"
    )

    
    args = parser.parse_args()
    
    # 检查输入文件是否存在
    if not os.path.exists(args.input_pdf):
        logger.error(f"输入文件不存在: {args.input_pdf}")
        return 1
    
    translator = PDFTranslator(
        base_url=args.base_url,
        model=args.model
    )
    
    try:
        output_path = await translator.translate_pdf(
            args.input_pdf,
            args.output,
            args.chunk_size,
        )
        logger.info(f"✓ 翻译完成！输出文件: {output_path}")
        return 0
    except Exception as e:
        logger.error(f"✗ 翻译失败: {e}", exc_info=True)
        return 1
    finally:
        await translator.close()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
