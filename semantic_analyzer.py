from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from scanner import Token


INT_MIN = -2147483648
INT_MAX = 2147483647


@dataclass
class SemanticErrorRecord:
    fragment: str
    line: int
    col: int
    message: str

    def location_ru(self) -> str:
        return f"строка {self.line}, позиция {self.col}"

    def location_en(self) -> str:
        return f"line {self.line}, position {self.col}"


@dataclass
class SemanticAnalysisResult:
    ast_text: str
    ast_root: Optional["AstNode"] = None
    errors: List[SemanticErrorRecord] = field(default_factory=list)


@dataclass
class AstNode:
    def label(self) -> str:
        return self.__class__.__name__

    def children(self) -> List["AstNode"]:
        return []

    def attributes(self) -> List[str]:
        return []


@dataclass
class IdentifierNode(AstNode):
    name: str
    line: int
    col: int

    def attributes(self) -> List[str]:
        return [f'name: "{self.name}"']


@dataclass
class IntLiteralNode(AstNode):
    value: int
    line: int
    col: int

    def attributes(self) -> List[str]:
        return [f"value: {self.value}"]


@dataclass
class BoolLiteralNode(AstNode):
    value: bool
    line: int
    col: int

    def attributes(self) -> List[str]:
        return [f"value: {self.value}"]


@dataclass
class TypeNode(AstNode):
    name: str

    def label(self) -> str:
        return f"{self.name}Node"

    def attributes(self) -> List[str]:
        return [f'name: "{self.name}"']


@dataclass
class CompareNode(AstNode):
    operator: str
    left: AstNode
    right: AstNode

    def attributes(self) -> List[str]:
        return [f'operator: "{self.operator}"']

    def children(self) -> List[AstNode]:
        return [self.left, self.right]


@dataclass
class NotNode(AstNode):
    operand: AstNode

    def children(self) -> List[AstNode]:
        return [self.operand]


@dataclass
class LogicalBinaryNode(AstNode):
    operator: str
    left: AstNode
    right: AstNode

    def attributes(self) -> List[str]:
        return [f'operator: "{self.operator}"']

    def children(self) -> List[AstNode]:
        return [self.left, self.right]


@dataclass
class AssignNode(AstNode):
    target: IdentifierNode
    value: AstNode

    def children(self) -> List[AstNode]:
        return [self.target, self.value]


@dataclass
class IfNode(AstNode):
    condition: AstNode
    then_branch: AssignNode
    else_branch: Optional[AssignNode]

    def children(self) -> List[AstNode]:
        nodes = [self.condition, self.then_branch]
        if self.else_branch is not None:
            nodes.append(self.else_branch)
        return nodes


@dataclass
class ConstDeclNode(AstNode):
    name: str
    modifiers: List[str]
    type_node: TypeNode
    value: AstNode
    line: int
    col: int

    def attributes(self) -> List[str]:
        return [f'name: "{self.name}"', f"modifiers: {self.modifiers}"]

    def children(self) -> List[AstNode]:
        return [self.type_node, self.value]


@dataclass
class ProgramNode(AstNode):
    statements: List[AstNode]

    def children(self) -> List[AstNode]:
        return self.statements


@dataclass
class SymbolInfo:
    name: str
    type_name: str
    line: int
    col: int


class SymbolTable:
    def __init__(self):
        self.scopes: List[Dict[str, SymbolInfo]] = [dict()]

    def push_scope(self):
        self.scopes.append(dict())

    def pop_scope(self):
        if len(self.scopes) > 1:
            self.scopes.pop()

    def declare(self, symbol: SymbolInfo) -> bool:
        current = self.scopes[-1]
        if symbol.name in current:
            return False
        current[symbol.name] = symbol
        return True

    def lookup(self, name: str) -> Optional[SymbolInfo]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def lookup_current(self, name: str) -> Optional[SymbolInfo]:
        return self.scopes[-1].get(name)


