import re
from typing import List, Tuple, Optional, Dict, Any


class Token:
    CODES = {
        'INTEGER': 1,
        'IDENTIFIER': 2,
        'KEYWORD': 14,
        'OPERATOR': 10,
        'DELIMITER': 11,
        'ERROR': 99
    }

    RU_TYPES = {
        'INTEGER': 'ЦЕЛОЕ_БЕЗ_ЗНАКА',
        'IDENTIFIER': 'ИДЕНТИФИКАТОР',
        'KEYWORD': 'КЛЮЧЕВОЕ_СЛОВО',
        'OPERATOR': 'ОПЕРАТОР',
        'DELIMITER': 'РАЗДЕЛИТЕЛЬ',
        'ERROR': 'ОШИБКА'
    }

    EN_TYPES = {
        'INTEGER': 'INTEGER',
        'IDENTIFIER': 'IDENTIFIER',
        'KEYWORD': 'KEYWORD',
        'OPERATOR': 'OPERATOR',
        'DELIMITER': 'DELIMITER',
        'ERROR': 'ERROR'
    }

    def __init__(
        self,
        token_type: str,
        value: str,
        line: int,
        start: int,
        end: int,
        error_message: str | None = None,
        raw_lexeme: str | None = None
    ):
        self.token_type = token_type
        self.value = value
        self.line = line
        self.start = start
        self.end = end
        self.code = self.CODES.get(token_type, 99)
        self.error_message = error_message
        self.raw_lexeme = raw_lexeme if raw_lexeme is not None else value

    def __repr__(self):
        return f"Token({self.token_type}, '{self.value}', line={self.line}, pos={self.start}-{self.end})"

    def get_display_type(self, lang='ru'):
        if lang == 'ru':
            return self.RU_TYPES.get(self.token_type, self.token_type)
        else:
            return self.EN_TYPES.get(self.token_type, self.token_type)

    def get_display_value(self, lang='ru'):
        if self.token_type == 'ERROR' and self.error_message:
            return self.error_message
        if self.value == '(пробел)' and lang == 'en':
            return '(space)'
        elif self.value == '\\n' and lang == 'en':
            return '\\n'
        elif self.value == '\\t' and lang == 'en':
            return '\\t'
        return self.value

    def to_table_row(self, lang='ru') -> tuple:
        if lang == 'ru':
            location = f"строка {self.line}, {self.start}-{self.end}"
        else:
            location = f"line {self.line}, {self.start}-{self.end}"
        return (self.code, self.get_display_type(lang), self.get_display_value(lang), location)


