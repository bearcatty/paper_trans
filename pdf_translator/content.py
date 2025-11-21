from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

@dataclass
class ContentBlock:
    """内容块"""
    text: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    block_type: str  # "text", "image", "table"
    image_data: Optional[bytes] = None
    image_ext: str = "png"
    page_num: int = 0

class ContentExtractor:
    """内容提取器"""
    
    def __init__(self, header_threshold: float = 50, footer_threshold: float = 50):
        self.header_threshold = header_threshold  # 距离页面顶部的阈值
        self.footer_threshold = footer_threshold  # 距离页面底部的阈值
        
    def is_header_or_footer(self, bbox: Tuple[float, float, float, float], page_height: float) -> bool:
        """判断是否为页眉或页脚"""
        y0, y1 = bbox[1], bbox[3]
        # 检查是否在页眉区域
        if y1 < self.header_threshold:
            return True
        # 检查是否在页脚区域
        if y0 > page_height - self.footer_threshold:
            return True
        return False

    def smart_sort_blocks(self, blocks: List[ContentBlock], page_width: float) -> List[ContentBlock]:
        """
        智能排序块，处理双栏布局
        策略：
        1. 将页面垂直划分为多个区域（由跨栏的大块分隔）
        2. 在每个区域内，区分左栏和右栏
        3. 按 区域 -> (左栏 -> 右栏) 的顺序排序
        """
        if not blocks:
            return []

        # 定义跨栏阈值（例如宽度超过页面宽度的60%）
        full_width_threshold = page_width * 0.6
        center_x = page_width / 2

        # 1. 识别跨栏块（Full）和分栏块（Left/Right）
        # 同时按垂直位置初步排序
        blocks.sort(key=lambda b: b.bbox[1])
        
        segments = []
        current_segment = []
        
        for block in blocks:
            width = block.bbox[2] - block.bbox[0]
            is_full_width = width > full_width_threshold
            
            if is_full_width:
                # 如果遇到跨栏块，先结束当前分栏区域
                if current_segment:
                    segments.append({"type": "columns", "blocks": current_segment})
                    current_segment = []
                # 添加跨栏块作为一个单独的区域
                segments.append({"type": "full", "blocks": [block]})
            else:
                current_segment.append(block)
        
        if current_segment:
            segments.append({"type": "columns", "blocks": current_segment})

        # 2. 对每个区域进行内部排序
        sorted_blocks = []
        
        for seg in segments:
            if seg["type"] == "full":
                sorted_blocks.extend(seg["blocks"])
            else:
                # 分栏区域：区分左右栏
                left_col = []
                right_col = []
                others = [] # 难以区分的
                
                for b in seg["blocks"]:
                    b_center = (b.bbox[0] + b.bbox[2]) / 2
                    if b_center < center_x:
                        left_col.append(b)
                    else:
                        right_col.append(b)
                
                # 栏内按垂直位置排序
                left_col.sort(key=lambda b: b.bbox[1])
                right_col.sort(key=lambda b: b.bbox[1])
                
                sorted_blocks.extend(left_col)
                sorted_blocks.extend(right_col)
                
        return sorted_blocks

    def calculate_bbox_distance(self, bbox1: Tuple[float, float, float, float], 
                                bbox2: Tuple[float, float, float, float]) -> float:
        """计算两个边界框之间的最小距离"""
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2
        
        # 检查是否重叠
        if not (x1_max < x2_min or x2_max < x1_min or y1_max < y2_min or y2_max < y1_min):
            return 0.0
        
        # 计算最小距离
        dx = max(0, max(x1_min - x2_max, x2_min - x1_max))
        dy = max(0, max(y1_min - y2_max, y2_min - y1_max))
        
        return (dx ** 2 + dy ** 2) ** 0.5
    
    def cluster_images(self, image_blocks: List[ContentBlock], 
                      distance_threshold: float = 50.0,
                      min_cluster_size: int = 2) -> List[List[ContentBlock]]:
        """使用简化的DBSCAN算法对图像进行聚类"""
        if len(image_blocks) < min_cluster_size:
            return [[block] for block in image_blocks]
        
        n = len(image_blocks)
        visited = [False] * n
        clusters = []
        
        for i in range(n):
            if visited[i]:
                continue
            
            # 找到所有邻居
            cluster = [image_blocks[i]]
            visited[i] = True
            queue = [i]
            
            while queue:
                current_idx = queue.pop(0)
                current_block = image_blocks[current_idx]
                
                # 检查所有未访问的块
                for j in range(n):
                    if visited[j]:
                        continue
                    
                    distance = self.calculate_bbox_distance(
                        current_block.bbox, 
                        image_blocks[j].bbox
                    )
                    
                    if distance <= distance_threshold:
                        cluster.append(image_blocks[j])
                        visited[j] = True
                        queue.append(j)
            
            clusters.append(cluster)
        
        # 过滤掉小于最小聚类大小的单独图像
        final_clusters = []
        for cluster in clusters:
            if len(cluster) >= min_cluster_size:
                final_clusters.append(cluster)
            else:
                # 单独的图像也作为独立聚类
                for block in cluster:
                    final_clusters.append([block])
        
        return final_clusters
    
    def create_composite_image(self, cluster: List[ContentBlock]) -> Tuple[bytes, str]:
        """将聚类中的多个图像合成为一个复合图像"""
        if len(cluster) == 1:
            # 只有一个图像，直接返回
            return cluster[0].image_data, cluster[0].image_ext
        
        # 计算整体边界框
        min_x = min(block.bbox[0] for block in cluster)
        min_y = min(block.bbox[1] for block in cluster)
        max_x = max(block.bbox[2] for block in cluster)
        max_y = max(block.bbox[3] for block in cluster)
        
        # 创建画布
        canvas_width = int(max_x - min_x)
        canvas_height = int(max_y - min_y)
        
        # 使用白色背景
        canvas = Image.new('RGB', (canvas_width, canvas_height), 'white')
        
        # 将每个图像粘贴到画布上
        for block in cluster:
            try:
                img = Image.open(BytesIO(block.image_data))
                
                # 计算相对位置
                x_offset = int(block.bbox[0] - min_x)
                y_offset = int(block.bbox[1] - min_y)
                
                # 粘贴图像
                if img.mode == 'RGBA':
                    canvas.paste(img, (x_offset, y_offset), img)
                else:
                    canvas.paste(img, (x_offset, y_offset))
            except Exception as e:
                logger.warning(f"合成图像时出错: {e}")
                continue
        
        # 将画布转换为字节
        output = BytesIO()
        canvas.save(output, format='PNG')
        composite_bytes = output.getvalue()
        
        return composite_bytes, 'png'

    def extract_page(self, page, page_num: int) -> List[ContentBlock]:
        """提取单页内容"""
        blocks: List[ContentBlock] = []
        page_height = page.rect.height
        page_width = page.rect.width
        
        # 1. 提取文本块
        # 使用 "blocks" 模式: (x0, y0, x1, y1, "lines", block_no, block_type)
        raw_blocks = page.get_text("blocks")
        
        for b in raw_blocks:
            bbox = (b[0], b[1], b[2], b[3])
            text = b[4].strip()
            b_type = b[6]  # 0 = text, 1 = image
            
            # 过滤页眉页脚
            if self.is_header_or_footer(bbox, page_height):
                continue
                
            if b_type == 0 and text:  # 文本
                # 简单过滤掉纯数字引用标记（如 [1]）或太短的内容，可视情况调整
                if len(text) < 3 and text.isdigit():
                    continue
                blocks.append(ContentBlock(
                    text=text,
                    bbox=bbox,
                    block_type="text",
                    page_num=page_num
                ))
            elif b_type == 1:  # 图像块（PyMuPDF识别的）
                # 注意：get_text("blocks") 中的图像通常是背景图或内嵌图
                # 我们稍后会专门处理图像，这里先占位
                pass

        # 2. 提取图像 (使用 get_images 更可靠)
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list, 1):
            xref = img[0]
            try:
                base_image = page.parent.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # 尝试获取图像在页面上的位置
                # 这需要搜索页面上的图像引用
                image_rects = page.get_image_rects(xref)
                
                if image_rects:
                    # 合并所有矩形区域，避免将一张图分割成多个子图
                    # 计算所有矩形的边界框
                    min_x0 = min(rect.x0 for rect in image_rects)
                    min_y0 = min(rect.y0 for rect in image_rects)
                    max_x1 = max(rect.x1 for rect in image_rects)
                    max_y1 = max(rect.y1 for rect in image_rects)
                    
                    merged_bbox = (min_x0, min_y0, max_x1, max_y1)
                    
                    # 检查合并后的边界框是否在页眉页脚区域
                    if not self.is_header_or_footer(merged_bbox, page_height):
                        blocks.append(ContentBlock(
                            text=f"<<IMAGE_{img_index}>>",
                            bbox=merged_bbox,
                            block_type="image",
                            image_data=image_bytes,
                            image_ext=image_ext,
                            page_num=page_num
                        ))
                else:
                    # 如果找不到位置，默认放在页面末尾或忽略
                    # 这里选择忽略位置未知的图像，或者可以作为一个无位置的块
                    pass
            except Exception as e:
                logger.warning(f"提取图像失败: {e}")

        # 3. 对图像进行聚类并创建复合图像
        image_blocks = [b for b in blocks if b.block_type == "image"]
        text_blocks = [b for b in blocks if b.block_type == "text"]
        
        if len(image_blocks) >= 2:
            # 进行聚类
            clusters = self.cluster_images(image_blocks, distance_threshold=50.0, min_cluster_size=2)
            
            # 为每个聚类创建复合图像或保留单个图像
            clustered_image_blocks = []
            cluster_index = 1
            
            for cluster in clusters:
                if len(cluster) > 1:
                    # 多个图像，创建复合图像
                    try:
                        composite_data, composite_ext = self.create_composite_image(cluster)
                        
                        # 计算聚类的整体边界框
                        min_x = min(b.bbox[0] for b in cluster)
                        min_y = min(b.bbox[1] for b in cluster)
                        max_x = max(b.bbox[2] for b in cluster)
                        max_y = max(b.bbox[3] for b in cluster)
                        
                        clustered_image_blocks.append(ContentBlock(
                            text=f"<<IMAGE_CLUSTER_{cluster_index}>>",
                            bbox=(min_x, min_y, max_x, max_y),
                            block_type="image",
                            image_data=composite_data,
                            image_ext=composite_ext,
                            page_num=page_num
                        ))
                        cluster_index += 1
                        logger.info(f"第 {page_num} 页：合并了 {len(cluster)} 个图像为一个复合图像")
                    except Exception as e:
                        logger.warning(f"创建复合图像失败: {e}，保留原始图像")
                        clustered_image_blocks.extend(cluster)
                else:
                    # 单个图像，直接保留
                    clustered_image_blocks.extend(cluster)
            
            # 合并文本块和聚类后的图像块
            blocks = text_blocks + clustered_image_blocks
        
        # 4. 智能排序
        return self.smart_sort_blocks(blocks, page_width)