class SemanticAnalyzer:
    REL_OPS = {">", "<", ">=", "<=", "==", "!="}
    SUPPORTED_TYPES = {"Int", "String", "Bool", "Float"}

    def __init__(self, tokens: List["Token"], lang: str = "ru"):
        self.tokens = self._filter_tokens(tokens)
        self.lang = lang if lang in ("ru", "en") else "ru"
        self.i = 0
        self.errors: List[SemanticErrorRecord] = []
        self.symbols = SymbolTable()
        self._reported_condition_nodes: set[int] = set()

    @staticmethod
    def _filter_tokens(tokens: List["Token"]) -> List["Token"]:
        filtered = []
        for tok in tokens:
            if tok.token_type == "DELIMITER" and tok.value in ("(пробел)", "\\t", "\\n"):
                continue
            filtered.append(tok)
        return filtered

    def _m(self, ru: str, en: str) -> str:
        return en if self.lang == "en" else ru

    def _current(self) -> Optional["Token"]:
        if self.i < len(self.tokens):
            return self.tokens[self.i]
        return None

    def _advance(self):
        self.i += 1

    def _match_keyword(self, value: str) -> bool:
        t = self._current()
        if t and t.token_type == "KEYWORD" and t.value == value:
            self._advance()
            return True
        return False

    def _match_word(self, value: str) -> bool:
        t = self._current()
        if t and t.value == value and t.token_type in ("KEYWORD", "IDENTIFIER"):
            self._advance()
            return True
        return False

    def _match_delimiter(self, value: str) -> bool:
        t = self._current()
        if t and t.token_type == "DELIMITER" and t.value == value:
            self._advance()
            return True
        return False

    def _add_error(self, t: Optional["Token"], message: str):
        self.errors.append(
            SemanticErrorRecord(
                fragment=t.raw_lexeme if t is not None else "EOF",
                line=t.line if t is not None else 1,
                col=t.start if t is not None else 1,
                message=message,
            )
        )

    def _expect_keyword(self, value: str) -> bool:
        if self._match_keyword(value):
            return True
        self._add_error(
            self._current(),
            self._m(f"Ожидалось ключевое слово '{value}'", f"Expected keyword '{value}'"),
        )
        return False

    def _expect_delimiter(self, value: str) -> bool:
        if self._match_delimiter(value):
            return True
        self._add_error(
            self._current(),
            self._m(f"Ожидался символ '{value}'", f"Expected '{value}'"),
        )
        return False

    def _parse_operand(self) -> Optional[AstNode]:
        t = self._current()
        if t is None:
            return None
        if t.token_type == "IDENTIFIER":
            self._advance()
            return IdentifierNode(name=t.value, line=t.line, col=t.start)
        if t.token_type == "INTEGER":
            self._advance()
            return IntLiteralNode(value=int(t.value), line=t.line, col=t.start)
        if t.token_type == "KEYWORD" and t.value in ("True", "False"):
            self._advance()
            return BoolLiteralNode(value=t.value == "True", line=t.line, col=t.start)
        self._add_error(
            t,
            self._m("Ожидался идентификатор или целое число", "Expected identifier or integer"),
        )
        self._advance()
        return None

    def _parse_compare(self) -> Optional[AstNode]:
        left = self._parse_operand()
        op = self._current()
        if op is None or op.token_type != "OPERATOR" or op.value not in self.REL_OPS:
            self._add_error(op, self._m("Ожидался оператор сравнения", "Expected comparison operator"))
            return left
        self._advance()
        right = self._parse_operand()
        if left is None or right is None:
            return left
        return CompareNode(operator=op.value, left=left, right=right)

    def _parse_primary_cond(self) -> Optional[AstNode]:
        if self._match_delimiter("("):
            node = self._parse_cond()
            self._expect_delimiter(")")
            return node
        return self._parse_compare()

    def _parse_logical_factor(self) -> Optional[AstNode]:
        if self._match_keyword("not"):
            operand = self._parse_primary_cond()
            return NotNode(operand=operand) if operand else None
        return self._parse_primary_cond()

    def _parse_logical_term(self) -> Optional[AstNode]:
        node = self._parse_logical_factor()
        while self._match_keyword("and"):
            right = self._parse_logical_factor()
            if node is None or right is None:
                continue
            node = LogicalBinaryNode(operator="and", left=node, right=right)
        return node

    def _parse_cond(self) -> Optional[AstNode]:
        node = self._parse_logical_term()
        while self._match_keyword("or"):
            right = self._parse_logical_term()
            if node is None or right is None:
                continue
            node = LogicalBinaryNode(operator="or", left=node, right=right)
        return node

    def _parse_assign(self) -> Optional[AssignNode]:
        left = self._current()
        if left is None or left.token_type != "IDENTIFIER":
            self._add_error(left, self._m("Ожидался идентификатор слева от '='", "Expected identifier before '='"))
            return None
        self._advance()
        self._expect_operator("=")
        right = self._parse_operand()
        self._expect_delimiter(";")
        if right is None:
            return None
        return AssignNode(target=IdentifierNode(name=left.value, line=left.line, col=left.start), value=right)

    def _expect_operator(self, value: str) -> bool:
        t = self._current()
        if t and t.token_type == "OPERATOR" and t.value == value:
            self._advance()
            return True
        self._add_error(t, self._m(f"Ожидался оператор '{value}'", f"Expected operator '{value}'"))
        return False

    def _parse_start(self) -> Optional[IfNode]:
        self._expect_keyword("if")
        cond = self._parse_cond()
        if cond is not None:
            self._infer_condition_type(cond)
        self._expect_delimiter(":")

        self.symbols.push_scope()
        then_assign = self._parse_assign()
        self._check_assignment_semantics(then_assign)
        self.symbols.pop_scope()

        else_assign: Optional[AssignNode] = None
        if self._match_keyword("else"):
            self._expect_delimiter(":")
            self.symbols.push_scope()
            else_assign = self._parse_assign()
            self._check_assignment_semantics(else_assign)
            self.symbols.pop_scope()
        else:
            self._add_error(self._current(), self._m("Ожидался блок else", "Expected else block"))

        self._expect_delimiter(";")
        return IfNode(
            condition=cond if cond else IdentifierNode("ERROR", 1, 1),
            then_branch=then_assign if then_assign else AssignNode(IdentifierNode("ERROR", 1, 1), IdentifierNode("ERROR", 1, 1)),
            else_branch=else_assign,
        )

    def _normalize_type_name(self, type_name: str) -> str:
        lowered = type_name.lower()
        if lowered in ("int", "int32"):
            return "Int"
        if lowered == "string":
            return "String"
        if lowered in ("bool", "boolean"):
            return "Bool"
        if lowered in ("float", "double"):
            return "Float"
        return type_name

    def _parse_type_name(self) -> Optional[TypeNode]:
        t = self._current()
        if t is None or t.token_type not in ("IDENTIFIER", "KEYWORD"):
            self._add_error(t, self._m("Ожидалось имя типа", "Expected type name"))
            return None
        self._advance()
        normalized = self._normalize_type_name(t.value)
        if normalized not in self.SUPPORTED_TYPES:
            self.errors.append(
                SemanticErrorRecord(
                    fragment=t.value,
                    line=t.line,
                    col=t.start,
                    message=self._m(
                        f'Неподдерживаемый тип "{t.value}"',
                        f'Unsupported type "{t.value}"',
                    ),
                )
            )
        return TypeNode(name=normalized)

    def _parse_const_decl(self) -> Optional[ConstDeclNode]:
        start = self._current()
        has_const = self._match_word("const")
        has_val = self._match_word("val")
        if not has_const:
            self._add_error(start, self._m("Ожидалось ключевое слово 'const'", "Expected keyword 'const'"))
        if not has_val:
            self._add_error(self._current(), self._m("Ожидалось ключевое слово 'val'", "Expected keyword 'val'"))

        name_tok = self._current()
        if name_tok is None or name_tok.token_type != "IDENTIFIER":
            self._add_error(name_tok, self._m("Ожидалось имя идентификатора", "Expected identifier name"))
            return None
        self._advance()

        self._expect_delimiter(":")
        type_node = self._parse_type_name()
        self._expect_operator("=")
        value_node = self._parse_operand()
        self._expect_delimiter(";")

        if type_node is None or value_node is None:
            return None
        return ConstDeclNode(
            name=name_tok.value,
            modifiers=["const", "val"],
            type_node=type_node,
            value=value_node,
            line=name_tok.line,
            col=name_tok.start,
        )

    def _parse_const_program(self) -> ProgramNode:
        statements: List[AstNode] = []
        while self._current() is not None:
            decl = self._parse_const_decl()
            if decl is None:
                break
            if self._check_const_decl_semantics(decl):
                statements.append(decl)
        return ProgramNode(statements=statements)

    def _check_const_decl_semantics(self, decl: ConstDeclNode) -> bool:
        current = self.symbols.lookup_current(decl.name)
        if current is not None:
            self.errors.append(
                SemanticErrorRecord(
                    fragment=decl.name,
                    line=decl.line,
                    col=decl.col,
                    message=self._m(
                        f'Идентификатор "{decl.name}" уже объявлен ранее (строка {current.line})',
                        f'Identifier "{decl.name}" is already declared earlier (line {current.line})',
                    ),
                )
            )
            return False

        declared_type = decl.type_node.name
        value_type = self._infer_expr_type(decl.value)
        if value_type != "Unknown" and declared_type != value_type:
            self.errors.append(
                SemanticErrorRecord(
                    fragment=decl.name,
                    line=decl.line,
                    col=decl.col,
                    message=self._m(
                        f'Несовместимость типов: "{decl.name}" имеет тип {declared_type}, получено {value_type}',
                        f'Type mismatch: "{decl.name}" is {declared_type}, got {value_type}',
                    ),
                )
            )

        self.symbols.declare(SymbolInfo(name=decl.name, type_name=declared_type, line=decl.line, col=decl.col))
        return True

    def _infer_expr_type(self, node: AstNode) -> str:
        if isinstance(node, IntLiteralNode):
            if node.value < INT_MIN or node.value > INT_MAX:
                self.errors.append(
                    SemanticErrorRecord(
                        fragment=str(node.value),
                        line=node.line,
                        col=node.col,
                        message=self._m(
                            f"Значение {node.value} выходит за диапазон Int32 [{INT_MIN}; {INT_MAX}]",
                            f"Value {node.value} is out of Int32 range [{INT_MIN}; {INT_MAX}]",
                        ),
                    )
                )
            return "Int"
        if isinstance(node, BoolLiteralNode):
            return "Bool"
        if isinstance(node, IdentifierNode):
            symbol = self.symbols.lookup(node.name)
            if symbol is None:
                self.errors.append(
                    SemanticErrorRecord(
                        fragment=node.name,
                        line=node.line,
                        col=node.col,
                        message=self._m(
                            f'Идентификатор "{node.name}" используется до объявления',
                            f'Identifier "{node.name}" is used before declaration',
                        ),
                    )
                )
                return "Unknown"
            return symbol.type_name
        return "Unknown"

    def _infer_condition_type(self, node: AstNode) -> str:
        if isinstance(node, CompareNode):
            left_type = self._infer_expr_type(node.left)
            right_type = self._infer_expr_type(node.right)
            if left_type == "Unknown" or right_type == "Unknown":
                return "Unknown"
            if left_type != "Int" or right_type != "Int":
                self.errors.append(
                    SemanticErrorRecord(
                        fragment=node.operator,
                        line=self._node_line(node.left),
                        col=self._node_col(node.left),
                        message=self._m(
                            f'Оператор "{node.operator}" применим только к целым значениям',
                            f'Operator "{node.operator}" expects integer operands',
                        ),
                    )
                )
                return "Unknown"
            return "Bool"

        if isinstance(node, LogicalBinaryNode):
            left_type = self._infer_condition_type(node.left)
            right_type = self._infer_condition_type(node.right)
            if left_type not in ("Bool", "Unknown"):
                self._add_condition_type_error(node.left, node.operator)
            if right_type not in ("Bool", "Unknown"):
                self._add_condition_type_error(node.right, node.operator)
            if left_type == "Bool" and right_type == "Bool":
                return "Bool"
            return "Unknown"

        if isinstance(node, NotNode):
            operand_type = self._infer_condition_type(node.operand)
            if operand_type not in ("Bool", "Unknown"):
                self._add_condition_type_error(node.operand, "not")
            if operand_type == "Bool":
                return "Bool"
            return "Unknown"

        inferred = self._infer_expr_type(node)
        if inferred != "Unknown":
            self.errors.append(
                SemanticErrorRecord(
                    fragment=self._node_fragment(node),
                    line=self._node_line(node),
                    col=self._node_col(node),
                    message=self._m(
                        "Условие должно быть логическим выражением",
                        "Condition must be a boolean expression",
                    ),
                )
            )
        return "Unknown"

    def _node_line(self, node: AstNode) -> int:
        return getattr(node, "line", 1)

    def _node_col(self, node: AstNode) -> int:
        return getattr(node, "col", 1)

    def _node_fragment(self, node: AstNode) -> str:
        if isinstance(node, IdentifierNode):
            return node.name
        if isinstance(node, IntLiteralNode):
            return str(node.value)
        return node.label()

    def _add_condition_type_error(self, node: AstNode, operator: str):
        node_id = id(node)
        if node_id in self._reported_condition_nodes:
            return
        self._reported_condition_nodes.add(node_id)
        self.errors.append(
            SemanticErrorRecord(
                fragment=self._node_fragment(node),
                line=self._node_line(node),
                col=self._node_col(node),
                message=self._m(
                    f'Оператор "{operator}" требует логический операнд',
                    f'Operator "{operator}" expects boolean operand',
                ),
            )
        )

    def _check_assignment_semantics(self, assign: Optional[AssignNode]):
        if assign is None:
            return
        previous = self.symbols.lookup(assign.target.name)
        rhs_type = self._infer_expr_type(assign.value)
        if previous is not None and rhs_type == "Unknown":
            rhs_type = previous.type_name
        symbol = SymbolInfo(name=assign.target.name, type_name=rhs_type, line=assign.target.line, col=assign.target.col)
        if not self.symbols.declare(symbol):
            self.errors.append(
                SemanticErrorRecord(
                    fragment=assign.target.name,
                    line=assign.target.line,
                    col=assign.target.col,
                    message=self._m(
                        f'Идентификатор "{assign.target.name}" уже объявлен в текущей области видимости',
                        f'Identifier "{assign.target.name}" is already declared in current scope',
                    ),
                )
            )
            return
        if previous is not None and previous.type_name != rhs_type and rhs_type != "Unknown":
            self.errors.append(
                SemanticErrorRecord(
                    fragment=assign.target.name,
                    line=assign.target.line,
                    col=assign.target.col,
                    message=self._m(
                        f'Несовместимость типов: "{assign.target.name}" имеет тип {previous.type_name}, получено {rhs_type}',
                        f'Type mismatch: "{assign.target.name}" is {previous.type_name}, got {rhs_type}',
                    ),
                )
            )

    def analyze(self) -> SemanticAnalysisResult:
        self.i = 0
        self.errors = []
        self.symbols = SymbolTable()
        self._reported_condition_nodes.clear()
        ast: Optional[AstNode]
        first = self._current()
        if first and first.value in ("const", "val"):
            ast = self._parse_const_program()
        else:
            ast = self._parse_start()
        ast_text = render_tree(ast) if ast is not None else "AST: <empty>"
        return SemanticAnalysisResult(ast_text=ast_text, ast_root=ast, errors=self.errors)


def render_tree(node: Optional[AstNode]) -> str:
    if node is None:
        return "AST: <empty>"

    lines: List[str] = [node.label()]

    def _walk(current: AstNode, prefix: str):
        entries: List[Union[str, AstNode]] = current.attributes() + current.children()
        for idx, item in enumerate(entries):
            is_last = idx == len(entries) - 1
            branch = "└── " if is_last else "├── "
            next_prefix = f"{prefix}{'    ' if is_last else '│   '}"
            if isinstance(item, str):
                lines.append(f"{prefix}{branch}{item}")
            else:
                lines.append(f"{prefix}{branch}{item.label()}")
                _walk(item, next_prefix)

    _walk(node, "")
    return "\n".join(lines)
