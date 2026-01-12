#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cv2
import numpy as np
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass, field
from hole_detector import Hole

@dataclass
class Wire:
    """表示面包板上的一条连接线"""
    start: Hole
    end: Hole
    color: Tuple[int, int, int] = (0, 0, 255)  # BGR格式，默认红色
    thickness: int = 2
    waypoints: List[Tuple[int, int]] = field(default_factory=list)  # 路径中间点
    
    def draw(self, image: np.ndarray) -> np.ndarray:
        """在图像上绘制连接线"""
        result = image.copy()
        
        if not self.waypoints:
            # 如果没有中间点，直接绘制直线
            cv2.line(result, self.start.position, self.end.position, 
                    self.color, self.thickness, cv2.LINE_AA)
        else:
            # 如果有中间点，绘制折线
            # 从起点到第一个中间点
            cv2.line(result, self.start.position, self.waypoints[0], 
                    self.color, self.thickness, cv2.LINE_AA)
            
            # 中间点之间的连线
            for i in range(len(self.waypoints) - 1):
                cv2.line(result, self.waypoints[i], self.waypoints[i + 1], 
                        self.color, self.thickness, cv2.LINE_AA)
            
            # 最后一个中间点到终点
            cv2.line(result, self.waypoints[-1], self.end.position, 
                    self.color, self.thickness, cv2.LINE_AA)
        
        # 在起点和终点绘制圆点
        dot_radius = self.thickness + 2  # 圆点半径比线宽大2个像素
        cv2.circle(result, self.start.position, dot_radius, self.color, -1, cv2.LINE_AA)
        cv2.circle(result, self.end.position, dot_radius, self.color, -1, cv2.LINE_AA)
        
        return result
    
    def length(self) -> float:
        """计算连接线的长度"""
        total_length = 0.0
        
        if not self.waypoints:
            # 如果没有中间点，直接计算起点到终点的距离
            dx = self.start.x - self.end.x
            dy = self.start.y - self.end.y
            return np.sqrt(dx*dx + dy*dy)
        else:
            # 计算起点到第一个中间点的距离
            dx = self.start.x - self.waypoints[0][0]
            dy = self.start.y - self.waypoints[0][1]
            total_length += np.sqrt(dx*dx + dy*dy)
            
            # 计算中间点之间的距离
            for i in range(len(self.waypoints) - 1):
                dx = self.waypoints[i][0] - self.waypoints[i+1][0]
                dy = self.waypoints[i][1] - self.waypoints[i+1][1]
                total_length += np.sqrt(dx*dx + dy*dy)
            
            # 计算最后一个中间点到终点的距离
            dx = self.waypoints[-1][0] - self.end.x
            dy = self.waypoints[-1][1] - self.end.y
            total_length += np.sqrt(dx*dx + dy*dy)
            
            return total_length
    
    def __eq__(self, other):
        """判断两条线是否相等（连接相同的孔）"""
        if not isinstance(other, Wire):
            return False
        
        # 两条线连接相同的孔（不考虑方向和中间点）
        return ((self.start.position == other.start.position and 
                self.end.position == other.end.position) or
               (self.start.position == other.end.position and 
                self.end.position == other.start.position))

