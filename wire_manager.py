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
    start: Hole = None  # 起始孔，自由线条时为None
    end: Hole = None    # 结束孔，自由线条时为None
    color: Tuple[int, int, int] = (0, 0, 255)  # BGR格式，默认红色
    thickness: int = 2
    waypoints: List[Tuple[int, int]] = field(default_factory=list)  # 路径中间点
    id: int = field(default_factory=lambda: Wire._next_id())  # 唯一标识
    selected: bool = False  # 是否被选中
    hovered: bool = False   # 是否被悬停
    is_free: bool = False   # 是否是自由线条（不依赖孔）
    start_pos: Tuple[int, int] = None  # 自由线条的起点坐标
    end_pos: Tuple[int, int] = None    # 自由线条的终点坐标
    
    _id_counter: int = field(default=0, init=False, repr=False, compare=False)
    
    @staticmethod
    def _next_id() -> int:
        Wire._id_counter_value = getattr(Wire, '_id_counter_value', 0) + 1
        return Wire._id_counter_value
    
    @property
    def start_position(self) -> Tuple[int, int]:
        """获取起点坐标（兼容孔和自由线条）"""
        if self.is_free:
            return self.start_pos
        return self.start.position if self.start else (0, 0)
    
    @property
    def end_position(self) -> Tuple[int, int]:
        """获取终点坐标（兼容孔和自由线条）"""
        if self.is_free:
            return self.end_pos
        return self.end.position if self.end else (0, 0)
    
    def draw_on_image(self, image: np.ndarray) -> None:
        """
        直接在提供的图像上绘制连接线（原地修改）
        
        性能优化说明：
        此方法直接在输入图像上进行绘制操作，避免创建图像副本。
        这是性能优化的核心方法，消除了链式图像拷贝问题。
        当绘制多条线时，所有线条都在同一个图像缓冲区上依次绘制，
        而不是每条线都创建一个新的副本，从而将内存拷贝量从 O(N) 降低到 O(1)。
        
        Args:
            image: 要绘制的目标图像（会被直接修改）
        
        Returns:
            None（直接修改输入图像）
        """
        # 根据状态调整绘制样式
        draw_color = self.color
        draw_thickness = self.thickness
        
        if self.selected:
            # 选中状态：先绘制高亮边框
            highlight_thickness = self.thickness + 4
            highlight_color = (255, 255, 255)  # 白色边框
            self._draw_line_path(image, highlight_color, highlight_thickness)
        
        if self.hovered and not self.selected:
            # 悬停状态：线条加粗
            draw_thickness = self.thickness + 2
        
        # 绘制主线条
        self._draw_line_path(image, draw_color, draw_thickness)
        
        # 在起点和终点绘制圆点
        dot_radius = self.thickness + 2
        cv2.circle(image, self.start_position, dot_radius, draw_color, -1, cv2.LINE_AA)
        cv2.circle(image, self.end_position, dot_radius, draw_color, -1, cv2.LINE_AA)
        
        # 选中状态：绘制端点控制点
        if self.selected:
            control_size = 6
            # 起点控制点（白色方块带黑边）
            self._draw_control_point(image, self.start_position, control_size)
            self._draw_control_point(image, self.end_position, control_size)
            # 中间点控制点
            for wp in self.waypoints:
                self._draw_control_point(image, wp, control_size - 2)
    
    def draw(self, image: np.ndarray) -> np.ndarray:
        """
        在图像副本上绘制连接线（向后兼容）
        
        性能优化说明：
        此方法保留用于向后兼容，内部调用 draw_on_image 方法。
        新代码应优先使用 draw_on_image 以获得更好的性能。
        此方法会创建一次图像副本，然后在副本上直接绘制。
        
        Args:
            image: 输入图像
            
        Returns:
            带有连接线的新图像
        """
        result = image.copy()
        self.draw_on_image(result)
        return result
    
    def _draw_line_path(self, image: np.ndarray, color: Tuple[int, int, int], thickness: int) -> None:
        """
        绘制线条路径（直接在图像上绘制）
        
        性能优化说明：
        此方法直接在输入图像上绘制，不返回新图像，避免不必要的内存拷贝。
        使用 cv2.LINE_AA 抗锯齿标志提升视觉质量。
        
        Args:
            image: 要绘制的目标图像（会被直接修改）
            color: 线条颜色
            thickness: 线条粗细
        
        Returns:
            None（直接修改输入图像）
        """
        if not self.waypoints:
            cv2.line(image, self.start_position, self.end_position, 
                    color, thickness, cv2.LINE_AA)
        else:
            cv2.line(image, self.start_position, self.waypoints[0], 
                    color, thickness, cv2.LINE_AA)
            for i in range(len(self.waypoints) - 1):
                cv2.line(image, self.waypoints[i], self.waypoints[i + 1], 
                        color, thickness, cv2.LINE_AA)
            cv2.line(image, self.waypoints[-1], self.end_position, 
                    color, thickness, cv2.LINE_AA)
    
    def _draw_control_point(self, image: np.ndarray, position: Tuple[int, int], size: int) -> None:
        """
        绘制控制点（方块）（直接在图像上绘制）
        
        性能优化说明：
        此方法直接在输入图像上绘制控制点，不返回新图像，避免内存拷贝。
        
        Args:
            image: 要绘制的目标图像（会被直接修改）
            position: 控制点位置
            size: 控制点大小
        
        Returns:
            None（直接修改输入图像）
        """
        x, y = position
        # 黑色边框
        cv2.rectangle(image, (x - size, y - size), (x + size, y + size), (0, 0, 0), 2)
        # 白色填充
        cv2.rectangle(image, (x - size + 1, y - size + 1), (x + size - 1, y + size - 1), (255, 255, 255), -1)
    
    def length(self) -> float:
        """计算连接线的长度"""
        total_length = 0.0
        
        if not self.waypoints:
            # 如果没有中间点，直接计算起点到终点的距离
            start_x, start_y = self.start_position
            end_x, end_y = self.end_position
            dx = start_x - end_x
            dy = start_y - end_y
            return np.sqrt(dx*dx + dy*dy)
        else:
            # 计算起点到第一个中间点的距离
            start_x, start_y = self.start_position
            dx = start_x - self.waypoints[0][0]
            dy = start_y - self.waypoints[0][1]
            total_length += np.sqrt(dx*dx + dy*dy)
            
            # 计算中间点之间的距离
            for i in range(len(self.waypoints) - 1):
                dx = self.waypoints[i][0] - self.waypoints[i+1][0]
                dy = self.waypoints[i][1] - self.waypoints[i+1][1]
                total_length += np.sqrt(dx*dx + dy*dy)
            
            # 计算最后一个中间点到终点的距离
            end_x, end_y = self.end_position
            dx = self.waypoints[-1][0] - end_x
            dy = self.waypoints[-1][1] - end_y
            total_length += np.sqrt(dx*dx + dy*dy)
            
            return total_length
    
    def __eq__(self, other):
        """判断两条线是否相等（连接相同的孔）"""
        if not isinstance(other, Wire):
            return False
        
        # 自由线条不参与相等性比较
        if self.is_free or other.is_free:
            return False
        
        # 检查是否有 None 的孔（防止访问 None.position）
        if self.start is None or self.end is None or other.start is None or other.end is None:
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
        self.selected_wire: Optional[Wire] = None  # 当前选中的线条
        self.hovered_wire: Optional[Wire] = None   # 当前悬停的线条
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
    
    def point_to_segment_distance(self, px: int, py: int, 
                                   x1: int, y1: int, x2: int, y2: int) -> float:
        """计算点到线段的距离"""
        dx = x2 - x1
        dy = y2 - y1
        
        if dx == 0 and dy == 0:
            return np.sqrt((px - x1) ** 2 + (py - y1) ** 2)
        
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        nearest_x = x1 + t * dx
        nearest_y = y1 + t * dy
        
        return np.sqrt((px - nearest_x) ** 2 + (py - nearest_y) ** 2)
    
    def distance_to_wire(self, x: int, y: int, wire: Wire) -> float:
        """计算点到线条的最短距离"""
        min_distance = float('inf')
        points = [wire.start_position] + wire.waypoints + [wire.end_position]
        
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            dist = self.point_to_segment_distance(x, y, x1, y1, x2, y2)
            min_distance = min(min_distance, dist)
        
        return min_distance
    
    def find_wire_at_point(self, x: int, y: int, threshold: float = 8) -> Optional[Wire]:
        """找到点击位置附近的线条"""
        for wire in reversed(self.wires):
            distance = self.distance_to_wire(x, y, wire)
            if distance < threshold:
                return wire
        return None
    
    def select_wire(self, wire: Optional[Wire]):
        """选中一条线"""
        if self.selected_wire:
            self.selected_wire.selected = False
        self.selected_wire = wire
        if wire:
            wire.selected = True
    
    def set_hovered_wire(self, wire: Optional[Wire]):
        """设置悬停的线条"""
        if self.hovered_wire == wire:
            return
        if self.hovered_wire:
            self.hovered_wire.hovered = False
        self.hovered_wire = wire
        if wire:
            wire.hovered = True
    
    def delete_selected_wire(self) -> bool:
        """删除选中的线条"""
        if not self.selected_wire:
            return False
        self.save_state()
        if self.selected_wire in self.wires:
            self.wires.remove(self.selected_wire)
            self.selected_wire = None
            return True
        return False
    
    def update_selected_wire_color(self, color: Tuple[int, int, int]):
        """更新选中线条的颜色"""
        if self.selected_wire:
            self.save_state()
            self.selected_wire.color = color
    
    def update_selected_wire_thickness(self, thickness: int):
        """更新选中线条的线宽"""
        if self.selected_wire:
            self.save_state()
            self.selected_wire.thickness = thickness
    
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
    
    def add_free_wire(self, start_pos: Tuple[int, int], end_pos: Tuple[int, int], 
                      waypoints: List[Tuple[int, int]] = None) -> Wire:
        """
        添加一条自由线条（不依赖孔）
        
        Args:
            start_pos: 起点坐标
            end_pos: 终点坐标
            waypoints: 路径中间点，默认为None（直线）
            
        Returns:
            添加的自由线条
        """
        # 保存当前状态到历史记录
        self.save_state()
        
        # 创建自由线条
        color = self.fixed_color if self.use_fixed_color else self.get_next_color()
        new_wire = Wire(
            start=None,
            end=None,
            color=color,
            thickness=self.line_thickness,
            waypoints=waypoints if waypoints else [],
            is_free=True,
            start_pos=start_pos,
            end_pos=end_pos
        )
        
        self.wires.append(new_wire)
        return new_wire
    
    def update_wire_position(self, wire: Wire, start_pos: Tuple[int, int] = None, 
                            end_pos: Tuple[int, int] = None, waypoint_index: int = None, 
                            waypoint_pos: Tuple[int, int] = None):
        """
        更新线条的位置（用于拖动）
        
        Args:
            wire: 要更新的线条
            start_pos: 新的起点位置
            end_pos: 新的终点位置
            waypoint_index: 要更新的中间点索引
            waypoint_pos: 新的中间点位置
        """
        if not wire.is_free:
            return  # 非自由线条不能拖动
        
        self.save_state()
        
        if start_pos is not None:
            wire.start_pos = start_pos
        if end_pos is not None:
            wire.end_pos = end_pos
        if waypoint_index is not None and waypoint_pos is not None:
            if 0 <= waypoint_index < len(wire.waypoints):
                wire.waypoints[waypoint_index] = waypoint_pos
    
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
            new_wire.is_free = wire.is_free
            new_wire.start_pos = wire.start_pos
            new_wire.end_pos = wire.end_pos
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
    
    def clear_history(self):
        """清空历史记录（用于导入数据后）"""
        self.wire_history.clear()
    
    def draw_all_wires(self, image: np.ndarray) -> np.ndarray:
        """
        在图像上绘制所有连接线（优化版本）
        
        性能优化说明：
        这是性能优化的关键方法。只在开始时创建一次图像副本，
        然后循环调用每条线的 draw_on_image 方法直接在副本上绘制。
        消除了原来每条线都创建副本的链式拷贝问题。
        
        优化前：N 条线 = (1 + N) × 6MB 内存拷贝
        优化后：N 条线 = 1 × 6MB 内存拷贝
        
        对于 100 条线，内存拷贝量从 606MB 降低到 6MB，性能提升约 100 倍。
        
        Args:
            image: 输入图像
            
        Returns:
            带有所有连接线的新图像
        """
        result = image.copy()  # 只拷贝一次
        for wire in self.wires:
            wire.draw_on_image(result)  # 直接绘制，无拷贝
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
            if wire.is_free:
                # 自由线条
                connection = {
                    'is_free': True,
                    'start': {'x': wire.start_pos[0], 'y': wire.start_pos[1]},
                    'end': {'x': wire.end_pos[0], 'y': wire.end_pos[1]},
                    'color': list(wire.color),
                    'thickness': wire.thickness
                }
            else:
                # 普通连线
                connection = {
                    'is_free': False,
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
            color = tuple(conn.get('color', (0, 0, 255)))
            thickness = conn.get('thickness', 2)
            is_free = conn.get('is_free', False)
            
            if is_free:
                # 创建自由线条
                wire = Wire(
                    start=None,
                    end=None,
                    color=color,
                    thickness=thickness,
                    is_free=True,
                    start_pos=(start_x, start_y),
                    end_pos=(end_x, end_y)
                )
                
                # 如果有中间点，也导入
                if 'waypoints' in conn:
                    wire.waypoints = [(wp['x'], wp['y']) for wp in conn['waypoints']]
                    
                manager.wires.append(wire)
            else:
                # 创建普通连线（依赖孔）
                start_hole = hole_map.get((start_x, start_y))
                end_hole = hole_map.get((end_x, end_y))
                
                if start_hole and end_hole:
                    wire = Wire(start_hole, end_hole, color, thickness)
                    
                    # 如果有中间点，也导入
                    if 'waypoints' in conn:
                        wire.waypoints = [(wp['x'], wp['y']) for wp in conn['waypoints']]
                        
                    manager.wires.append(wire)
                
        return manager 