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
    # 工具模式常量
    TOOL_SELECT = 'select'
    TOOL_WIRE = 'wire'
    TOOL_PATH = 'path'
    TOOL_FREE = 'free'  # 自由线条工具
    
    def __init__(self):
        super().__init__()
        
        # 初始化变量
        self.image = None
        self.holes = []
        self.wire_manager = WireManager()
        self.hole_detector = HoleDetector()
        
        # 当前工具模式
        self.current_tool = self.TOOL_WIRE  # 默认连线工具
        
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
        
        # 自由线条绘制状态
        self.free_drawing = False
        self.free_start_pos = None
        self.free_waypoints = []
        
        # 拖动控制点状态
        self.dragging_control_point = False
        self.dragging_point_type = None  # 'start', 'end', 'waypoint'
        self.dragging_waypoint_index = None
        
        # 更新节流机制
        # 性能优化说明：
        # 通过限制更新频率避免过度频繁的显示刷新。
        # last_update_time 记录上次更新的时间戳（毫秒）
        # update_interval_ms 设置最小更新间隔（默认 16ms ≈ 60fps）
        # 这可以防止鼠标快速移动时触发过多的绘制操作，降低 CPU 和内存带宽消耗
        self.last_update_time = 0
        self.update_interval_ms = 16  # 约60fps
        
        self.initUI()
    
    def _should_update(self):
        """
        检查是否应该更新显示（节流）
        
        性能优化说明：
        实现更新节流机制，避免过度频繁的显示更新。
        通过比较当前时间与上次更新时间，确保更新间隔不小于 update_interval_ms。
        这在鼠标快速移动、拖动控制点等高频事件中特别有效，
        可以将更新频率限制在 60fps 以内，避免不必要的性能消耗。
        
        Returns:
            bool: 如果距离上次更新已超过设定间隔，返回 True；否则返回 False
        """
        current_time = self._current_time_ms()
        return (current_time - self.last_update_time) >= self.update_interval_ms
    
    def _current_time_ms(self):
        """
        获取当前时间（毫秒）
        
        性能优化说明：
        为节流机制提供时间戳。使用毫秒精度足以满足 60fps 的更新频率控制需求。
        
        Returns:
            int: 当前时间的毫秒表示
        """
        import time
        return int(time.time() * 1000)
        
    def initUI(self):
        self.setWindowTitle('面包板连线工具 v2.1.1')
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
        
        # 工具选择
        tool_group = QGroupBox("工具")
        tool_layout = QVBoxLayout()
        
        self.tool_buttons = QButtonGroup()
        self.tool_buttons.setExclusive(True)
        
        self.select_tool_btn = QRadioButton("🖱️ 选择工具")
        self.select_tool_btn.setToolTip("点击线条进行选中、删除或修改属性")
        self.select_tool_btn.clicked.connect(lambda: self.set_tool(self.TOOL_SELECT))
        
        self.wire_tool_btn = QRadioButton("✏️ 连线工具")
        self.wire_tool_btn.setToolTip("在孔之间绘制连接线")
        self.wire_tool_btn.setChecked(True)
        self.wire_tool_btn.clicked.connect(lambda: self.set_tool(self.TOOL_WIRE))
        
        self.path_tool_btn = QRadioButton("📍 路径工具")
        self.path_tool_btn.setToolTip("绘制多点路径连线，左键添加点，右键完成")
        self.path_tool_btn.clicked.connect(lambda: self.set_tool(self.TOOL_PATH))
        
        self.free_tool_btn = QRadioButton("🖊️ 自由线条")
        self.free_tool_btn.setToolTip("绘制不依赖孔的自由线条，左键添加点，右键完成")
        self.free_tool_btn.clicked.connect(lambda: self.set_tool(self.TOOL_FREE))
        
        self.tool_buttons.addButton(self.select_tool_btn, 0)
        self.tool_buttons.addButton(self.wire_tool_btn, 1)
        self.tool_buttons.addButton(self.path_tool_btn, 2)
        self.tool_buttons.addButton(self.free_tool_btn, 3)
        
        tool_layout.addWidget(self.select_tool_btn)
        tool_layout.addWidget(self.wire_tool_btn)
        tool_layout.addWidget(self.path_tool_btn)
        tool_layout.addWidget(self.free_tool_btn)
        tool_group.setLayout(tool_layout)
        
        # 选中线条属性面板
        self.property_group = QGroupBox("选中线条属性")
        property_layout = QFormLayout()
        
        self.prop_start_label = QLabel("-")
        self.prop_end_label = QLabel("-")
        self.prop_length_label = QLabel("-")
        
        property_layout.addRow("起点:", self.prop_start_label)
        property_layout.addRow("终点:", self.prop_end_label)
        property_layout.addRow("长度:", self.prop_length_label)
        
        # 线条颜色选择
        self.prop_color_combo = QComboBox()
        self.prop_color_combo.addItem("红色", (19, 61, 207))
        self.prop_color_combo.addItem("黑色", (0, 0, 0))
        self.prop_color_combo.addItem("绿色", (68, 121, 53))
        self.prop_color_combo.addItem("橙色", (31, 120, 238))
        self.prop_color_combo.addItem("青色", (175, 164, 91))
        self.prop_color_combo.addItem("紫色", (134, 61, 130))
        self.prop_color_combo.currentIndexChanged.connect(self.on_prop_color_changed)
        self.prop_color_combo.setEnabled(False)
        
        property_layout.addRow("颜色:", self.prop_color_combo)
        
        # 线条宽度
        self.prop_thickness_spin = QSpinBox()
        self.prop_thickness_spin.setRange(1, 10)
        self.prop_thickness_spin.setValue(2)
        self.prop_thickness_spin.valueChanged.connect(self.on_prop_thickness_changed)
        self.prop_thickness_spin.setEnabled(False)
        
        property_layout.addRow("线宽:", self.prop_thickness_spin)
        
        # 删除按钮
        self.delete_wire_btn = QPushButton("删除此线条")
        self.delete_wire_btn.clicked.connect(self.delete_selected_wire)
        self.delete_wire_btn.setEnabled(False)
        self.delete_wire_btn.setStyleSheet("QPushButton { color: red; }")
        
        property_layout.addRow(self.delete_wire_btn)
        
        self.property_group.setLayout(property_layout)
        self.property_group.setVisible(False)  # 默认隐藏
        
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
        self.finish_path_button.setToolTip('或者右键点击终点孔完成')
        self.finish_path_button.clicked.connect(self.finish_current_path)
        self.finish_path_button.setEnabled(False)
        
        # 添加取消路径按钮
        self.cancel_path_button = QPushButton('取消当前路径')
        self.cancel_path_button.setToolTip('取消正在绘制的路径')
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
        control_layout.addWidget(tool_group)
        control_layout.addWidget(self.property_group)
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
    
    def set_tool(self, tool):
        """切换工具模式"""
        self.current_tool = tool
        
        # 取消当前选中和悬停
        self.wire_manager.select_wire(None)
        self.wire_manager.set_hovered_wire(None)
        
        # 取消当前路径绘制
        self.cancel_current_path()
        
        # 取消自由线条绘制
        self.free_drawing = False
        self.free_start_pos = None
        self.free_waypoints = []
        
        # 同步旧的 path_mode_check
        self.path_mode_check.blockSignals(True)
        self.path_mode_check.setChecked(tool == self.TOOL_PATH)
        self.path_mode_check.blockSignals(False)
        
        # 更新属性面板可见性
        self.property_group.setVisible(tool == self.TOOL_SELECT)
        self.update_property_panel()
        
        # 更新鼠标光标
        if tool == self.TOOL_SELECT:
            self.image_label.setCursor(Qt.ArrowCursor)
            self.statusBar.showMessage('选择工具：点击线条进行选中，拖动控制点调整位置')
        elif tool == self.TOOL_WIRE:
            self.image_label.setCursor(Qt.CrossCursor)
            self.statusBar.showMessage('连线工具：在孔之间绘制连接线')
        elif tool == self.TOOL_PATH:
            self.image_label.setCursor(Qt.CrossCursor)
            self.statusBar.showMessage('路径工具：点击起点孔，点击中间孔添加转折，右键点击终点孔完成')
        elif tool == self.TOOL_FREE:
            self.image_label.setCursor(Qt.CrossCursor)
            self.statusBar.showMessage('自由线条：点击起点，移动鼠标，点击添加转折点，右键完成')
        
        self.update_display()
    
    def update_property_panel(self):
        """更新属性面板显示"""
        wire = self.wire_manager.selected_wire
        
        if wire:
            start_x, start_y = wire.start_position
            end_x, end_y = wire.end_position
            
            if wire.is_free:
                self.prop_start_label.setText(f"({start_x}, {start_y}) [自由]")
                self.prop_end_label.setText(f"({end_x}, {end_y}) [自由]")
            else:
                self.prop_start_label.setText(f"({start_x}, {start_y})")
                self.prop_end_label.setText(f"({end_x}, {end_y})")
            
            self.prop_length_label.setText(f"{wire.length():.1f} px")
            
            # 设置颜色下拉框
            color_map = {
                (19, 61, 207): 0,
                (0, 0, 0): 1,
                (68, 121, 53): 2,
                (31, 120, 238): 3,
                (175, 164, 91): 4,
                (134, 61, 130): 5,
            }
            color_index = color_map.get(wire.color, 0)
            self.prop_color_combo.blockSignals(True)
            self.prop_color_combo.setCurrentIndex(color_index)
            self.prop_color_combo.blockSignals(False)
            
            # 设置线宽
            self.prop_thickness_spin.blockSignals(True)
            self.prop_thickness_spin.setValue(wire.thickness)
            self.prop_thickness_spin.blockSignals(False)
            
            # 启用控件
            self.prop_color_combo.setEnabled(True)
            self.prop_thickness_spin.setEnabled(True)
            self.delete_wire_btn.setEnabled(True)
        else:
            self.prop_start_label.setText("-")
            self.prop_end_label.setText("-")
            self.prop_length_label.setText("-")
            self.prop_color_combo.setEnabled(False)
            self.prop_thickness_spin.setEnabled(False)
            self.delete_wire_btn.setEnabled(False)
    
    def on_prop_color_changed(self, index):
        """属性面板颜色改变"""
        color = self.prop_color_combo.currentData()
        if color:
            self.wire_manager.update_selected_wire_color(color)
            self.update_display()
    
    def on_prop_thickness_changed(self, value):
        """属性面板线宽改变"""
        self.wire_manager.update_selected_wire_thickness(value)
        self.update_display()
    
    def delete_selected_wire(self):
        """删除选中的线条"""
        if self.wire_manager.delete_selected_wire():
            self.statusBar.showMessage('已删除选中的线条')
            self.update_property_panel()
            self.update_display()
            self.undo_button.setEnabled(True)
    
    def screen_to_image_coords(self, screen_x, screen_y):
        """将屏幕坐标转换为图像坐标"""
        pixmap = self.image_label.pixmap()
        if not pixmap:
            return None, None
        
        img_label_x = (self.image_label.width() - pixmap.width()) / 2 + self.image_label.offset_x
        img_label_y = (self.image_label.height() - pixmap.height()) / 2 + self.image_label.offset_y
        
        rel_x = screen_x - img_label_x
        rel_y = screen_y - img_label_y
        
        img_x = int(rel_x / self.image_label.scale_factor)
        img_y = int(rel_y / self.image_label.scale_factor)
        
        return img_x, img_y
    
    def find_control_point_at(self, x, y, wire):
        """查找点击位置是否在某个控制点上"""
        if not wire or not wire.selected:
            return None, None
        
        threshold = 10  # 控制点检测阈值
        
        # 检查起点
        start_x, start_y = wire.start_position
        if abs(x - start_x) < threshold and abs(y - start_y) < threshold:
            return 'start', None
        
        # 检查终点
        end_x, end_y = wire.end_position
        if abs(x - end_x) < threshold and abs(y - end_y) < threshold:
            return 'end', None
        
        # 检查中间点
        for i, (wp_x, wp_y) in enumerate(wire.waypoints):
            if abs(x - wp_x) < threshold and abs(y - wp_y) < threshold:
                return 'waypoint', i
        
        return None, None
    
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
            # 根据当前工具处理
            if self.current_tool == self.TOOL_SELECT:
                # 选择工具模式
                img_x, img_y = self.screen_to_image_coords(event.pos().x(), event.pos().y())
                if img_x is not None:
                    # 先检查是否点击了控制点
                    selected_wire = self.wire_manager.selected_wire
                    if selected_wire and selected_wire.is_free:
                        point_type, waypoint_idx = self.find_control_point_at(img_x, img_y, selected_wire)
                        if point_type:
                            # 开始拖动控制点
                            self.dragging_control_point = True
                            self.dragging_point_type = point_type
                            self.dragging_waypoint_index = waypoint_idx
                            self.statusBar.showMessage(f'拖动控制点: {point_type}')
                            self.handling_mouse_event = False
                            return
                    
                    # 没有点击控制点，尝试选中线条
                    wire = self.wire_manager.find_wire_at_point(img_x, img_y)
                    self.wire_manager.select_wire(wire)
                    self.update_property_panel()
                    self.update_display()
                    if wire:
                        if wire.is_free:
                            self.statusBar.showMessage(f'选中自由线条 (可拖动控制点调整)')
                        else:
                            start_x, start_y = wire.start_position
                            end_x, end_y = wire.end_position
                            self.statusBar.showMessage(f'选中线条: ({start_x}, {start_y}) -> ({end_x}, {end_y})')
                    else:
                        self.statusBar.showMessage('未选中任何线条')
            elif self.current_tool == self.TOOL_FREE:
                # 自由线条工具
                img_x, img_y = self.screen_to_image_coords(event.pos().x(), event.pos().y())
                if img_x is not None:
                    if not self.free_drawing:
                        # 开始绘制
                        self.free_drawing = True
                        self.free_start_pos = (img_x, img_y)
                        self.temp_line_end = (event.x(), event.y())
                        self.statusBar.showMessage(f'自由线条起点: ({img_x}, {img_y})，点击添加转折点，右键完成')
                    else:
                        # 添加转折点
                        self.free_waypoints.append((img_x, img_y))
                        self.statusBar.showMessage(f'添加转折点: ({img_x}, {img_y})')
                        self.update_display_with_free_line()
            elif self.current_tool == self.TOOL_WIRE:
                # 连线工具模式
                nearest_hole = self.find_nearest_hole(event.pos())
                if nearest_hole:
                    self.drawing = True
                    self.current_hole = nearest_hole
                    self.temp_line_end = (event.x(), event.y())
                    self.update_display_with_temp_line()
                    self.statusBar.showMessage(f'开始绘制连线，从孔 ({nearest_hole.x}, {nearest_hole.y})')
            elif self.current_tool == self.TOOL_PATH:
                # 路径工具模式
                nearest_hole = self.find_nearest_hole(event.pos())
                if nearest_hole:
                    if not self.path_start_hole:
                        # 如果没有起点，设置起点
                        self.path_start_hole = nearest_hole
                        self.statusBar.showMessage(f'设置路径起点: ({nearest_hole.x}, {nearest_hole.y})，点击中间孔添加转折，右键点击终点孔完成')
                        self.cancel_path_button.setEnabled(True)
                    else:
                        # 如果已有起点，添加中间点
                        if nearest_hole != self.path_start_hole:
                            self.current_path.append((nearest_hole.x, nearest_hole.y))
                            self.current_hole = nearest_hole
                            self.statusBar.showMessage(f'添加路径点: ({nearest_hole.x}, {nearest_hole.y})')
                            self.finish_path_button.setEnabled(True)
                            self.update_display_with_path()
        
        self.handling_mouse_event = False
    
    def mouse_move_event(self, event):
        """
        鼠标移动事件处理
        
        性能优化说明：
        在多个场景中应用了更新节流机制：
        1. 拖动控制点时：通过 _should_update() 检查，避免过度频繁的更新
        2. 选择工具悬停检测：只在悬停线条变化时更新，并应用节流
        3. 自由线条预览：应用节流限制预览更新频率
        4. 临时线条绘制：应用节流限制更新频率
        
        这些优化确保鼠标快速移动时不会触发过多的显示更新，
        将更新频率控制在 60fps 以内，显著降低 CPU 和内存带宽消耗。
        """
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
        elif self.dragging_control_point:
            # 拖动控制点 - 应用节流
            if self._should_update():
                img_x, img_y = self.screen_to_image_coords(event.pos().x(), event.pos().y())
                if img_x is not None:
                    wire = self.wire_manager.selected_wire
                    if wire and wire.is_free:
                        if self.dragging_point_type == 'start':
                            self.wire_manager.update_wire_position(wire, start_pos=(img_x, img_y))
                        elif self.dragging_point_type == 'end':
                            self.wire_manager.update_wire_position(wire, end_pos=(img_x, img_y))
                        elif self.dragging_point_type == 'waypoint':
                            self.wire_manager.update_wire_position(wire, waypoint_index=self.dragging_waypoint_index, 
                                                                  waypoint_pos=(img_x, img_y))
                        self.update_display()
                        self.last_update_time = self._current_time_ms()
        elif self.current_tool == self.TOOL_SELECT and self.image is not None:
            # 选择工具模式：检测悬停 - 应用节流
            if self._should_update():
                img_x, img_y = self.screen_to_image_coords(event.pos().x(), event.pos().y())
                if img_x is not None:
                    wire = self.wire_manager.find_wire_at_point(img_x, img_y)
                    if wire != self.wire_manager.hovered_wire:
                        self.wire_manager.set_hovered_wire(wire)
                        self.update_display()
                        self.last_update_time = self._current_time_ms()
                        # 更新鼠标光标
                        if wire:
                            self.image_label.setCursor(Qt.PointingHandCursor)
                        else:
                            self.image_label.setCursor(Qt.ArrowCursor)
        elif self.current_tool == self.TOOL_FREE and self.free_drawing:
            # 自由线条绘制：更新预览 - 应用节流
            if self._should_update():
                self.temp_line_end = (event.x(), event.y())
                self.update_display_with_free_line()
                self.last_update_time = self._current_time_ms()
        elif self.drawing and self.holes and self.current_hole:
            # 更新临时线的终点 - 应用节流
            if self._should_update():
                self.temp_line_end = (event.x(), event.y())
                
                # 更新显示
                self.update_display_with_temp_line()
                self.last_update_time = self._current_time_ms()
        
        self.handling_mouse_event = False
    
    def mouse_release_event(self, event):
        """鼠标释放事件处理"""
        # 防止递归调用
        if self.handling_mouse_event:
            return
            
        self.handling_mouse_event = True
        
        # 如果正在拖动视图
        if self.image_label.dragging:
            self.image_label.dragging = False
            if self.image_label.space_pressed:
                self.image_label.setCursor(Qt.OpenHandCursor)
            else:
                self.image_label.setCursor(Qt.ArrowCursor)
        # 如果正在拖动控制点
        elif self.dragging_control_point:
            self.dragging_control_point = False
            self.dragging_point_type = None
            self.dragging_waypoint_index = None
            self.update_property_panel()  # 更新长度显示
            self.statusBar.showMessage('控制点调整完成')
        # 自由线条工具：右键完成绘制
        elif self.current_tool == self.TOOL_FREE and self.free_drawing and event.button() == Qt.RightButton:
            # 如果有转折点，使用最后一个转折点作为终点
            if self.free_waypoints:
                end_pos = self.free_waypoints[-1]
                # 移除最后一个转折点（因为它现在是终点）
                waypoints = self.free_waypoints[:-1] if len(self.free_waypoints) > 1 else None
            else:
                # 没有转折点，使用右键点击位置作为终点
                img_x, img_y = self.screen_to_image_coords(event.pos().x(), event.pos().y())
                if img_x is None:
                    self.handling_mouse_event = False
                    return
                end_pos = (img_x, img_y)
                waypoints = None
            
            # 创建自由线条
            wire = self.wire_manager.add_free_wire(
                self.free_start_pos, 
                end_pos,
                waypoints
            )
            self.statusBar.showMessage(f'完成自由线条绘制')
            self.undo_button.setEnabled(True)
            
            # 重置状态
            self.free_drawing = False
            self.free_start_pos = None
            self.free_waypoints = []
            self.temp_line_end = None
            
            # 更新显示
            self.update_display()
        # 路径工具：右键完成路径
        elif self.current_tool == self.TOOL_PATH and self.path_start_hole and event.button() == Qt.RightButton:
            # 如果有中间点，使用最后一个中间点对应的孔作为终点
            if self.current_hole and self.current_path:
                # 使用最后点击的孔作为终点
                end_hole = self.current_hole
                # 移除最后一个中间点（因为它现在是终点）
                waypoints = self.current_path[:-1] if len(self.current_path) > 1 else None
                
                # 添加连线
                wire = self.wire_manager.add_wire(self.path_start_hole, end_hole, waypoints)
                if wire:
                    self.statusBar.showMessage(f'完成多点路径连线: ({self.path_start_hole.x}, {self.path_start_hole.y}) -> ({end_hole.x}, {end_hole.y})')
                    self.undo_button.setEnabled(True)
                else:
                    self.statusBar.showMessage(f'连线已存在')
            else:
                # 没有中间点，找右键点击位置最近的孔作为终点
                nearest_hole = self.find_nearest_hole(event.pos())
                if nearest_hole and nearest_hole != self.path_start_hole:
                    wire = self.wire_manager.add_wire(self.path_start_hole, nearest_hole, None)
                    if wire:
                        self.statusBar.showMessage(f'完成路径连线: ({self.path_start_hole.x}, {self.path_start_hole.y}) -> ({nearest_hole.x}, {nearest_hole.y})')
                        self.undo_button.setEnabled(True)
                    else:
                        self.statusBar.showMessage(f'连线已存在')
                else:
                    self.statusBar.showMessage('未找到有效的终点孔，取消路径')
            
            # 重置路径
            self.path_start_hole = None
            self.current_path = []
            self.current_hole = None
            self.finish_path_button.setEnabled(False)
            self.cancel_path_button.setEnabled(False)
            
            # 更新显示
            self.update_display()
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
        """
        更新显示（优化版本 - 只创建一次图像副本）
        
        性能优化说明：
        这是主显示更新方法的优化版本，遵循"创建副本 → 绘制孔 → 绘制线条 → 显示"的流程。
        关键优化点：
        1. 只在开始时创建一次图像副本（唯一的内存拷贝）
        2. 直接在副本上绘制孔位（原地修改，无额外拷贝）
        3. 调用优化后的 draw_all_wires，它会直接在副本上绘制所有线条（无额外拷贝）
        
        优化前：每条线都会创建副本，导致链式拷贝
        优化后：整个绘制过程只有一次图像拷贝
        
        对于包含 N 条线的场景，内存拷贝量从 O(N) 降低到 O(1)。
        """
        if self.image is None:
            return
        
        # 创建显示图像的副本（唯一的拷贝）
        display_image = self.image.copy()
        
        # 直接在副本上绘制孔（原地修改，无额外拷贝）
        if self.show_holes_check.isChecked() and self.holes:
            for hole in self.holes:
                cv2.circle(display_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 调用优化后的 draw_all_wires（直接在 display_image 上绘制）
        if self.show_wires_check.isChecked():
            display_image = self.wire_manager.draw_all_wires(display_image)
            
        # 显示图像
        self.display_image(display_image)
    
    def update_display_with_temp_line(self):
        """
        更新显示，包括临时连接线（优化版本 - 只创建一次图像副本）
        
        性能优化说明：
        应用与 update_display 相同的优化策略：
        1. 只在开始时创建一次图像副本
        2. 直接在副本上绘制孔位（无额外拷贝）
        3. 调用优化后的 draw_all_wires（无额外拷贝）
        4. 直接在副本上绘制临时线条（无额外拷贝）
        
        确保在绘制预览线条时也不会产生链式图像拷贝。
        """
        if self.image is None or not self.current_hole or not self.temp_line_end:
            return
            
        # 创建显示图像的副本（唯一的拷贝）
        display_image = self.image.copy()
        
        # 直接在副本上绘制孔（原地修改，无额外拷贝）
        if self.show_holes_check.isChecked() and self.holes:
            for hole in self.holes:
                cv2.circle(display_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 调用优化后的 draw_all_wires（直接在 display_image 上绘制）
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
            
            # 直接在 display_image 上绘制临时线（无额外拷贝）
            cv2.line(display_image, self.current_hole.position, (temp_end_x, temp_end_y), (0, 0, 255), 2)
        
        # 显示图像
        self.display_image(display_image)
    
    def update_display_with_path(self):
        """
        更新显示，包括当前路径（优化版本 - 只创建一次图像副本）
        
        性能优化说明：
        应用与 update_display 相同的优化策略：
        1. 只在开始时创建一次图像副本
        2. 直接在副本上绘制孔位（无额外拷贝）
        3. 调用优化后的 draw_all_wires（无额外拷贝）
        4. 直接在副本上绘制当前路径预览（无额外拷贝）
        
        确保在绘制多点路径预览时也不会产生链式图像拷贝。
        """
        if self.image is None or not self.path_start_hole:
            return
            
        # 创建显示图像的副本（唯一的拷贝）
        display_image = self.image.copy()
        
        # 直接在副本上绘制孔（原地修改，无额外拷贝）
        if self.show_holes_check.isChecked() and self.holes:
            for hole in self.holes:
                cv2.circle(display_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 调用优化后的 draw_all_wires（直接在 display_image 上绘制）
        if self.show_wires_check.isChecked():
            display_image = self.wire_manager.draw_all_wires(display_image)
        
        # 获取当前颜色
        color = self.wire_manager.fixed_color if self.wire_manager.use_fixed_color else (0, 0, 255)
        
        # 直接在 display_image 上绘制当前路径（无额外拷贝）
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
    
    def update_display_with_free_line(self):
        """
        更新显示，包括自由线条预览（优化版本 - 只创建一次图像副本）
        
        性能优化说明：
        应用与 update_display 相同的优化策略：
        1. 只在开始时创建一次图像副本
        2. 直接在副本上绘制孔位（无额外拷贝）
        3. 调用优化后的 draw_all_wires（无额外拷贝）
        4. 直接在副本上绘制自由线条预览（无额外拷贝）
        
        确保在绘制自由线条预览时也不会产生链式图像拷贝。
        """
        if self.image is None or not self.free_drawing or not self.free_start_pos or not self.temp_line_end:
            return
            
        # 创建显示图像的副本（唯一的拷贝）
        display_image = self.image.copy()
        
        # 直接在副本上绘制孔（原地修改，无额外拷贝）
        if self.show_holes_check.isChecked() and self.holes:
            for hole in self.holes:
                cv2.circle(display_image, hole.position, int(hole.radius), (0, 255, 0), -1)
        
        # 调用优化后的 draw_all_wires（直接在 display_image 上绘制）
        if self.show_wires_check.isChecked():
            display_image = self.wire_manager.draw_all_wires(display_image)
        
        # 获取当前颜色
        color = self.wire_manager.fixed_color if self.wire_manager.use_fixed_color else (0, 0, 255)
        
        # 获取图像在Label中的位置
        pixmap = self.image_label.pixmap()
        if pixmap:
            img_label_x = (self.image_label.width() - pixmap.width()) / 2 + self.image_label.offset_x
            img_label_y = (self.image_label.height() - pixmap.height()) / 2 + self.image_label.offset_y
            
            # 将临时线终点转换为图像坐标
            rel_x = self.temp_line_end[0] - img_label_x
            rel_y = self.temp_line_end[1] - img_label_y
            temp_end_x = int(rel_x / self.image_label.scale_factor)
            temp_end_y = int(rel_y / self.image_label.scale_factor)
            
            # 确保坐标在图像范围内
            h, w = display_image.shape[:2]
            temp_end_x = max(0, min(temp_end_x, w-1))
            temp_end_y = max(0, min(temp_end_y, h-1))
            
            # 直接在 display_image 上绘制自由线条预览（无额外拷贝）
            if not self.free_waypoints:
                # 没有中间点，直接画线
                cv2.line(display_image, self.free_start_pos, (temp_end_x, temp_end_y), color, 2, cv2.LINE_AA)
            else:
                # 有中间点，画折线
                cv2.line(display_image, self.free_start_pos, self.free_waypoints[0], color, 2, cv2.LINE_AA)
                for i in range(len(self.free_waypoints) - 1):
                    cv2.line(display_image, self.free_waypoints[i], self.free_waypoints[i + 1], color, 2, cv2.LINE_AA)
                cv2.line(display_image, self.free_waypoints[-1], (temp_end_x, temp_end_y), color, 2, cv2.LINE_AA)
                
                # 绘制中间点
                for point in self.free_waypoints:
                    cv2.circle(display_image, point, 4, (255, 0, 0), -1)
            
            # 绘制起点
            cv2.circle(display_image, self.free_start_pos, 5, color, -1)
        
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
                
                # 清空历史记录，避免撤销到导入前的状态
                self.wire_manager.clear_history()
                
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
        # Delete 键删除选中的线条
        if event.key() == Qt.Key_Delete:
            if self.current_tool == self.TOOL_SELECT and self.wire_manager.selected_wire:
                self.delete_selected_wire()
                return
        
        # ESC 键取消当前绘制
        if event.key() == Qt.Key_Escape:
            if self.current_tool == self.TOOL_PATH and self.path_start_hole:
                # 取消路径绘制
                self.cancel_current_path()
                self.statusBar.showMessage('已取消路径绘制')
                return
            elif self.current_tool == self.TOOL_FREE and self.free_drawing:
                # 取消自由线条绘制
                self.free_drawing = False
                self.free_start_pos = None
                self.free_waypoints = []
                self.temp_line_end = None
                self.update_display()
                self.statusBar.showMessage('已取消自由线条绘制')
                return
        
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
        """切换多点路径模式（旧的 checkbox 方式，保持兼容）"""
        if state == Qt.Checked:
            self.set_tool(self.TOOL_PATH)
            self.path_tool_btn.setChecked(True)
        else:
            self.set_tool(self.TOOL_WIRE)
            self.wire_tool_btn.setChecked(True)
    
    def finish_current_path(self):
        """完成当前路径"""
        if self.current_tool != self.TOOL_PATH or not self.path_start_hole or not self.current_hole:
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