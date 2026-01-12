#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class Hole:
    """表示面包板上的一个孔"""
    x: int
    y: int
    radius: float = 3.0
    
    @property
    def position(self) -> Tuple[int, int]:
        """返回孔的位置坐标"""
        return (self.x, self.y)

class HoleDetector:
    """面包板孔检测器"""
    
    def __init__(self):
        # 检测参数
        self.min_area = 10
        self.max_area = 500
        self.min_circularity = 0.5
        self.distance_threshold = 10
        
    def set_params(self, min_area: int = 10, max_area: int = 500, 
                  min_circularity: float = 0.5, distance_threshold: int = 10):
        """设置检测参数"""
        self.min_area = min_area
        self.max_area = max_area
        self.min_circularity = min_circularity
        self.distance_threshold = distance_threshold
        
    def detect(self, image: np.ndarray) -> List[Hole]:
        """
        检测图像中的面包板孔
        
        Args:
            image: 输入图像，BGR格式
            
        Returns:
            检测到的孔列表
        """
        # 转换为灰度图
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 应用高斯模糊减少噪声
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 使用自适应阈值处理
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # 形态学操作以改善孔的形状
        kernel = np.ones((3, 3), np.uint8)
        opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # 查找轮廓
        contours, _ = cv2.findContours(
            opening, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        # 分析轮廓并提取孔
        holes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            
            # 过滤面积
            if self.min_area < area < self.max_area:
                # 计算周长
                perimeter = cv2.arcLength(contour, True)
                
                # 计算圆形度 (4π·面积/周长²)
                circularity = 0
                if perimeter > 0:
                    circularity = 4 * np.pi * area / (perimeter * perimeter)
                
                # 过滤非圆形物体
                if circularity > self.min_circularity:
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        
                        # 计算等效半径
                        radius = np.sqrt(area / np.pi)
                        
                        holes.append(Hole(cx, cy, radius))
        
        # 对孔进行聚类，合并相近的孔
        merged_holes = self._merge_nearby_holes(holes)
        
        return merged_holes
    
    def _merge_nearby_holes(self, holes: List[Hole]) -> List[Hole]:
        """合并相近的孔"""
        if not holes:
            return []
            
        # 按x坐标排序
        sorted_holes = sorted(holes, key=lambda h: h.x)
        
        merged = []
        current_group = [sorted_holes[0]]
        
        for i in range(1, len(sorted_holes)):
            current_hole = sorted_holes[i]
            prev_hole = current_group[-1]
            
            # 计算距离
            distance = np.sqrt((current_hole.x - prev_hole.x)**2 + 
                              (current_hole.y - prev_hole.y)**2)
            
            if distance < self.distance_threshold:
                # 合并到当前组
                current_group.append(current_hole)
            else:
                # 处理当前组并开始新组
                if current_group:
                    # 计算组中所有孔的平均位置
                    avg_x = sum(h.x for h in current_group) // len(current_group)
                    avg_y = sum(h.y for h in current_group) // len(current_group)
                    avg_radius = sum(h.radius for h in current_group) / len(current_group)
                    
                    merged.append(Hole(avg_x, avg_y, avg_radius))
                
                current_group = [current_hole]
        
        # 处理最后一组
        if current_group:
            avg_x = sum(h.x for h in current_group) // len(current_group)
            avg_y = sum(h.y for h in current_group) // len(current_group)
            avg_radius = sum(h.radius for h in current_group) / len(current_group)
            
            merged.append(Hole(avg_x, avg_y, avg_radius))
        
        return merged
    
    def detect_grid(self, image: np.ndarray) -> Tuple[List[Hole], np.ndarray]:
        """
        检测面包板孔并尝试识别网格结构
        
        Args:
            image: 输入图像
            
        Returns:
            (孔列表, 带有网格可视化的图像)
        """
        # 检测孔
        holes = self.detect(image)
        
        # 创建结果图像
        result_image = image.copy()
        
        # 绘制检测到的孔
        for hole in holes:
            cv2.circle(result_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 尝试识别网格结构
        if len(holes) > 10:
            # 提取所有孔的坐标
            points = np.array([hole.position for hole in holes])
            
            # 使用DBSCAN聚类算法识别行
            try:
                from sklearn.cluster import DBSCAN
                
                # 按y坐标聚类识别行
                y_clustering = DBSCAN(eps=10, min_samples=3).fit(points[:, 1].reshape(-1, 1))
                y_labels = y_clustering.labels_
                
                # 获取行的唯一标签
                unique_rows = np.unique(y_labels[y_labels >= 0])
                
                # 为每一行分配不同的颜色
                colors = [(0, 0, 255), (255, 0, 0), (255, 255, 0), 
                         (0, 255, 255), (255, 0, 255), (128, 128, 0)]
                
                # 绘制行
                for i, row_label in enumerate(unique_rows):
                    row_points = points[y_labels == row_label]
                    color = colors[i % len(colors)]
                    
                    # 按x坐标排序
                    row_points = row_points[row_points[:, 0].argsort()]
                    
                    # 绘制行连接线
                    for j in range(len(row_points) - 1):
                        pt1 = tuple(row_points[j])
                        pt2 = tuple(row_points[j + 1])
                        cv2.line(result_image, pt1, pt2, color, 1, cv2.LINE_AA)
            except ImportError:
                # sklearn不可用时跳过网格识别
                pass
        
        return holes, result_image
    
    def visualize(self, image: np.ndarray, holes: List[Hole]) -> np.ndarray:
        """
        在图像上可视化检测到的孔
        
        Args:
            image: 输入图像
            holes: 检测到的孔列表
            
        Returns:
            可视化结果图像
        """
        result = image.copy()
        
        # 绘制检测到的孔
        for hole in holes:
            cv2.circle(result, hole.position, int(hole.radius), (0, 255, 0), -1)
            
        return result 