class WireManager:
    """管理面包板上的连接线"""
    
    def __init__(self):
        self.wires: List[Wire] = []
        self.wire_history: List[List[Wire]] = []  # 用于撤销功能的历史记录
        self.colors = [
            (19, 61, 207),    # 红色 #cf3d13 (BGR格式)
            (0, 0, 0),        # 黑色
            (68, 121, 53),    # 绿色 #357944 (BGR格式)
            (31, 120, 238),   # 橙色 #ee781f (BGR格式)
            (175, 164, 91),   # 青色 #5ba4af (BGR格式)
            (134, 61, 130),   # 紫色 #823d86 (BGR格式)
        ]
        self.current_color_index = 0
        self.use_fixed_color = False  # 是否使用固定颜色
        self.fixed_color = (19, 61, 207)  # 默认固定颜色为红色 #cf3d13
        self.line_thickness = 5  # 默认线宽
    
    def add_wire(self, start_hole: Hole, end_hole: Hole, waypoints: List[Tuple[int, int]] = None) -> Optional[Wire]:
        """
        添加一条连接线
        
        Args:
            start_hole: 起始孔
            end_hole: 结束孔
            waypoints: 路径中间点，默认为None（直线）
            
        Returns:
            添加的连接线，如果已存在则返回None
        """
        # 保存当前状态到历史记录
        self.save_state()
        
        # 检查是否已存在相同的连接
        color = self.fixed_color if self.use_fixed_color else self.get_next_color()
        new_wire = Wire(start_hole, end_hole, color, self.line_thickness)
        
        # 添加中间点
        if waypoints:
            new_wire.waypoints = waypoints
        
        # 检查是否已存在相同的连线（不考虑中间点）
        for wire in self.wires:
            if wire == new_wire:
                return None
        
        self.wires.append(new_wire)
        return new_wire
    
    def remove_wire(self, wire: Wire) -> bool:
        """
        移除一条连接线
        
        Args:
            wire: 要移除的连接线
            
        Returns:
            是否成功移除
        """
        # 保存当前状态到历史记录
        self.save_state()
        
        if wire in self.wires:
            self.wires.remove(wire)
            return True
        return False
    
    def remove_wire_between_holes(self, hole1: Hole, hole2: Hole) -> bool:
        """
        移除连接两个孔的线
        
        Args:
            hole1: 第一个孔
            hole2: 第二个孔
            
        Returns:
            是否成功移除
        """
        # 保存当前状态到历史记录
        self.save_state()
        
        temp_wire = Wire(hole1, hole2)
        
        for wire in self.wires:
            if wire == temp_wire:
                self.wires.remove(wire)
                return True
        
        return False
    
    def save_state(self):
        """保存当前状态到历史记录"""
        # 创建当前连线的深拷贝
        current_state = []
        for wire in self.wires:
            new_wire = Wire(wire.start, wire.end, wire.color, wire.thickness)
            new_wire.waypoints = wire.waypoints.copy() if wire.waypoints else []
            current_state.append(new_wire)
            
        self.wire_history.append(current_state)
        
        # 限制历史记录长度，防止内存占用过多
        if len(self.wire_history) > 50:  # 最多保存50步
            self.wire_history.pop(0)
    
    def undo(self) -> bool:
        """
        撤销上一步操作
        
        Returns:
            是否成功撤销
        """
        if not self.wire_history:
            return False
        
        # 恢复到上一个状态
        previous_state = self.wire_history.pop()
        self.wires = previous_state
        return True
    
    def set_color_mode(self, use_fixed: bool, color: Tuple[int, int, int] = None):
        """
        设置颜色模式
        
        Args:
            use_fixed: 是否使用固定颜色
            color: 固定颜色，如果为None则不改变当前固定颜色
        """
        self.use_fixed_color = use_fixed
        if color is not None:
            self.fixed_color = color
    
    def set_line_thickness(self, thickness: int):
        """
        设置线宽
        
        Args:
            thickness: 线宽，单位为像素
        """
        self.line_thickness = max(1, min(10, thickness))  # 限制在1-10之间
    
    def get_next_color(self) -> Tuple[int, int, int]:
        """获取下一个颜色"""
        color = self.colors[self.current_color_index]
        self.current_color_index = (self.current_color_index + 1) % len(self.colors)
        return color
    
    def clear(self):
        """清除所有连接线"""
        # 保存当前状态到历史记录
        if self.wires:
            self.save_state()
        self.wires.clear()
    
    def draw_all_wires(self, image: np.ndarray) -> np.ndarray:
        """
        在图像上绘制所有连接线
        
        Args:
            image: 输入图像
            
        Returns:
            带有连接线的图像
        """
        result = image.copy()
        
        for wire in self.wires:
            result = wire.draw(result)
            
        return result
    
    def get_connected_components(self) -> List[Set[Hole]]:
        """
        获取连通分量（连接在一起的孔的集合）
        
        Returns:
            连通分量列表，每个连通分量是一个孔的集合
        """
        # 构建无向图
        graph: Dict[Tuple[int, int], Set[Tuple[int, int]]] = {}
        
        # 添加所有孔作为节点
        for wire in self.wires:
            start_pos = wire.start.position
            end_pos = wire.end.position
            
            if start_pos not in graph:
                graph[start_pos] = set()
            if end_pos not in graph:
                graph[end_pos] = set()
                
            # 添加边
            graph[start_pos].add(end_pos)
            graph[end_pos].add(start_pos)
        
        # 查找连通分量
        visited = set()
        components = []
        
        for node in graph:
            if node not in visited:
                # 开始一个新的连通分量
                component = set()
                queue = [node]
                visited.add(node)
                
                while queue:
                    current = queue.pop(0)
                    component.add(current)
                    
                    for neighbor in graph[current]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                
                # 将坐标转换回Hole对象
                hole_component = set()
                for pos in component:
                    for wire in self.wires:
                        if wire.start.position == pos:
                            hole_component.add(wire.start)
                        if wire.end.position == pos:
                            hole_component.add(wire.end)
                
                components.append(hole_component)
        
        return components
    
    def export_connections(self) -> Dict:
        """
        导出连接数据
        
        Returns:
            包含连接数据的字典
        """
        connections = []
        for wire in self.wires:
            connection = {
                'start': {'x': wire.start.x, 'y': wire.start.y},
                'end': {'x': wire.end.x, 'y': wire.end.y},
                'color': list(wire.color),
                'thickness': wire.thickness
            }
            
            # 如果有中间点，也导出
            if wire.waypoints:
                connection['waypoints'] = [{'x': x, 'y': y} for x, y in wire.waypoints]
                
            connections.append(connection)
            
        # 导出当前线宽设置
        settings = {
            'line_thickness': self.line_thickness,
            'use_fixed_color': self.use_fixed_color,
            'fixed_color': list(self.fixed_color) if self.fixed_color else None
        }
            
        return {
            'connections': connections,
            'settings': settings
        }
    
    @classmethod
    def from_dict(cls, data: Dict, holes: List[Hole]) -> 'WireManager':
        """
        从字典创建WireManager
        
        Args:
            data: 包含连接数据的字典
            holes: 孔列表
            
        Returns:
            创建的WireManager实例
        """
        manager = cls()
        
        if 'connections' not in data:
            return manager
            
        # 创建孔位置到孔对象的映射
        hole_map = {(hole.x, hole.y): hole for hole in holes}
        
        # 加载设置
        if 'settings' in data:
            settings = data['settings']
            manager.line_thickness = settings.get('line_thickness', 2)
            manager.use_fixed_color = settings.get('use_fixed_color', False)
            if settings.get('fixed_color'):
                manager.fixed_color = tuple(settings['fixed_color'])
        
        for conn in data['connections']:
            start_x, start_y = conn['start']['x'], conn['start']['y']
            end_x, end_y = conn['end']['x'], conn['end']['y']
            
            # 查找对应的孔对象
            start_hole = hole_map.get((start_x, start_y))
            end_hole = hole_map.get((end_x, end_y))
            
            if start_hole and end_hole:
                # 创建连接线
                color = tuple(conn.get('color', (0, 0, 255)))
                thickness = conn.get('thickness', 2)
                
                wire = Wire(start_hole, end_hole, color, thickness)
                
                # 如果有中间点，也导入
                if 'waypoints' in conn:
                    wire.waypoints = [(wp['x'], wp['y']) for wp in conn['waypoints']]
                    
                manager.wires.append(wire)
                
        return manager 