from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QBrush, QPen, QFont, QPainter, QPainterPath
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QGraphicsScene, QGraphicsView, QGraphicsSimpleTextItem

from semantic_analyzer import (
    AssignNode,
    AstNode,
    CompareNode,
    IdentifierNode,
    IfNode,
    IntLiteralNode,
    LogicalBinaryNode,
    NotNode,
)


@dataclass
class _TreeNode:
    label: str
    children: List["_TreeNode"] = field(default_factory=list)


@dataclass
class _LayoutNode:
    node: _TreeNode
    width: float
    children: List["_LayoutNode"]


class _AstGraphicsView(QGraphicsView):
    """Graphics view with wheel and keyboard zoom support."""

    MIN_SCALE = 0.15
    MAX_SCALE = 6.0
    ZOOM_IN_FACTOR = 1.2
    ZOOM_OUT_FACTOR = 1.0 / ZOOM_IN_FACTOR

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self._apply_zoom(self.ZOOM_IN_FACTOR)
            elif event.angleDelta().y() < 0:
                self._apply_zoom(self.ZOOM_OUT_FACTOR)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self._apply_zoom(self.ZOOM_IN_FACTOR)
                event.accept()
                return
            if key == Qt.Key.Key_Minus:
                self._apply_zoom(self.ZOOM_OUT_FACTOR)
                event.accept()
                return
            if key == Qt.Key.Key_0:
                self.resetTransform()
                event.accept()
                return
        super().keyPressEvent(event)

    def _apply_zoom(self, factor: float):
        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < self.MIN_SCALE or new_scale > self.MAX_SCALE:
            return
        self.scale(factor, factor)


