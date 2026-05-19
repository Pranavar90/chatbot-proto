"""
sim_hook.py — Subprocess-based hook for scientist-provided simulation scripts.

Interface contract for the scientist's script:
  - Called as: python /path/to/script.py '{"param1": 1.5, "param2": 0.3}'
  - Must print a single JSON line to stdout:
    {"property_name": 82.3, "another_property": 145.0}
  - Non-zero exit code → failure; stderr is captured as error message
  - Timeout: configurable, default 60 seconds

The hook is OPTIONAL and ADDITIVE: if a script returns values for some
properties, those REPLACE the GP predictions for those properties only.
GP std is retained as the uncertainty estimate around the hook value.
Properties the script does NOT return are served by the GP as normal.

Security:
  - The subprocess runs using sys.executable (same Python env)
  - No network access is restricted (the script runs with user's permissions)
  - Script path must be an absolute path on the local filesystem
  - stdout is parsed as JSON; anything else is an error
"""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

HOOK_TIMEOUT_DEFAULT = 60  # seconds


def call_simulation_hook(
    script_path: str,
    composition: Dict[str, float],
    timeout: int = HOOK_TIMEOUT_DEFAULT,
) -> Dict[str, Any]:
    """
    Call a scientist-provided simulation script with a composition dict.

    Parameters
    ----------
    script_path : str — absolute path to the Python script
    composition : dict — {param_name: value} in original units
    timeout : int — seconds before process is killed

    Returns
    -------
    {
      "success": bool,
      "predictions": {property_name: float},
      "stderr": str,
      "runtime_s": float,
    }
    """
    path = Path(script_path)

    if not path.exists():
        return {
            "success": False,
            "predictions": {},
            "stderr": f"Script not found: {script_path}",
            "runtime_s": 0.0,
        }

    if not path.is_file():
        return {
            "success": False,
            "predictions": {},
            "stderr": f"Path is not a file: {script_path}",
            "runtime_s": 0.0,
        }

    t0 = time.monotonic()

    try:
        result = subprocess.run(
            [sys.executable, str(path), json.dumps(composition)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.monotonic() - t0

        if result.returncode != 0:
            logger.warning(
                f"[SimHook] Script exited {result.returncode}: {result.stderr[:300]}"
            )
            return {
                "success": False,
                "predictions": {},
                "stderr": result.stderr[:1000],
                "runtime_s": round(elapsed, 3),
            }

        stdout = result.stdout.strip()
        if not stdout:
            return {
                "success": False,
                "predictions": {},
                "stderr": "Script produced no output",
                "runtime_s": round(elapsed, 3),
            }

        # Use the last non-empty line (scripts may print debug output)
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        last_line = lines[-1]

        try:
            parsed = json.loads(last_line)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "predictions": {},
                "stderr": f"Cannot parse script output as JSON: {e}\nOutput: {last_line[:200]}",
                "runtime_s": round(elapsed, 3),
            }

        if not isinstance(parsed, dict):
            return {
                "success": False,
                "predictions": {},
                "stderr": "Script output must be a JSON object (dict), got: " + type(parsed).__name__,
                "runtime_s": round(elapsed, 3),
            }

        # Keep only numeric values
        predictions = {
            k: float(v)
            for k, v in parsed.items()
            if isinstance(v, (int, float))
        }

        logger.info(
            f"[SimHook] Script returned {len(predictions)} properties in {elapsed:.2f}s"
        )
        return {
            "success": True,
            "predictions": predictions,
            "stderr": "",
            "runtime_s": round(elapsed, 3),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "predictions": {},
            "stderr": f"Script timed out after {timeout}s",
            "runtime_s": float(timeout),
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error(f"[SimHook] Unexpected error: {e}")
        return {
            "success": False,
            "predictions": {},
            "stderr": str(e),
            "runtime_s": round(elapsed, 3),
        }


def blend_predictions(
    gp_predictions: Dict[str, Any],
    hook_predictions: Dict[str, float],
    schema,
) -> Dict[str, Any]:
    """
    Merge GP predictions with hook predictions.

    Hook values REPLACE the GP mean for properties the script returned.
    GP std is retained as the uncertainty estimate around the hook value.
    Properties not returned by the hook are served by GP predictions unchanged.

    Parameters
    ----------
    gp_predictions : {property_name: {"mean": float, "std": float, "trained": bool, "unit": str}}
    hook_predictions : {property_name: float}
    schema : ExperimentSchema (used to verify property names)

    Returns
    -------
    Merged predictions dict in the same format as gp_predictions.
    """
    if not hook_predictions:
        return gp_predictions

    blended = {name: dict(pred) for name, pred in gp_predictions.items()}

    for prop in schema.properties:
        if prop.name in hook_predictions:
            hook_val = hook_predictions[prop.name]
            existing = blended.get(prop.name, {})
            # Keep GP std as uncertainty; replace mean with simulation result
            blended[prop.name] = {
                **existing,
                "mean": float(hook_val),
                "source": "simulation_hook",
                "std": existing.get("std", abs(float(hook_val)) * 0.05 + 0.01),
            }

    return blended
