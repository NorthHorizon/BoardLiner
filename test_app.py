#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication
from main import BreadboardConnector
from hole_detector import HoleDetector, Hole
from wire_manager import WireManager, Wire

def create_test_image():
    """创建一个测试用的面包板图像"""
    # 创建空白图像
    width, height = 800, 600
    image = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    # 绘制面包板轮廓
    board_width, board_height = 600, 400
    board_x = (width - board_width) // 2
    board_y = (height - board_height) // 2
    
    cv2.rectangle(image, (board_x, board_y), 
                 (board_x + board_width, board_y + board_height), 
                 (200, 200, 200), -1)
    cv2.rectangle(image, (board_x, board_y), 
                 (board_x + board_width, board_y + board_height), 
                 (100, 100, 100), 2)
    
    # 创建孔的网格
    rows, cols = 10, 30
    hole_radius = 3
    spacing_x = board_width // (cols + 1)
    spacing_y = board_height // (rows + 1)
    
    # 绘制孔
    for row in range(rows):
        for col in range(cols):
            x = board_x + (col + 1) * spacing_x
            y = board_y + (row + 1) * spacing_y
            cv2.circle(image, (x, y), hole_radius, (0, 0, 0), -1)
    
    # 添加一些噪声
    noise = np.random.normal(0, 5, image.shape).astype(np.int16)
    image = cv2.add(image.astype(np.int16), noise).clip(0, 255).astype(np.uint8)
    
    return image

def test_hole_detector():
    """测试孔检测器"""
    print("测试孔检测器...")
    
    # 创建测试图像
    image = create_test_image()
    
    # 创建孔检测器
    detector = HoleDetector()
    
    # 检测孔
    holes = detector.detect(image)
    
    print(f"检测到 {len(holes)} 个孔")
    
    # 可视化结果
    result = detector.visualize(image, holes)
    
    # 保存结果
    cv2.imwrite("test_holes.jpg", result)
    print("孔检测结果已保存为 test_holes.jpg")
    
    return holes, image

def test_wire_manager(holes, image):
    """测试连线管理器"""
    print("测试连线管理器...")
    
    # 创建连线管理器
    manager = WireManager()
    
    # 随机添加一些连接线
    import random
    for _ in range(10):
        hole1 = random.choice(holes)
        hole2 = random.choice(holes)
        
        if hole1 != hole2:
            manager.add_wire(hole1, hole2)
    
    print(f"添加了 {len(manager.wires)} 条连接线")
    
    # 可视化结果
    result = manager.draw_all_wires(image)
    
    # 保存结果
    cv2.imwrite("test_wires.jpg", result)
    print("连线结果已保存为 test_wires.jpg")

def main():
    """测试主程序"""
    # 测试孔检测器
    holes, image = test_hole_detector()
    
    # 测试连线管理器
    test_wire_manager(holes, image)
    
    # 启动GUI应用
    print("启动GUI应用...")
    app = QApplication(sys.argv)
    window = BreadboardConnector()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 