class Scanner:
    KEYWORDS = {
        'if', 'else', 'elif', 'True', 'False', 'None', 'and', 'or', 'not', 'int', 'float', 'str', 'print',
        'const', 'val', 'Int', 'String', 'Bool', 'Float'
    }

    OPERATORS = {'=', '>', '<', '>=', '<=', '==', '!=', '+', '-', '*', '/', '%', '//', '**', '+=', '-=', '*=', '/='}

    DELIMITERS = {' ', '\t', '\n', ':', ';', ',', '(', ')', '{', '}', '[', ']'}

    def __init__(self):
        self.tokens: List[Token] = []
        self.errors: List[Token] = []
        self.line = 1
        self.pos = 1
        self.text = ""
        self.current_char = ''
        self.index = 0

    def analyze(self, text: str) -> Dict[str, Any]:
        self.tokens = []
        self.errors = []
        self.line = 1
        self.pos = 1
        self.index = 0
        self.text = text

        if not text:
            return {'tokens': [], 'errors': []}

        while self.index < len(self.text):
            self.current_char = self.text[self.index]

            if self.current_char in (' ', '\t'):
                self._handle_whitespace()
            elif self.current_char == '\n':
                self._handle_newline()
            elif self.current_char.isdigit():
                self._handle_number()
            elif self.current_char.isalpha() or self.current_char == '_':
                self._handle_identifier_or_keyword()
            elif self.current_char in self._get_operator_chars():
                self._handle_operator()
            elif self.current_char in self._get_delimiter_chars():
                self._handle_delimiter()
            elif self.current_char == '#':
                self._handle_comment()
            else:
                self._handle_error(f"Недопустимый символ: '{self.current_char}'")

        return {
            'tokens': self.tokens,
            'errors': self.errors
        }

    def _get_operator_chars(self) -> set:
        chars = set()
        for op in self.OPERATORS:
            for ch in op:
                chars.add(ch)
        return chars

    def _get_delimiter_chars(self) -> set:
        return {d for d in self.DELIMITERS if d not in (' ', '\t', '\n')}

    def _handle_whitespace(self):
        start_pos = self.pos
        value = ''

        while self.index < len(self.text) and self.current_char in (' ', '\t'):
            value += self.current_char
            self._advance()

        if value == ' ':
            display_value = '(пробел)'
        elif value == '\t':
            display_value = '\\t'
        else:
            display_value = '(пробел)'

        token = Token('DELIMITER', display_value, self.line, start_pos, start_pos + len(value) - 1)
        self.tokens.append(token)

    def _handle_newline(self):
        token = Token('DELIMITER', '\\n', self.line, self.pos, self.pos)
        self.tokens.append(token)
        self.line += 1
        self.pos = 1
        self.index += 1
        if self.index < len(self.text):
            self.current_char = self.text[self.index]

    def _handle_number(self):
        start_pos = self.pos
        value = ''

        while self.index < len(self.text) and self.current_char.isdigit():
            value += self.current_char
            self._advance()

        if self.index < len(self.text) and (self.current_char.isalpha() or self.current_char == '_'):
            while self.index < len(self.text) and (self.current_char.isalnum() or self.current_char == '_'):
                value += self.current_char
                self._advance()
            self._add_error(f"Недопустимый идентификатор, начинающийся с цифры: '{value}'",
                           self.line, start_pos, start_pos + len(value) - 1)
        else:
            token = Token('INTEGER', value, self.line, start_pos, start_pos + len(value) - 1)
            self.tokens.append(token)

    def _handle_identifier_or_keyword(self):
        start_pos = self.pos
        value = ''

        while self.index < len(self.text) and (self.current_char.isalnum() or self.current_char == '_'):
            value += self.current_char
            self._advance()

        if value in self.KEYWORDS:
            token_type = 'KEYWORD'
        else:
            token_type = 'IDENTIFIER'

        token = Token(token_type, value, self.line, start_pos, start_pos + len(value) - 1)
        self.tokens.append(token)

    def _handle_operator(self):
        start_pos = self.pos
        value = ''

        while self.index < len(self.text):
            value += self.current_char
            self._advance()

            if value in self.OPERATORS:
                continue
            else:
                value = value[:-1]
                self.index -= 1
                if self.index >= 0:
                    self.current_char = self.text[self.index]
                break

        if not value and self.index < len(self.text):
            value = self.text[self.index]
            self._advance()

        if value in self.OPERATORS:
            token = Token('OPERATOR', value, self.line, start_pos, start_pos + len(value) - 1)
            self.tokens.append(token)
        else:
            self._add_error(f"Недопустимый оператор: '{value}'", self.line, start_pos, start_pos + len(value) - 1)

    def _handle_delimiter(self):
        token = Token('DELIMITER', self.current_char, self.line, self.pos, self.pos)
        self.tokens.append(token)
        self._advance()

    def _handle_comment(self):
        while self.index < len(self.text) and self.current_char != '\n':
            self._advance()

    def _handle_error(self, message: str):
        start_pos = self.pos
        bad_fragment = ''

        while self.index < len(self.text):
            ch = self.current_char
            if ch in (' ', '\t', '\n'):
                break
            if ch.isdigit() or ch.isalpha() or ch == '_':
                break
            if ch in self._get_operator_chars() or ch in self._get_delimiter_chars():
                break
            bad_fragment += ch
            self._advance()

        if not bad_fragment:
            bad_fragment = self.current_char
            self._advance()

        self._add_error(message, self.line, start_pos, start_pos + len(bad_fragment) - 1, bad_fragment)

    def _add_error(self, message: str, line: int, start: int, end: int, raw_lexeme: str | None = None):
        token = Token('ERROR', raw_lexeme or message, line, start, end, error_message=message, raw_lexeme=raw_lexeme)
        self.errors.append(token)
        self.tokens.append(token)

    def _advance(self):
        self.index += 1
        self.pos += 1
        if self.index < len(self.text):
            self.current_char = self.text[self.index]

    def get_token_table_data(self, lang='ru') -> List[tuple]:
        return [token.to_table_row(lang) for token in self.tokens]

    def get_errors_table_data(self, lang='ru') -> List[tuple]:
        return [token.to_table_row(lang) for token in self.errors]
    