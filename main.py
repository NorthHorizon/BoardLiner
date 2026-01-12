#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import cv2
import numpy as np
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QFileDialog, QLabel, 
                            QMessageBox, QStatusBar, QSlider, QGroupBox,
                            QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
                            QComboBox, QScrollArea, QRadioButton, QButtonGroup)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QWheelEvent
from PyQt5.QtCore import Qt, QPoint, QRect

from hole_detector import HoleDetector, Hole
from wire_manager import WireManager, Wire

class ZoomableImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.scale_factor = 1.0
        self.pixmap_original = None
        self.setMinimumSize(800, 600)
        self.offset_x = 0
        self.offset_y = 0
        self.dragging = False
        self.drag_start_pos = None
        self.setFocusPolicy(Qt.StrongFocus)  # 允许接收键盘焦点
        self.space_pressed = False  # 跟踪空格键状态
        self.handling_event = False  # 防止递归
        
    def set_pixmap(self, pixmap):
        self.pixmap_original = pixmap
        self.update_pixmap()
        
    def update_pixmap(self):
        if self.pixmap_original:
            # 将浮点数转换为整数
            width = int(self.pixmap_original.width() * self.scale_factor)
            height = int(self.pixmap_original.height() * self.scale_factor)
            scaled_pixmap = self.pixmap_original.scaled(
                width,
                height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            super().setPixmap(scaled_pixmap)
            
    def paintEvent(self, event):
        if self.pixmap() is None:
            return super().paintEvent(event)
            
        painter = QPainter(self)
        pixmap = self.pixmap()
        
        # 计算图像在Label中的位置
        x = (self.width() - pixmap.width()) / 2 + self.offset_x
        y = (self.height() - pixmap.height()) / 2 + self.offset_y
        
        # 绘制图像
        painter.drawPixmap(int(x), int(y), pixmap)
            
    def wheelEvent(self, event: QWheelEvent):
        # 处理鼠标滚轮事件，用于缩放图像
        delta = event.angleDelta().y()
        if delta > 0:
            # 放大
            self.scale_factor *= 1.1
        else:
            # 缩小
            self.scale_factor *= 0.9
            
        # 限制缩放范围
        self.scale_factor = max(0.1, min(self.scale_factor, 10.0))
        
        self.update_pixmap()
        self.update()  # 更新显示
        
        # 通知父窗口缩放因子已更改
        if hasattr(self.parent(), 'parent') and hasattr(self.parent().parent(), 'on_zoom_changed'):
            self.parent().parent().on_zoom_changed()
            
    def keyPressEvent(self, event):
        # 处理空格键按下事件
        if event.key() == Qt.Key_Space:
            self.space_pressed = True
            self.setCursor(Qt.OpenHandCursor)
        else:
            super().keyPressEvent(event)
            
    def keyReleaseEvent(self, event):
        # 处理空格键释放事件
        if event.key() == Qt.Key_Space:
            self.space_pressed = False
            self.setCursor(Qt.ArrowCursor)
            self.dragging = False
        else:
            super().keyReleaseEvent(event)
            
    def mousePressEvent(self, event):
        # 如果已经在处理事件，直接返回
        if self.handling_event:
            return
            
        self.handling_event = True
        
        # 如果空格键被按下或按下中键，开始拖动
        modifiers = QApplication.keyboardModifiers()
        if self.space_pressed or modifiers == Qt.ShiftModifier or event.button() == Qt.MiddleButton:
            self.dragging = True
            self.drag_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        else:
            # 传递给父类处理
            super().mousePressEvent(event)
            
        self.handling_event = False
            
    def mouseMoveEvent(self, event):
        # 如果已经在处理事件，直接返回
        if self.handling_event:
            return
            
        self.handling_event = True
        
        # 如果正在拖动，更新偏移量
        if self.dragging and self.drag_start_pos:
            delta = event.pos() - self.drag_start_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self.drag_start_pos = event.pos()
            
            # 更新显示
            self.update()
            
            # 通知父窗口更新视图
            if hasattr(self.parent(), 'parent') and hasattr(self.parent().parent(), 'update_view_offset'):
                self.parent().parent().update_view_offset()
        else:
            # 传递给父类处理
            super().mouseMoveEvent(event)
            
        self.handling_event = False
            
    def mouseReleaseEvent(self, event):
        # 如果已经在处理事件，直接返回
        if self.handling_event:
            return
            
        self.handling_event = True
        
        # 如果释放鼠标，结束拖动
        if self.dragging:
            self.dragging = False
            if self.space_pressed:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        else:
            # 传递给父类处理
            super().mouseReleaseEvent(event)
            
        self.handling_event = False

class BreadboardConnector(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 初始化变量
        self.image = None
        self.holes = []
        self.wire_manager = WireManager()
        self.hole_detector = HoleDetector()
        
        # 绘制状态
        self.drawing = False
        self.current_hole = None
        self.temp_line_end = None
        
        # 防止递归调用标志
        self.handling_mouse_event = False
        
        # 多点路径模式
        self.path_mode = False  # 是否启用多点路径模式
        self.current_path = []  # 当前路径的中间点
        self.path_start_hole = None  # 路径起点
        
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('面包板连线工具')
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 创建左侧控制面板
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_panel.setMaximumWidth(300)
        
        # 文件操作按钮
        file_group = QGroupBox("文件操作")
        file_layout = QVBoxLayout()
        
        self.load_button = QPushButton('加载图片')
        self.load_button.clicked.connect(self.load_image)
        
        self.save_button = QPushButton('保存结果图片')
        self.save_button.clicked.connect(self.save_result)
        self.save_button.setEnabled(False)
        
        self.export_button = QPushButton('导出连线数据')
        self.export_button.clicked.connect(self.export_connections)
        self.export_button.setEnabled(False)
        
        self.import_button = QPushButton('导入连线数据')
        self.import_button.clicked.connect(self.import_connections)
        self.import_button.setEnabled(False)
        
        file_layout.addWidget(self.load_button)
        file_layout.addWidget(self.save_button)
        file_layout.addWidget(self.export_button)
        file_layout.addWidget(self.import_button)
        file_group.setLayout(file_layout)
        
        # 孔检测参数
        detection_group = QGroupBox("孔检测设置")
        detection_layout = QFormLayout()
        
        self.min_area_spin = QSpinBox()
        self.min_area_spin.setRange(1, 1000)
        self.min_area_spin.setValue(10)
        self.min_area_spin.valueChanged.connect(self.update_detection_params)
        
        self.max_area_spin = QSpinBox()
        self.max_area_spin.setRange(10, 10000)
        self.max_area_spin.setValue(500)
        self.max_area_spin.valueChanged.connect(self.update_detection_params)
        
        self.circularity_spin = QDoubleSpinBox()
        self.circularity_spin.setRange(0.1, 1.0)
        self.circularity_spin.setSingleStep(0.05)
        self.circularity_spin.setValue(0.5)
        self.circularity_spin.valueChanged.connect(self.update_detection_params)
        
        self.distance_threshold_spin = QSpinBox()
        self.distance_threshold_spin.setRange(1, 50)
        self.distance_threshold_spin.setValue(10)
        self.distance_threshold_spin.valueChanged.connect(self.update_detection_params)
        
        detection_layout.addRow("最小面积:", self.min_area_spin)
        detection_layout.addRow("最大面积:", self.max_area_spin)
        detection_layout.addRow("圆形度阈值:", self.circularity_spin)
        detection_layout.addRow("合并距离:", self.distance_threshold_spin)
        
        self.detect_button = QPushButton('检测孔')
        self.detect_button.clicked.connect(self.detect_holes)
        self.detect_button.setEnabled(False)
        
        detection_layout.addRow(self.detect_button)
        detection_group.setLayout(detection_layout)
        
        # 连线操作
        wire_group = QGroupBox("连线操作")
        wire_layout = QVBoxLayout()
        
        self.clear_button = QPushButton('清除所有连线')
        self.clear_button.clicked.connect(self.clear_wires)
        self.clear_button.setEnabled(False)
        
        # 添加撤销按钮
        self.undo_button = QPushButton('撤销上一步')
        self.undo_button.clicked.connect(self.undo_last_action)
        self.undo_button.setEnabled(False)
        
        # 添加路径模式切换
        self.path_mode_check = QCheckBox("多点路径模式")
        self.path_mode_check.setChecked(False)
        self.path_mode_check.stateChanged.connect(self.toggle_path_mode)
        
        # 添加完成路径按钮
        self.finish_path_button = QPushButton('完成当前路径')
        self.finish_path_button.clicked.connect(self.finish_current_path)
        self.finish_path_button.setEnabled(False)
        
        # 添加取消路径按钮
        self.cancel_path_button = QPushButton('取消当前路径')
        self.cancel_path_button.clicked.connect(self.cancel_current_path)
        self.cancel_path_button.setEnabled(False)
        
        wire_layout.addWidget(self.clear_button)
        wire_layout.addWidget(self.undo_button)
        wire_layout.addWidget(self.path_mode_check)
        wire_layout.addWidget(self.finish_path_button)
        wire_layout.addWidget(self.cancel_path_button)
        wire_group.setLayout(wire_layout)
        
        # 添加颜色选择
        color_group = QGroupBox("连线颜色")
        color_layout = QVBoxLayout()
        
        self.color_buttons = QButtonGroup()
        self.color_buttons.setExclusive(True)  # 单选
        
        # 定义颜色选项
        color_options = [
            ("红色", "#cf3d13", (19, 61, 207)),  # BGR格式
            ("黑色", "#000000", (0, 0, 0)),
            ("绿色", "#357944", (68, 121, 53)),
            ("橙色", "#ee781f", (31, 120, 238)),
            ("青色", "#5ba4af", (175, 164, 91)),
            ("紫色", "#823d86", (134, 61, 130)),
            ("随机", None, None)
        ]
        
        for i, (name, hex_color, bgr_color) in enumerate(color_options):
            if name == "随机":
                rb = QRadioButton("随机颜色")
                rb.setChecked(True)  # 默认选择随机颜色
                rb.color_value = None
                rb.clicked.connect(lambda checked, rb=rb: self.on_color_selected(rb.color_value))
            else:
                rb = QRadioButton(name)
                # 设置按钮样式，显示颜色
                rb.setStyleSheet(f"QRadioButton::indicator {{ background-color: {hex_color}; border: 1px solid gray; }}")
                rb.color_value = bgr_color
                rb.clicked.connect(lambda checked, rb=rb: self.on_color_selected(rb.color_value))
            
            self.color_buttons.addButton(rb, i)
            color_layout.addWidget(rb)
        
        color_group.setLayout(color_layout)
        
        # 添加线宽调整
        line_width_group = QGroupBox("线宽设置")
        line_width_layout = QFormLayout()
        
        self.line_width_slider = QSlider(Qt.Horizontal)
        self.line_width_slider.setRange(1, 10)  # 1-10像素
        self.line_width_slider.setValue(5)  # 默认2像素
        self.line_width_slider.setTickPosition(QSlider.TicksBelow)
        self.line_width_slider.setTickInterval(1)
        self.line_width_slider.valueChanged.connect(self.on_line_width_changed)
        
        self.line_width_label = QLabel("2")
        
        line_width_layout.addRow("线宽:", self.line_width_slider)
        line_width_layout.addRow("", self.line_width_label)
        
        line_width_group.setLayout(line_width_layout)
        
        # 显示设置
        display_group = QGroupBox("显示设置")
        display_layout = QFormLayout()
        
        self.show_holes_check = QCheckBox()
        self.show_holes_check.setChecked(True)
        self.show_holes_check.stateChanged.connect(self.update_display)
        
        self.show_wires_check = QCheckBox()
        self.show_wires_check.setChecked(True)
        self.show_wires_check.stateChanged.connect(self.update_display)
        
        # 添加缩放控制
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 500)  # 10% 到 500%
        self.zoom_slider.setValue(100)  # 默认 100%
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        
        self.zoom_label = QLabel("100%")
        
        display_layout.addRow("显示孔:", self.show_holes_check)
        display_layout.addRow("显示连线:", self.show_wires_check)
        display_layout.addRow("缩放:", self.zoom_slider)
        display_layout.addRow("", self.zoom_label)
        
        display_group.setLayout(display_layout)
        
        # 添加所有控制组到控制面板
        control_layout.addWidget(file_group)
        control_layout.addWidget(detection_group)
        control_layout.addWidget(wire_group)
        control_layout.addWidget(color_group)
        control_layout.addWidget(line_width_group)
        control_layout.addWidget(display_group)
        control_layout.addStretch(1)
        
        # 创建图像显示区
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        
        self.image_panel = QWidget()
        image_layout = QVBoxLayout(self.image_panel)
        
        # 使用可缩放的标签
        self.image_label = ZoomableImageLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid black")
        
        # 设置鼠标追踪
        self.image_label.setMouseTracking(True)
        self.image_label.mousePressEvent = self.mouse_press_event
        self.image_label.mouseMoveEvent = self.mouse_move_event
        self.image_label.mouseReleaseEvent = self.mouse_release_event
        
        image_layout.addWidget(self.image_label)
        
        self.scroll_area.setWidget(self.image_panel)
        
        # 添加到主布局
        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.scroll_area, 1)
        
        # 添加状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage('就绪')
    
    def on_zoom_slider_changed(self, value):
        """处理缩放滑块值变化"""
        scale_factor = value / 100.0
        self.image_label.scale_factor = scale_factor
        self.image_label.update_pixmap()
        self.zoom_label.setText(f"{value}%")
        
    def on_zoom_changed(self):
        """处理图像缩放变化"""
        # 更新缩放滑块的值
        zoom_percent = int(self.image_label.scale_factor * 100)
        self.zoom_slider.setValue(zoom_percent)
        self.zoom_label.setText(f"{zoom_percent}%")
    
    def update_detection_params(self):
        """更新孔检测参数"""
        self.hole_detector.set_params(
            min_area=self.min_area_spin.value(),
            max_area=self.max_area_spin.value(),
            min_circularity=self.circularity_spin.value(),
            distance_threshold=self.distance_threshold_spin.value()
        )
        
        # 如果已经加载了图像，重新检测
        if self.image is not None and hasattr(self, 'holes') and self.holes:
            self.detect_holes()
    
    def load_image(self):
        """加载面包板图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择面包板图片', '', 'Image Files (*.png *.jpg *.jpeg *.bmp)'
        )
        
        if file_path:
            self.image = cv2.imread(file_path)
            if self.image is None:
                QMessageBox.critical(self, '错误', '无法加载图片')
                return
                
            self.processed_image = self.image.copy()
            self.display_image(self.processed_image)
            self.detect_button.setEnabled(True)
            self.statusBar.showMessage(f'已加载图片: {file_path}')
            
            # 重置数据
            self.holes = []
            self.wire_manager.clear()
            self.clear_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.export_button.setEnabled(False)
            self.import_button.setEnabled(True)
    
    def detect_holes(self):
        """检测面包板上的孔"""
        if self.image is None:
            return
            
        self.statusBar.showMessage('正在检测孔...')
        
        # 使用孔检测器检测孔
        self.holes, self.processed_image = self.hole_detector.detect_grid(self.image)
        
        # 更新显示
        self.update_display()
        self.statusBar.showMessage(f'检测到 {len(self.holes)} 个孔')
        
        self.clear_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.undo_button.setEnabled(False)  # 重新检测孔后，禁用撤销按钮
    
    def update_view_offset(self):
        """处理视图偏移变化"""
        # 更新显示
        self.update_display()
    
    def find_nearest_hole(self, point):
        """查找距离点击位置最近的孔"""
        if not self.holes:
            return None
        
        # 获取图像在Label中的位置
        pixmap = self.image_label.pixmap()
        if pixmap:
            # 计算图像在Label中的位置
            img_label_x = (self.image_label.width() - pixmap.width()) / 2 + self.image_label.offset_x
            img_label_y = (self.image_label.height() - pixmap.height()) / 2 + self.image_label.offset_y
            
            # 将点击位置转换为相对于图像的坐标
            rel_x = point.x() - img_label_x
            rel_y = point.y() - img_label_y
            
            # 转换为原始图像坐标
            img_x = int(rel_x / self.image_label.scale_factor)
            img_y = int(rel_y / self.image_label.scale_factor)
            
            min_dist = float('inf')
            nearest_hole = None
            
            for hole in self.holes:
                dist = ((img_x - hole.x) ** 2 + (img_y - hole.y) ** 2) ** 0.5
                if dist < min_dist:
                    min_dist = dist
                    nearest_hole = hole
                    
            # 如果最近的孔距离太远，则不选择任何孔
            # 根据缩放因子调整阈值
            threshold = 20 / self.image_label.scale_factor
            if min_dist > threshold:
                return None
                
            return nearest_hole
        
        return None
    
    def mouse_press_event(self, event):
        """鼠标按下事件处理"""
        # 防止递归调用
        if self.handling_mouse_event:
            return
            
        self.handling_mouse_event = True
        
        # 如果按下Shift键、空格键或中键，则处理拖动
        modifiers = QApplication.keyboardModifiers()
        if self.image_label.space_pressed or modifiers == Qt.ShiftModifier or event.button() == Qt.MiddleButton:
            # 直接处理拖动逻辑，而不是调用 image_label 的方法
            if not self.image_label.dragging:
                self.image_label.dragging = True
                self.image_label.drag_start_pos = event.pos()
                self.image_label.setCursor(Qt.ClosedHandCursor)
        elif not self.holes or self.image is None:
            pass  # 不做任何处理
        elif event.button() == Qt.LeftButton:
            nearest_hole = self.find_nearest_hole(event.pos())
            if nearest_hole:
                if self.path_mode:
                    # 多点路径模式
                    if not self.path_start_hole:
                        # 如果没有起点，设置起点
                        self.path_start_hole = nearest_hole
                        self.statusBar.showMessage(f'设置路径起点: ({nearest_hole.x}, {nearest_hole.y})')
                        self.cancel_path_button.setEnabled(True)
                    else:
                        # 如果已有起点，添加中间点或设置终点
                        if nearest_hole == self.path_start_hole:
                            # 如果点击的是起点，不做任何处理
                            pass
                        else:
                            # 获取点击位置在原始图像中的坐标
                            pixmap = self.image_label.pixmap()
                            if pixmap:
                                img_label_x = (self.image_label.width() - pixmap.width()) / 2 + self.image_label.offset_x
                                img_label_y = (self.image_label.height() - pixmap.height()) / 2 + self.image_label.offset_y
                                
                                rel_x = event.pos().x() - img_label_x
                                rel_y = event.pos().y() - img_label_y
                                
                                img_x = int(rel_x / self.image_label.scale_factor)
                                img_y = int(rel_y / self.image_label.scale_factor)
                                
                                # 添加中间点
                                self.current_path.append((nearest_hole.x, nearest_hole.y))
                                self.current_hole = nearest_hole
                                self.statusBar.showMessage(f'添加路径点: ({nearest_hole.x}, {nearest_hole.y})')
                                self.finish_path_button.setEnabled(True)
                                
                                # 更新显示
                                self.update_display_with_path()
                else:
                    # 普通模式
                    self.drawing = True
                    self.current_hole = nearest_hole
                    self.temp_line_end = (event.x(), event.y())
                    
                    # 更新显示
                    self.update_display_with_temp_line()
                    self.statusBar.showMessage(f'开始绘制连线，从孔 ({nearest_hole.x}, {nearest_hole.y})')
        
        self.handling_mouse_event = False
    
    def mouse_move_event(self, event):
        """鼠标移动事件处理"""
        # 防止递归调用
        if self.handling_mouse_event:
            return
            
        self.handling_mouse_event = True
        
        # 如果正在拖动，则处理拖动逻辑
        if self.image_label.dragging and self.image_label.drag_start_pos:
            delta = event.pos() - self.image_label.drag_start_pos
            self.image_label.offset_x += delta.x()
            self.image_label.offset_y += delta.y()
            self.image_label.drag_start_pos = event.pos()
            
            # 更新显示
            self.image_label.update()
            self.update_view_offset()
        elif self.drawing and self.holes and self.current_hole:
            # 更新临时线的终点
            self.temp_line_end = (event.x(), event.y())
            
            # 更新显示
            self.update_display_with_temp_line()
        
        self.handling_mouse_event = False
    
    def mouse_release_event(self, event):
        """鼠标释放事件处理"""
        # 防止递归调用
        if self.handling_mouse_event:
            return
            
        self.handling_mouse_event = True
        
        # 如果正在拖动，则处理拖动结束逻辑
        if self.image_label.dragging:
            self.image_label.dragging = False
            if self.image_label.space_pressed:
                self.image_label.setCursor(Qt.OpenHandCursor)
            else:
                self.image_label.setCursor(Qt.ArrowCursor)
        elif self.drawing and self.holes and self.current_hole and event.button() == Qt.LeftButton:
            nearest_hole = self.find_nearest_hole(event.pos())
            if nearest_hole and nearest_hole != self.current_hole:
                # 添加连接线
                wire = self.wire_manager.add_wire(self.current_hole, nearest_hole)
                if wire:
                    self.statusBar.showMessage(f'添加连线: ({self.current_hole.x}, {self.current_hole.y}) -> ({nearest_hole.x}, {nearest_hole.y})')
                    # 启用撤销按钮
                    self.undo_button.setEnabled(True)
                else:
                    self.statusBar.showMessage(f'连线已存在')
                
                # 更新显示
                self.update_display()
            else:
                self.statusBar.showMessage('未选择有效的终点孔，取消绘制')
                
            self.drawing = False
            self.current_hole = None
            self.temp_line_end = None
        
        self.handling_mouse_event = False
    
    def update_display(self):
        """更新显示"""
        if self.image is None:
            return
        
        # 创建显示图像的副本
        display_image = self.image.copy()
        
        # 绘制孔
        if self.show_holes_check.isChecked() and self.holes:
            for hole in self.holes:
                cv2.circle(display_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 绘制连接线
        if self.show_wires_check.isChecked():
            display_image = self.wire_manager.draw_all_wires(display_image)
            
        # 显示图像
        self.display_image(display_image)
    
    def update_display_with_temp_line(self):
        """更新显示，包括临时连接线"""
        if self.image is None or not self.current_hole or not self.temp_line_end:
            return
            
        # 创建显示图像
        display_image = self.image.copy()
        
        # 绘制孔
        if self.show_holes_check.isChecked() and self.holes:
            for hole in self.holes:
                cv2.circle(display_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 绘制已有的连接线
        if self.show_wires_check.isChecked():
            display_image = self.wire_manager.draw_all_wires(display_image)
        
        # 获取图像在Label中的位置
        pixmap = self.image_label.pixmap()
        if pixmap:
            # 计算图像在Label中的位置
            img_label_x = (self.image_label.width() - pixmap.width()) / 2 + self.image_label.offset_x
            img_label_y = (self.image_label.height() - pixmap.height()) / 2 + self.image_label.offset_y
            
            # 将临时线终点转换为相对于图像的坐标
            rel_x = self.temp_line_end[0] - img_label_x
            rel_y = self.temp_line_end[1] - img_label_y
            
            # 转换为原始图像坐标
            temp_end_x = int(rel_x / self.image_label.scale_factor)
            temp_end_y = int(rel_y / self.image_label.scale_factor)
            
            # 确保坐标在图像范围内
            h, w = display_image.shape[:2]
            temp_end_x = max(0, min(temp_end_x, w-1))
            temp_end_y = max(0, min(temp_end_y, h-1))
            
            # 绘制临时线
            cv2.line(display_image, self.current_hole.position, (temp_end_x, temp_end_y), (0, 0, 255), 2)
        
        # 显示图像
        self.display_image(display_image)
    
    def update_display_with_path(self):
        """更新显示，包括当前路径"""
        if self.image is None or not self.path_start_hole:
            return
            
        # 创建显示图像
        display_image = self.image.copy()
        
        # 绘制孔
        if self.show_holes_check.isChecked() and self.holes:
            for hole in self.holes:
                cv2.circle(display_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 绘制已有的连接线
        if self.show_wires_check.isChecked():
            display_image = self.wire_manager.draw_all_wires(display_image)
        
        # 获取当前颜色
        color = self.wire_manager.fixed_color if self.wire_manager.use_fixed_color else (0, 0, 255)
        
        # 绘制当前路径
        if self.current_path:
            # 从起点到第一个中间点
            cv2.line(display_image, self.path_start_hole.position, self.current_path[0], color, 2, cv2.LINE_AA)
            
            # 中间点之间的连线
            for i in range(len(self.current_path) - 1):
                cv2.line(display_image, self.current_path[i], self.current_path[i + 1], color, 2, cv2.LINE_AA)
            
            # 绘制中间点
            for point in self.current_path:
                cv2.circle(display_image, point, 3, (255, 0, 0), -1)
        
        # 显示图像
        self.display_image(display_image)
    
    def clear_wires(self):
        """清除所有连接线"""
        if self.image is None:
            return
            
        self.wire_manager.clear()
        self.update_display()
        self.statusBar.showMessage('已清除所有连接线')
        # 启用撤销按钮
        self.undo_button.setEnabled(True)
    
    def save_result(self):
        """保存结果图片"""
        if self.image is None:
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, '保存结果', '', 'Image Files (*.png *.jpg *.jpeg)'
        )
        
        if file_path:
            # 创建最终图像
            final_image = self.image.copy()
            
            # 绘制孔 - 只在显示设置中选择了显示孔时才绘制
            show_holes = QMessageBox.question(
                self, '导出设置', '是否在导出图像中包含绿色辅助点？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) == QMessageBox.Yes
            
            if show_holes and self.holes:
                for hole in self.holes:
                    cv2.circle(final_image, hole.position, int(hole.radius), (0, 255, 0), -1)
            
            # 绘制连接线
            if self.show_wires_check.isChecked():
                final_image = self.wire_manager.draw_all_wires(final_image)
            
            cv2.imwrite(file_path, final_image)
            self.statusBar.showMessage(f'已保存结果: {file_path}')
    
    def export_connections(self):
        """导出连接数据"""
        if not self.holes or not self.wire_manager.wires:
            QMessageBox.warning(self, '警告', '没有连接线可以导出')
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, '导出连接数据', '', 'JSON Files (*.json)'
        )
        
        if file_path:
            # 导出连接数据
            data = self.wire_manager.export_connections()
            
            # 添加孔的数据
            data['holes'] = [{'x': hole.x, 'y': hole.y, 'radius': hole.radius} 
                            for hole in self.holes]
            
            # 保存为JSON文件
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            self.statusBar.showMessage(f'已导出连接数据: {file_path}')
    
    def import_connections(self):
        """导入连接数据"""
        if self.image is None:
            QMessageBox.warning(self, '警告', '请先加载图片')
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, '导入连接数据', '', 'JSON Files (*.json)'
        )
        
        if file_path:
            try:
                # 加载JSON数据
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # 检查是否有孔的数据
                if 'holes' in data:
                    # 创建孔列表
                    self.holes = [Hole(h['x'], h['y'], h.get('radius', 3.0)) 
                                 for h in data['holes']]
                    
                # 创建连接线管理器
                self.wire_manager = WireManager.from_dict(data, self.holes)
                
                # 更新显示
                self.update_display()
                
                # 启用按钮
                self.clear_button.setEnabled(True)
                self.save_button.setEnabled(True)
                self.export_button.setEnabled(True)
                self.undo_button.setEnabled(False)  # 导入后，禁用撤销按钮
                
                self.statusBar.showMessage(f'已导入连接数据: {file_path}')
                
            except Exception as e:
                QMessageBox.critical(self, '错误', f'导入连接数据失败: {str(e)}')
    
    def display_image(self, image):
        """在界面上显示图像"""
        if image is None:
            return
            
        h, w, c = image.shape
        bytes_per_line = 3 * w
        
        # 转换为Qt图像
        q_image = QImage(
            image.data, w, h, bytes_per_line, QImage.Format_RGB888
        ).rgbSwapped()
        
        # 设置图像到可缩放标签
        pixmap = QPixmap.fromImage(q_image)
        self.image_label.set_pixmap(pixmap)

    def keyPressEvent(self, event):
        """处理键盘按键事件"""
        # 将键盘事件传递给图像标签
        if self.image_label:
            self.image_label.keyPressEvent(event)
        else:
            super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """处理键盘释放事件"""
        # 将键盘事件传递给图像标签
        if self.image_label:
            self.image_label.keyReleaseEvent(event)
        else:
            super().keyReleaseEvent(event)

    def undo_last_action(self):
        """撤销上一步操作"""
        if self.wire_manager.undo():
            self.update_display()
            self.statusBar.showMessage('已撤销上一步操作')
        else:
            self.statusBar.showMessage('没有可撤销的操作')

    def on_color_selected(self, color):
        """处理颜色选择"""
        # 颜色名称映射
        color_names = {
            (19, 61, 207): "红色",
            (0, 0, 0): "黑色",
            (68, 121, 53): "绿色",
            (31, 120, 238): "橙色",
            (175, 164, 91): "青色",
            (134, 61, 130): "紫色"
        }
        
        if color is None:
            # 随机颜色模式
            self.wire_manager.set_color_mode(False)
            self.statusBar.showMessage('已选择随机颜色模式')
        else:
            # 固定颜色模式
            self.wire_manager.set_color_mode(True, color)
            color_name = color_names.get(color, "自定义颜色")
            self.statusBar.showMessage(f'已选择固定颜色: {color_name}')

    def toggle_path_mode(self, state):
        """切换多点路径模式"""
        self.path_mode = state == Qt.Checked
        if self.path_mode:
            self.statusBar.showMessage('已启用多点路径模式')
        else:
            self.statusBar.showMessage('已禁用多点路径模式')
            self.cancel_current_path()
    
    def finish_current_path(self):
        """完成当前路径"""
        if not self.path_mode or not self.path_start_hole or not self.current_hole:
            return
            
        # 添加连线（带中间点）
        wire = self.wire_manager.add_wire(self.path_start_hole, self.current_hole, self.current_path)
        if wire:
            self.statusBar.showMessage(f'添加多点路径连线: ({self.path_start_hole.x}, {self.path_start_hole.y}) -> ({self.current_hole.x}, {self.current_hole.y})')
            # 启用撤销按钮
            self.undo_button.setEnabled(True)
        else:
            self.statusBar.showMessage(f'连线已存在')
        
        # 重置路径
        self.path_start_hole = None
        self.current_path = []
        self.finish_path_button.setEnabled(False)
        self.cancel_path_button.setEnabled(False)
        
        # 更新显示
        self.update_display()
    
    def cancel_current_path(self):
        """取消当前路径"""
        if not self.path_mode:
            return
            
        # 重置路径
        self.path_start_hole = None
        self.current_path = []
        self.finish_path_button.setEnabled(False)
        self.cancel_path_button.setEnabled(False)
        
        # 更新显示
        self.update_display()
        self.statusBar.showMessage('已取消当前路径')

    def on_line_width_changed(self, value):
        """处理线宽变化"""
        self.wire_manager.set_line_thickness(value)
        self.line_width_label.setText(str(value))
        self.statusBar.showMessage(f'线宽已设置为: {value}像素')

def main():
    app = QApplication(sys.argv)
    window = BreadboardConnector()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 