import ast
import math
import operator
import time
from typing import Any
from pydantic import BaseModel, Field
from app.services.tools.base import BaseTool, ToolContext, ToolResult


class CalculatorInput(BaseModel):
    """Input payload for the safe calculator tool."""
    expression: str = Field(
        ...,
        description="Mathematical expression to evaluate (e.g. '25 * 4', '1500 / 12', '0.15 * 2400')",
        min_length=1,
        max_length=500,
    )


class CalculatorOutput(BaseModel):
    """Output payload for the safe calculator tool."""
    expression: str
    result: float | int


class SafeMathEvaluator(ast.NodeVisitor):
    """AST visitor that only allows safe mathematical operations and numbers."""

    ALLOWED_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    ALLOWED_FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sqrt": math.sqrt,
    }

    ALLOWED_CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
    }

    def evaluate(self, expr: str) -> float | int:
        # Pre-process percentage signs like '15%' -> '(15 / 100)'
        cleaned_expr = expr.strip()
        # Parse expression into AST mode='eval'
        try:
            tree = ast.parse(cleaned_expr, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid mathematical syntax: {e}")

        return self.visit(tree.body)

    def visit_BinOp(self, node: ast.BinOp) -> float | int:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)

        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported mathematical operator: {op_type.__name__}")

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero is undefined.")

        if op_type == ast.Pow:
            # Prevent memory explosion from huge exponents like 9999**9999
            if abs(right) > 100:
                raise ValueError("Exponent too large (maximum allowed power magnitude is 100).")
            if abs(left) > 100000 and right > 10:
                raise ValueError("Base value too large for exponentiation.")

        return self.ALLOWED_OPERATORS[op_type](left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float | int:
        operand = self.visit(node.operand)
        op_type = type(node.op)
        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return self.ALLOWED_OPERATORS[op_type](operand)

    def visit_Constant(self, node: ast.Constant) -> float | int:
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"Unsupported constant type in math expression: {type(node.value).__name__}")

    def visit_Name(self, node: ast.Name) -> float | int:
        if node.id in self.ALLOWED_CONSTANTS:
            return self.ALLOWED_CONSTANTS[node.id]
        raise ValueError(f"Disallowed variable or identifier: '{node.id}'")

    def visit_Call(self, node: ast.Call) -> float | int:
        # Only allow simple identifier calls from the whitelist (e.g. abs(-5), round(3.14))
        if not isinstance(node.func, ast.Name):
            raise ValueError("Direct function calls only. Attribute calls are strictly forbidden.")

        func_name = node.func.id
        if func_name not in self.ALLOWED_FUNCTIONS:
            raise ValueError(f"Disallowed function call: '{func_name}'")

        args = [self.visit(arg) for arg in node.args]
        return self.ALLOWED_FUNCTIONS[func_name](*args)

    def generic_visit(self, node: ast.AST):
        # Strictly reject any AST node not explicitly handled above
        raise ValueError(f"Disallowed code construct in expression: {type(node).__name__}")


class CalculatorTool(BaseTool):
    """Safely evaluates mathematical expressions using an AST whitelist."""

    name = "calculator"
    description = "Perform safe arithmetic calculations (e.g. addition, subtraction, multiplication, division, percentages, powers, abs, round)."
    input_schema = CalculatorInput
    output_schema = CalculatorOutput
    required_roles = ["VIEWER", "MEMBER", "MANAGER", "ADMIN", "OWNER"]

    async def execute(self, input_data: CalculatorInput, context: ToolContext) -> ToolResult:
        start_time = time.time()
        try:
            evaluator = SafeMathEvaluator()
            result = evaluator.evaluate(input_data.expression)

            # Round float to 6 decimal places if needed for neatness
            if isinstance(result, float) and abs(result - round(result)) < 1e-10:
                result = int(round(result))
            elif isinstance(result, float):
                result = round(result, 6)

            elapsed = (time.time() - start_time) * 1000.0
            return ToolResult(
                success=True,
                data={"expression": input_data.expression, "result": result},
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000.0
            return ToolResult(
                success=False,
                error=f"Calculation error: {str(e)}",
                execution_time_ms=elapsed,
            )
