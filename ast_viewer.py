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
    NODE_WIDTH = 250.0
    NODE_HEIGHT = 70.0
    H_SPACING = 40.0
    V_SPACING = 100.0
    MARGIN = 40.0

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

        tree_root = self._build_parse_tree(ast_root)
        layout_root = self._build_layout(tree_root)
        self._draw_tree(layout_root, self.MARGIN, self.MARGIN)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _build_parse_tree(self, ast_root: AstNode) -> _TreeNode:
        if not isinstance(ast_root, IfNode):
            return _TreeNode("<START>", [_TreeNode("<UNSUPPORTED_AST>")])

        return _TreeNode(
            "<START>",
            [
                _TreeNode("'if'"),
                self._build_cond(ast_root.condition),
                _TreeNode("':'"),
                self._build_assignment_block("<THEN>", ast_root.then_branch),
                self._build_else_opt(ast_root.else_branch),
                _TreeNode("';'"),
            ],
        )

    def _build_else_opt(self, else_branch: AssignNode | None) -> _TreeNode:
        if else_branch is None:
            return _TreeNode("<ELSE_OPT> → eps")
        return _TreeNode(
            "<ELSE_OPT>",
            [
                _TreeNode("'else:'"),
                self._build_assignment_block("<ASSIGN>", else_branch),
            ],
        )

    def _build_assignment_block(self, label: str, assign: AssignNode) -> _TreeNode:
        return _TreeNode(
            label,
            [
                self._operand_label(assign.target),
                _TreeNode("="),
                self._operand_label(assign.value),
                _TreeNode("';'"),
            ],
        )

    def _build_cond(self, node: AstNode) -> _TreeNode:
        terms = self._flatten_binary(node, "or")
        return _TreeNode(
            "<COND>",
            [
                self._build_logical_term(terms[0]),
                self._build_or_tail(terms[1:]),
            ],
        )

    def _build_or_tail(self, rest_terms: List[AstNode]) -> _TreeNode:
        if not rest_terms:
            return _TreeNode("<LOGICAL_EXPR_TAIL> → eps")
        return _TreeNode(
            "<LOGICAL_EXPR_TAIL>",
            [
                _TreeNode("'or'"),
                self._build_logical_term(rest_terms[0]),
                self._build_or_tail(rest_terms[1:]),
            ],
        )

    def _build_logical_term(self, node: AstNode) -> _TreeNode:
        factors = self._flatten_binary(node, "and")
        return _TreeNode(
            "<LOGICAL_TERM>",
            [
                self._build_logical_factor(factors[0]),
                self._build_and_tail(factors[1:]),
            ],
        )

    def _build_and_tail(self, rest_factors: List[AstNode]) -> _TreeNode:
        if not rest_factors:
            return _TreeNode("<LOGICAL_TERM_TAIL> → eps")
        return _TreeNode(
            "<LOGICAL_TERM_TAIL>",
            [
                _TreeNode("'and'"),
                self._build_logical_factor(rest_factors[0]),
                self._build_and_tail(rest_factors[1:]),
            ],
        )

    def _build_logical_factor(self, node: AstNode) -> _TreeNode:
        if isinstance(node, NotNode):
            return _TreeNode(
                "<LOGICAL_FACTOR>",
                [
                    _TreeNode("'not'"),
                    self._build_primary_cond(node.operand),
                ],
            )
        return _TreeNode("<LOGICAL_FACTOR>", [self._build_primary_cond(node)])

    def _build_primary_cond(self, node: AstNode) -> _TreeNode:
        return _TreeNode("<PRIMARY_COND>", [self._build_compare(node)])

    def _build_compare(self, node: AstNode) -> _TreeNode:
        if isinstance(node, CompareNode):
            return _TreeNode(
                "<COMPARE>",
                [
                    self._operand_label(node.left),
                    _TreeNode(f"<OPERATOR> → {node.operator}"),
                    self._operand_label(node.right),
                ],
            )
        return _TreeNode("<COMPARE>", [self._operand_label(node)])

    def _operand_label(self, node: AstNode) -> _TreeNode:
        if isinstance(node, IdentifierNode):
            return _TreeNode(f"<VAR> → {node.name}")
        if isinstance(node, IntLiteralNode):
            return _TreeNode(f"<VAR> → {node.value}")
        if isinstance(node, CompareNode):
            return self._build_compare(node)
        if isinstance(node, NotNode):
            return self._build_logical_factor(node)
        if isinstance(node, LogicalBinaryNode):
            return self._build_cond(node)
        return _TreeNode("<UNKNOWN>")

    def _flatten_binary(self, node: AstNode, op: str) -> List[AstNode]:
        if isinstance(node, LogicalBinaryNode) and node.operator == op:
            return self._flatten_binary(node.left, op) + [node.right]
        return [node]

    def _build_layout(self, node: _TreeNode) -> _LayoutNode:
        child_layouts = [self._build_layout(ch) for ch in node.children]
        if not child_layouts:
            return _LayoutNode(node=node, width=self.NODE_WIDTH, children=[])

        children_width = sum(ch.width for ch in child_layouts)
        children_width += self.H_SPACING * (len(child_layouts) - 1)
        width = max(self.NODE_WIDTH, children_width)
        return _LayoutNode(node=node, width=width, children=child_layouts)

    def _draw_tree(self, layout_node: _LayoutNode, x: float, y: float) -> Tuple[float, float]:
        center_x = x + layout_node.width / 2.0
        node_x = center_x - self.NODE_WIDTH / 2.0
        node_y = y

        node_rect = QRectF(node_x, node_y, self.NODE_WIDTH, self.NODE_HEIGHT)
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
                QPen(QColor("#91d7ff"), 1.7),
            )
            child_cursor_x += child.width + self.H_SPACING

        return center_x, node_y

    def _draw_node_box(self, rect: QRectF, node: _TreeNode):
        fill_color, border_color = self._node_colors(node.label)
        rounded_rect_path = QPainterPath()
        rounded_rect_path.addRoundedRect(rect, 8.0, 8.0)
        self.scene.addPath(
            rounded_rect_path,
            QPen(border_color, 1.6),
            QBrush(fill_color),
        )

        title = QGraphicsSimpleTextItem(node.label)
        title.setBrush(QBrush(QColor("#f7f7f7")))
        title.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        title_rect = title.boundingRect()
        title.setPos(
            rect.left() + (rect.width() - title_rect.width()) / 2.0,
            rect.top() + (rect.height() - title_rect.height()) / 2.0,
        )
        self.scene.addItem(title)

    def _node_colors(self, label: str) -> Tuple[QColor, QColor]:
        if label.startswith("<START>") or label == "'if'" or label == "':'" or label == "';'":
            return QColor("#2a2f56"), QColor("#8ea1ff")
        if label.startswith("<COND>") or label.startswith("<LOGICAL_") or label.startswith("<PRIMARY_") or label.startswith("<COMPARE>"):
            return QColor("#24456b"), QColor("#76c5ff")
        if label.startswith("<THEN>") or label.startswith("<ELSE_OPT>") or label.startswith("<ASSIGN>") or label == "=" or label == "'else:'":
            return QColor("#3a345f"), QColor("#a68bff")
        if label.startswith("<VAR>") or label.startswith("<OPERATOR>"):
            return QColor("#2f4b3f"), QColor("#74d8a4")
        if "eps" in label:
            return QColor("#5a3a27"), QColor("#ffb86b")
        return QColor("#2d314a"), QColor("#7aa2ff")
