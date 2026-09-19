import re
from typing import Any, Dict, Optional, Union
from app.services.workflow.exceptions import InvalidConditionError


# Safe operators mapping
ALLOWED_OPERATORS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "not in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a if hasattr(a, "__contains__") else False,
    "is_null": lambda a, b: a is None,
    "is_not_null": lambda a, b: a is not None,
    "is_true": lambda a, b: bool(a) is True,
    "is_false": lambda a, b: bool(a) is False,
}

# Regex to safely parse string conditions like: "stats.document_count > 10" or "result == 'success'"
EXPR_PATTERN = re.compile(
    r"^\s*([a-zA-Z0-9_\.]+)\s*(==|!=|>=|<=|>|<|in|not\s+in|contains)\s*(.+?)\s*$"
)


class SafeConditionEvaluator:
    """Safe, non-eval condition evaluator for workflow branching."""

    @classmethod
    def get_field_value(cls, context_data: Dict[str, Any], field_path: str) -> Any:
        """Safely navigate nested dictionary paths like 'stats.document_count'."""
        if not field_path:
            return None

        # Strip optional leading '$.' or 'context.'
        if field_path.startswith("$."):
            field_path = field_path[2:]
        elif field_path.startswith("context."):
            field_path = field_path[8:]

        parts = field_path.split(".")
        current = context_data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
            if current is None:
                return None

        return current

    @classmethod
    def parse_literal_value(cls, val_str: str) -> Any:
        """Parse literal strings, numbers, booleans, and nulls without eval()."""
        val_str = val_str.strip()
        if val_str.lower() in ("null", "none"):
            return None
        if val_str.lower() == "true":
            return True
        if val_str.lower() == "false":
            return False

        # Quoted strings
        if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
            return val_str[1:-1]

        # Numeric (int or float)
        try:
            if "." in val_str:
                return float(val_str)
            return int(val_str)
        except ValueError:
            pass

        # Return as plain string literal
        return val_str

    @classmethod
    def evaluate(cls, condition: Union[Dict[str, Any], str, None], context_data: Dict[str, Any]) -> bool:
        """Evaluate a safe condition against workflow context data.
        
        Returns True if condition is satisfied or condition is None.
        Raises InvalidConditionError on malicious or unparseable expressions.
        """
        if condition is None:
            return True

        # Forbid dangerous keywords and builtins
        forbidden = [
            "eval", "exec", "import", "__", "lambda", "class", "def",
            "globals", "locals", "os.", "sys.", "subprocess", "open", "read"
        ]
        cond_str = str(condition)
        for bad in forbidden:
            if bad in cond_str:
                raise InvalidConditionError(f"Unsafe keyword '{bad}' detected in condition expression.")

        # Case 1: Structured Dictionary format
        if isinstance(condition, dict):
            # Compound AND
            if "all" in condition:
                items = condition.get("all")
                if not isinstance(items, list):
                    raise InvalidConditionError("'all' condition must be a list.")
                return all(cls.evaluate(item, context_data) for item in items)

            # Compound OR
            if "any" in condition:
                items = condition.get("any")
                if not isinstance(items, list):
                    raise InvalidConditionError("'any' condition must be a list.")
                return any(cls.evaluate(item, context_data) for item in items)

            # Single comparison
            field = condition.get("field")
            operator = condition.get("operator")
            target_value = condition.get("value")

            if not field or not operator:
                raise InvalidConditionError("Condition must specify 'field' and 'operator'.")

            operator = operator.strip().lower() if operator in ("in", "not in") else operator.strip()
            op_func = ALLOWED_OPERATORS.get(operator)
            if not op_func:
                raise InvalidConditionError(
                    f"Unsupported operator '{operator}'. Allowed: {list(ALLOWED_OPERATORS.keys())}"
                )

            actual_value = cls.get_field_value(context_data, field)

            try:
                # Type coercion if comparing numbers
                if isinstance(target_value, (int, float)) and isinstance(actual_value, (int, float, str)):
                    if isinstance(actual_value, str):
                        try:
                            actual_value = float(actual_value) if "." in actual_value else int(actual_value)
                        except ValueError:
                            pass
                return bool(op_func(actual_value, target_value))
            except Exception as e:
                # Any evaluation error (e.g. comparing incompatible types) evaluates to False
                return False

        # Case 2: String expression format
        elif isinstance(condition, str):
            condition = condition.strip()
            match = EXPR_PATTERN.match(condition)
            if not match:
                raise InvalidConditionError(
                    f"Invalid condition expression format: '{condition}'. Expected 'field op value'."
                )

            field_path, operator, val_raw = match.groups()
            operator = operator.strip()
            op_func = ALLOWED_OPERATORS.get(operator)
            if not op_func:
                raise InvalidConditionError(f"Unsupported operator '{operator}'.")

            actual_value = cls.get_field_value(context_data, field_path)
            target_value = cls.parse_literal_value(val_raw)

            try:
                if isinstance(target_value, (int, float)) and isinstance(actual_value, (int, float, str)):
                    if isinstance(actual_value, str):
                        try:
                            actual_value = float(actual_value) if "." in actual_value else int(actual_value)
                        except ValueError:
                            pass
                return bool(op_func(actual_value, target_value))
            except Exception:
                return False

        raise InvalidConditionError(f"Unsupported condition type: {type(condition)}")