class AstGraphDialog(QDialog):
    NODE_MIN_WIDTH = 120.0
    NODE_HEIGHT = 36.0
    H_SPACING = 24.0
    V_SPACING = 56.0
    MARGIN = 40.0
    TEXT_PADDING_X = 16.0

    def __init__(self, ast_root: AstNode, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Дерево разбора")
        self.resize(1200, 760)

        layout = QVBoxLayout(self)
        self.scene = QGraphicsScene(self)
        self.view = _AstGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.setBackgroundBrush(QBrush(QColor("#1f1f1f")))
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.view.setToolTip(
            "Ctrl + колесо мыши: масштаб\n"
            "Ctrl + '+/-': увеличить/уменьшить\n"
            "Ctrl + 0: сбросить масштаб"
        )
        layout.addWidget(self.view)

        tree_root = self._build_ast_tree(ast_root)
        layout_root = self._build_layout(tree_root)
        self._draw_tree(layout_root, self.MARGIN, self.MARGIN)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _build_ast_tree(self, ast_root: AstNode) -> _TreeNode:
        if isinstance(ast_root, IfNode):
            children = [
                _TreeNode("Condition", [self._build_ast_tree(ast_root.condition)]),
                _TreeNode("Then", [self._build_ast_tree(ast_root.then_branch)]),
            ]
            if ast_root.else_branch is not None:
                children.append(_TreeNode("Else", [self._build_ast_tree(ast_root.else_branch)]))
            return _TreeNode("If", children)
        if isinstance(ast_root, AssignNode):
            return _TreeNode(
                "Assign",
                [
                    _TreeNode("Target", [self._build_ast_tree(ast_root.target)]),
                    _TreeNode("Value", [self._build_ast_tree(ast_root.value)]),
                ],
            )
        if isinstance(ast_root, CompareNode):
            return _TreeNode(
                f"Compare ({ast_root.operator})",
                [self._build_ast_tree(ast_root.left), self._build_ast_tree(ast_root.right)],
            )
        if isinstance(ast_root, LogicalBinaryNode):
            return _TreeNode(
                f"Logical ({ast_root.operator})",
                [self._build_ast_tree(ast_root.left), self._build_ast_tree(ast_root.right)],
            )
        if isinstance(ast_root, NotNode):
            return _TreeNode("Not", [self._build_ast_tree(ast_root.operand)])
        if isinstance(ast_root, IdentifierNode):
            return _TreeNode(f"Id: {ast_root.name}")
        if isinstance(ast_root, IntLiteralNode):
            return _TreeNode(f"Int: {ast_root.value}")
        return _TreeNode("Unknown")

    def _measure_node_width(self, label: str) -> float:
        tmp = QGraphicsSimpleTextItem(label)
        tmp.setFont(QFont("Consolas", 10))
        return max(self.NODE_MIN_WIDTH, tmp.boundingRect().width() + self.TEXT_PADDING_X * 2.0)

    def _build_layout(self, node: _TreeNode) -> _LayoutNode:
        child_layouts = [self._build_layout(ch) for ch in node.children]
        own_width = self._measure_node_width(node.label)
        if not child_layouts:
            return _LayoutNode(node=node, width=own_width, children=[])

        children_width = sum(ch.width for ch in child_layouts)
        children_width += self.H_SPACING * (len(child_layouts) - 1)
        width = max(own_width, children_width)
        return _LayoutNode(node=node, width=width, children=child_layouts)

    def _draw_tree(self, layout_node: _LayoutNode, x: float, y: float) -> Tuple[float, float]:
        center_x = x + layout_node.width / 2.0
        node_width = self._measure_node_width(layout_node.node.label)
        node_x = center_x - node_width / 2.0
        node_y = y

        node_rect = QRectF(node_x, node_y, node_width, self.NODE_HEIGHT)
        self._draw_node_box(node_rect, layout_node.node)

        if not layout_node.children:
            return center_x, node_y

        children_total_width = sum(ch.width for ch in layout_node.children)
        children_total_width += self.H_SPACING * (len(layout_node.children) - 1)
        child_cursor_x = center_x - children_total_width / 2.0

        for child in layout_node.children:
            child_center_x, child_top_y = self._draw_tree(
                child,
                child_cursor_x,
                node_y + self.NODE_HEIGHT + self.V_SPACING,
            )
            self.scene.addLine(
                center_x,
                node_y + self.NODE_HEIGHT,
                child_center_x,
                child_top_y,
                QPen(QColor("#7a8fb5"), 1.3),
            )
            child_cursor_x += child.width + self.H_SPACING

        return center_x, node_y

    def _draw_node_box(self, rect: QRectF, node: _TreeNode):
        fill_color, border_color = self._node_colors(node.label)
        rounded_rect_path = QPainterPath()
        rounded_rect_path.addRoundedRect(rect, 6.0, 6.0)
        self.scene.addPath(
            rounded_rect_path,
            QPen(border_color, 1.2),
            QBrush(fill_color),
        )

        title = QGraphicsSimpleTextItem(node.label)
        title.setBrush(QBrush(QColor("#f2f5ff")))
        title.setFont(QFont("Consolas", 10))
        title_rect = title.boundingRect()
        title.setPos(
            rect.left() + (rect.width() - title_rect.width()) / 2.0,
            rect.top() + (rect.height() - title_rect.height()) / 2.0,
        )
        self.scene.addItem(title)

    def _node_colors(self, label: str) -> Tuple[QColor, QColor]:
        if label in ("If", "Then", "Else", "Condition"):
            return QColor("#2b3552"), QColor("#8ea1cc")
        if label.startswith("Assign") or label in ("Target", "Value"):
            return QColor("#2f3a47"), QColor("#8fb2d9")
        if label.startswith("Compare") or label.startswith("Logical") or label == "Not":
            return QColor("#314053"), QColor("#9cc0f0")
        if label.startswith("Id:"):
            return QColor("#2f4b3f"), QColor("#7ac8a0")
        if label.startswith("Int:"):
            return QColor("#4d3d2f"), QColor("#d4b08a")
        return QColor("#2b2f38"), QColor("#8a93a5")
