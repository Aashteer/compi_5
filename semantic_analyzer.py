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


class SemanticAnalyzer:
    REL_OPS = {">", "<", ">=", "<=", "==", "!="}

    def __init__(self, tokens: List["Token"], lang: str = "ru"):
        self.tokens = self._filter_tokens(tokens)
        self.lang = lang if lang in ("ru", "en") else "ru"
        self.i = 0
        self.errors: List[SemanticErrorRecord] = []
        self.symbols = SymbolTable()

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
            self._register_condition_identifiers(cond)
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

    def _check_assignment_semantics(self, assign: Optional[AssignNode]):
        if assign is None:
            return
        previous = self.symbols.lookup(assign.target.name)
        rhs_type = self._infer_expr_type(assign.value)
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

    def _register_condition_identifiers(self, node: AstNode):
        if isinstance(node, CompareNode):
            self._declare_if_identifier(node.left)
            self._declare_if_identifier(node.right)
            return
        if isinstance(node, LogicalBinaryNode):
            self._register_condition_identifiers(node.left)
            self._register_condition_identifiers(node.right)
            return
        if isinstance(node, NotNode):
            self._register_condition_identifiers(node.operand)

    def _declare_if_identifier(self, node: AstNode):
        if not isinstance(node, IdentifierNode):
            return
        if self.symbols.lookup(node.name) is None:
            self.symbols.declare(SymbolInfo(name=node.name, type_name="Int", line=node.line, col=node.col))

    def analyze(self) -> SemanticAnalysisResult:
        self.i = 0
        self.errors = []
        ast = self._parse_start()
        ast_text = render_tree(ast) if ast is not None else "AST: <empty>"
        return SemanticAnalysisResult(ast_text=ast_text, ast_root=ast, errors=self.errors)


def render_tree(node: Optional[AstNode], prefix: str = "", is_last: bool = True) -> str:
    if node is None:
        return "AST: <empty>"

    lines: List[str] = []
    branch = "└── " if is_last else "├── "
    if prefix:
        lines.append(f"{prefix}{branch}{node.label()}")
    else:
        lines.append(node.label())

    attrs = node.attributes()
    children = node.children()

    child_entries: List[Union[str, AstNode]] = attrs + children
    for idx, item in enumerate(child_entries):
        last_child = idx == len(child_entries) - 1
        child_prefix = f"{prefix}{'    ' if is_last else '│   '}" if prefix else ""
        if isinstance(item, str):
            symbol = "└── " if last_child else "├── "
            lines.append(f"{child_prefix}{symbol}{item}")
        else:
            nested = render_tree(item, child_prefix, last_child)
            lines.append(nested)
    return "\n".join(lines)
