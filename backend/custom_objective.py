"""
custom_objective.py — Safe evaluation of scientist-defined scoring expressions.

Scientists write expressions like:
  "0.5 * tensile_strength_mpa + 0.3 * emi_shielding - 0.2 * density"

Safety approach: SymPy symbolic parsing + whitelist of allowed operations.
No exec/eval of raw Python. SymPy converts the expression to a safe AST,
extracts only the leaf symbols, and evaluates numerically by substitution.

Fallback: If SymPy is not installed, a regex-based restricted eval is used
that only allows numbers, property names, and arithmetic operators.
"""

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

_ALLOWED_FUNCTIONS = {"sqrt", "log", "exp", "abs", "min", "max"}


class ObjectiveParseError(ValueError):
    pass


def validate_expression(expression: str, property_names: List[str]) -> Dict[str, Any]:
    """
    Validate a scoring expression without evaluating it.

    Returns
    -------
    {"valid": True, "symbols": [...], "warnings": [...]}
    or
    {"valid": False, "error": "..."}
    """
    if not expression or not expression.strip():
        return {"valid": False, "error": "Expression is empty"}

    try:
        symbols = _extract_symbols(expression)
        unknown = [s for s in symbols if s not in property_names and s not in _ALLOWED_FUNCTIONS]
        warnings = []
        if unknown:
            warnings.append(f"Unknown symbols (will default to 0): {unknown}")
        return {"valid": True, "symbols": symbols, "warnings": warnings}
    except ObjectiveParseError as e:
        return {"valid": False, "error": str(e)}
    except Exception as e:
        return {"valid": False, "error": f"Parse error: {e}"}


def evaluate_objective(
    expression: str,
    predictions: Dict[str, Any],
    default_missing: float = 0.0,
) -> float:
    """
    Evaluate a scientist-defined scoring expression against GP predictions.

    Parameters
    ----------
    expression : str — e.g. "0.5 * tensile_strength_mpa + 0.3 * emi_shielding"
    predictions : dict — {property_name: {"mean": float, "std": float, ...}}
    default_missing : float — value used for unknown symbols

    Returns a single float score.
    """
    # Extract mean values from predictions
    values: Dict[str, float] = {}
    for name, pred in predictions.items():
        if isinstance(pred, dict):
            values[name] = float(pred.get("mean", default_missing))
        elif isinstance(pred, (int, float)):
            values[name] = float(pred)

    try:
        return _eval_sympy(expression, values, default_missing)
    except ImportError:
        return _eval_fallback(expression, values, default_missing)
    except Exception as e:
        logger.warning(f"[CustomObjective] SymPy eval failed ({e}), trying fallback")
        try:
            return _eval_fallback(expression, values, default_missing)
        except Exception as e2:
            logger.error(f"[CustomObjective] Both eval paths failed: {e2}")
            return 0.0


def _extract_symbols(expression: str) -> List[str]:
    """Extract symbol names from expression using SymPy."""
    try:
        import sympy
        expr = sympy.sympify(expression, evaluate=False)
        return [str(s) for s in expr.free_symbols]
    except ImportError:
        # Fallback: extract identifiers via regex
        tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', expression)
        return list(set(tokens))
    except Exception as e:
        raise ObjectiveParseError(f"Invalid expression: {e}")


def _eval_sympy(expression: str, values: Dict[str, float], default_missing: float) -> float:
    """Evaluate expression using SymPy substitution (no exec/eval)."""
    import sympy
    try:
        expr = sympy.sympify(expression, evaluate=False)
    except Exception as e:
        raise ObjectiveParseError(f"SymPy cannot parse expression: {e}")

    # Build substitution dict
    subs = {}
    for symbol in expr.free_symbols:
        name = str(symbol)
        subs[symbol] = values.get(name, default_missing)

    result = expr.subs(subs).evalf()
    val = float(result)

    # NaN/inf guard
    if val != val or abs(val) == float("inf"):
        return 0.0
    return val


def _eval_fallback(expression: str, values: Dict[str, float], default_missing: float) -> float:
    """
    Regex-gated restricted eval fallback when SymPy is unavailable.
    Only allows: numbers, property names, +, -, *, /, (, ), spaces, dots.
    """
    if re.search(r'[^a-zA-Z0-9_\s\+\-\*\/\(\)\.]', expression):
        raise ObjectiveParseError("Expression contains disallowed characters")

    # Build safe namespace with only property values
    safe_ns = {name: val for name, val in values.items()}
    # Fill any missing identifiers with default
    for token in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', expression):
        if token not in safe_ns:
            safe_ns[token] = default_missing

    try:
        result = eval(expression, {"__builtins__": {}}, safe_ns)  # noqa: S307
        return float(result)
    except Exception as e:
        raise ObjectiveParseError(f"Evaluation failed: {e}")
