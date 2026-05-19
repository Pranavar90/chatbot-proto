"""
twin.py — Digital Twin simulation engine.

Three capabilities, all built on the existing BoTorch GP surrogate:

  1. interactive_predict(schema_id, composition)
       Instant multi-property GP prediction for any formulation.
       Used by the interactive simulator sliders.

  2. virtual_run(schema_id, n_iterations, ...)
       Run N BO iterations using the GP itself as the lab oracle.
       Mean predictions become the "observed" ground truth — no real lab needed.
       Uses a PRIVATE SurrogateModel clone; the shared registry is untouched
       unless persist=True.

  3. space_map(schema_id, param_x, param_y, resolution, fixed_params)
       Build a 2D grid of GP predictions over two chosen parameter dimensions.
       All other parameters are held at their midpoints (or fixed_params values).
       Returns cells for heatmap rendering on the frontend.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── 1. Interactive Predict ────────────────────────────────────────────────────

def interactive_predict(
    schema_id: str,
    composition: Dict[str, Any],
    sim_hook_path: Optional[str] = None,
    hook_timeout: int = 60,
) -> Dict[str, Any]:
    """
    Predict all schema properties for a given composition using the GP surrogate.
    Optionally blend with a scientist-provided simulation script.

    Parameters
    ----------
    schema_id : str
    composition : dict — {param_name: value} in original units
    sim_hook_path : str|None — absolute path to a simulation script (optional)
    hook_timeout : int — seconds to allow the hook script to run

    Returns
    -------
    {
      "schema_id": str,
      "composition": dict,
      "predictions": {property_name: {"mean", "std", "unit", "trained", "source"}},
      "scoring": {"composite_score", "scores", "weights_used", "meets_goals"},
      "n_training_points": int,
      "is_ready": bool,
      "hook_result": dict | None,
    }
    """
    from surrogate.registry import get_surrogate_registry
    from qdrant_store import get_store
    from experiment_runner import calculate_composite_score

    store = get_store()
    schema = store.get_schema(schema_id)
    if schema is None:
        raise ValueError(f"Schema '{schema_id}' not found")

    registry = get_surrogate_registry()
    model = registry.get_or_load(schema_id, schema)
    predictions = model.predict_single(composition)

    hook_result = None
    if sim_hook_path:
        from sim_hook import call_simulation_hook, blend_predictions
        hook_result = call_simulation_hook(sim_hook_path, composition, timeout=hook_timeout)
        if hook_result["success"] and hook_result["predictions"]:
            predictions = blend_predictions(predictions, hook_result["predictions"], schema)

    scoring = calculate_composite_score(predictions, schema=schema)

    return {
        "schema_id": schema_id,
        "composition": composition,
        "predictions": predictions,
        "scoring": scoring,
        "n_training_points": model.n_training_points(),
        "is_ready": model.is_ready(),
        "hook_result": hook_result,
    }


# ── 2. Virtual Run ────────────────────────────────────────────────────────────

def virtual_run(
    schema_id: str,
    n_iterations: int = 10,
    seed: int = 42,
    persist: bool = False,
    use_custom_objective: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run N simulated BO iterations using the GP as the experimental oracle.

    Algorithm per iteration:
      1. Ask suggest_next() for the best candidate (or use DoE if GP not ready)
      2. Evaluate that candidate via model.predict_single() — means become observations
      3. Add the point to the private surrogate clone and retrain
      4. Record the iteration in a trajectory list

    The shared registry model is NEVER touched unless persist=True.
    When persist=True, all virtual observations are fed to registry.add_observation()
    at the end, which retrains and saves the real model.

    Parameters
    ----------
    n_iterations : int — number of virtual iterations (1–50 recommended)
    seed : int — random seed for the BO candidate pool
    persist : bool — if True, add virtual observations to the real GP model
    use_custom_objective : str|None — custom scoring expression (SymPy)

    Returns
    -------
    {
      "run_id": str,
      "schema_id": str,
      "n_iterations": int,
      "persisted": bool,
      "trajectory": [
        {
          "iteration": int,
          "composition": dict,
          "predictions": dict,
          "acquisition_score": float,
          "composite_score": float,
          "custom_objective_score": float | None,
          "n_training_points": int,
          "best_values": dict,
        }
      ],
      "final_best_values": dict,
      "best_composite_score": float,
      "best_composition": dict,
    }
    """
    from surrogate.registry import get_surrogate_registry
    from surrogate.acquisition import suggest_next
    from surrogate.doe import latin_hypercube, suggest_n_initial
    from surrogate.model import SurrogateModel
    from surrogate.encoder import encode
    from experiment_runner import calculate_composite_score
    from qdrant_store import get_store

    store = get_store()
    schema = store.get_schema(schema_id)
    if schema is None:
        raise ValueError(f"Schema '{schema_id}' not found")

    n_iterations = max(1, min(n_iterations, 50))  # safety cap

    registry = get_surrogate_registry()
    # Load the real model to get current training data
    registry.get_or_load(schema_id, schema)
    X_base, Y_base = registry.get_training_data(schema_id)

    # Clone training arrays so the private sim model starts from the same state
    if len(X_base) > 0:
        X_sim = X_base.copy()
        Y_sim = Y_base.copy()
    else:
        n_params = len(schema.parameters)
        n_props = len(schema.properties)
        X_sim = np.empty((0, n_params))
        Y_sim = np.empty((0, n_props))

    # Private SurrogateModel — never touches the shared registry
    sim_model = SurrogateModel(schema)
    if len(X_sim) >= 3:
        sim_model.fit(X_sim, Y_sim)

    trajectory = []
    run_id = str(uuid.uuid4())

    # Track per-property best values for acquisition function
    best_values: Dict[str, float] = {p.name: p.target for p in schema.properties}
    # Seed best_values from existing training data if available
    if len(Y_sim) > 0:
        for j, prop in enumerate(schema.properties):
            col = Y_sim[:, j]
            valid = col[~np.isnan(col)]
            if len(valid) > 0:
                if prop.direction == "minimize":
                    best_values[prop.name] = float(np.min(valid))
                else:
                    best_values[prop.name] = float(np.max(valid))

    for i in range(n_iterations):
        # --- Candidate selection ---
        if sim_model.is_ready():
            candidates = suggest_next(
                sim_model,
                schema,
                n_suggestions=1,
                best_values=best_values,
                seed=seed + i,
            )
            if candidates:
                best_cand = candidates[0]
                composition = best_cand["composition"]
                acq_score = best_cand["acquisition_score"]
            else:
                # Fallback to random DoE point
                doe_pts = latin_hypercube(schema, n_points=suggest_n_initial(schema), seed=seed + i)
                composition = {k: v for k, v in doe_pts[i % len(doe_pts)].items()}
                acq_score = 0.0
        else:
            # Not enough data yet — use Design of Experiments
            n_doe = suggest_n_initial(schema)
            doe_pts = latin_hypercube(schema, n_points=n_doe, seed=seed + i)
            composition = {k: v for k, v in doe_pts[i % len(doe_pts)].items()}
            acq_score = 0.0

        # --- Evaluate via GP oracle ---
        if sim_model.is_ready():
            predictions = sim_model.predict_single(composition)
        else:
            # Prior predictions: use schema targets with high uncertainty
            predictions = {
                p.name: {
                    "mean": p.target,
                    "std": abs(p.target) * 0.3 + 1.0,
                    "trained": False,
                    "unit": p.unit,
                }
                for p in schema.properties
            }

        # --- Scoring ---
        scoring = calculate_composite_score(predictions, schema=schema)
        composite_score = scoring["composite_score"]

        custom_obj_score = None
        if use_custom_objective and use_custom_objective.strip():
            from custom_objective import evaluate_objective
            try:
                custom_obj_score = round(evaluate_objective(use_custom_objective, predictions), 4)
            except Exception as e:
                logger.warning(f"[VirtualRun] Custom objective failed at iter {i+1}: {e}")

        # --- Update best values for next iteration's EI ---
        for prop in schema.properties:
            val = predictions.get(prop.name, {}).get("mean") if isinstance(
                predictions.get(prop.name), dict
            ) else None
            if val is None:
                continue
            if prop.direction == "minimize" and val < best_values[prop.name]:
                best_values[prop.name] = val
            elif prop.direction != "minimize" and val > best_values[prop.name]:
                best_values[prop.name] = val

        # --- Add observation to private sim_model ---
        obs_values = {
            name: pred["mean"]
            for name, pred in predictions.items()
            if isinstance(pred, dict) and "mean" in pred
        }
        x_new = encode(composition, schema).reshape(1, -1)
        y_new = np.array(
            [obs_values.get(p.name, np.nan) for p in schema.properties],
            dtype=np.float32,
        ).reshape(1, -1)

        if len(X_sim) == 0:
            X_sim = x_new
            Y_sim = y_new
        else:
            X_sim = np.vstack([X_sim, x_new])
            Y_sim = np.vstack([Y_sim, y_new])

        # Cap at 200 to keep GP training fast on RTX 3050
        if len(X_sim) > 200:
            X_sim = X_sim[-200:]
            Y_sim = Y_sim[-200:]

        if len(X_sim) >= 3:
            try:
                sim_model.fit(X_sim, Y_sim)
            except Exception as e:
                logger.warning(f"[VirtualRun] GP refit failed at iter {i+1}: {e}")

        trajectory.append({
            "iteration": i + 1,
            "composition": {k: round(v, 4) if isinstance(v, float) else v
                            for k, v in composition.items()},
            "predictions": predictions,
            "acquisition_score": round(acq_score, 4),
            "composite_score": composite_score,
            "custom_objective_score": custom_obj_score,
            "n_training_points": len(X_sim),
            "best_values": dict(best_values),
        })

    # --- Optionally persist virtual observations into the real model ---
    if persist and trajectory:
        logger.info(f"[VirtualRun] Persisting {len(trajectory)} virtual observations to real model")
        for step in trajectory:
            real_obs = {
                name: pred["mean"]
                for name, pred in step["predictions"].items()
                if isinstance(pred, dict) and "mean" in pred
            }
            try:
                registry.add_observation(schema_id, step["composition"], real_obs)
            except Exception as e:
                logger.error(f"[VirtualRun] Failed to persist iter {step['iteration']}: {e}")

    best_score = max((t["composite_score"] for t in trajectory), default=0.0)
    best_step = max(trajectory, key=lambda t: t["composite_score"], default={})

    return {
        "run_id": run_id,
        "schema_id": schema_id,
        "n_iterations": len(trajectory),
        "persisted": persist,
        "trajectory": trajectory,
        "final_best_values": best_values,
        "best_composite_score": round(best_score, 4),
        "best_composition": best_step.get("composition", {}),
    }


# ── 3. Space Map ──────────────────────────────────────────────────────────────

def space_map(
    schema_id: str,
    param_x: str,
    param_y: str,
    resolution: int = 20,
    fixed_params: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Build a 2D grid of GP predictions over two chosen parameter dimensions.

    All other parameters are held at their midpoints (or at fixed_params values).
    Returns a list of cells for heatmap visualization on the frontend.

    Parameters
    ----------
    schema_id : str
    param_x : str — name of the X-axis parameter
    param_y : str — name of the Y-axis parameter
    resolution : int — grid is resolution×resolution (max 30 recommended)
    fixed_params : dict|None — {param_name: value} for non-axis parameters

    Returns
    -------
    {
      "schema_id": str,
      "param_x": str,
      "param_y": str,
      "resolution": int,
      "is_trained": bool,
      "n_training_points": int,
      "cells": [
        {"x": float, "y": float, "{prop_name}_mean": float, "{prop_name}_std": float, ...}
      ],
      "properties": [str],
      "param_x_bounds": {"min", "max", "unit"},
      "param_y_bounds": {"min", "max", "unit"},
    }
    """
    from surrogate.registry import get_surrogate_registry
    from surrogate.encoder import decode
    from qdrant_store import get_store

    store = get_store()
    schema = store.get_schema(schema_id)
    if schema is None:
        raise ValueError(f"Schema '{schema_id}' not found")

    param_names = [p.name for p in schema.parameters]
    if param_x not in param_names:
        raise ValueError(f"Parameter '{param_x}' not found in schema '{schema.name}'")
    if param_y not in param_names:
        raise ValueError(f"Parameter '{param_y}' not found in schema '{schema.name}'")
    if param_x == param_y:
        raise ValueError("param_x and param_y must be different parameters")

    resolution = max(5, min(resolution, 30))  # safety clamp

    registry = get_surrogate_registry()
    model = registry.get_or_load(schema_id, schema)

    x_idx = param_names.index(param_x)
    y_idx = param_names.index(param_y)

    # Build base vector: all params at midpoint [0.5] in normalized space
    n_params = len(schema.parameters)
    base = np.full(n_params, 0.5)

    # Override with fixed_params values (convert from original units to [0,1])
    if fixed_params:
        for pname, raw_val in fixed_params.items():
            if pname in param_names:
                idx = param_names.index(pname)
                param_def = schema.parameters[idx]
                span = param_def.max_val - param_def.min_val
                if span > 0:
                    base[idx] = float(np.clip(
                        (raw_val - param_def.min_val) / span, 0.0, 1.0
                    ))

    # Build grid: resolution × resolution points
    linspace = np.linspace(0.0, 1.0, resolution)
    grid_vecs = []
    for xi in linspace:
        for yi in linspace:
            vec = base.copy()
            vec[x_idx] = xi
            vec[y_idx] = yi
            grid_vecs.append(vec)

    X_grid = np.stack(grid_vecs, axis=0)  # (resolution², n_params)

    # Batch predict
    if model.is_ready():
        raw_preds = model.predict(X_grid)  # {prop: {"mean": array, "std": array}}
    else:
        raw_preds = {
            p.name: {
                "mean": np.full(len(grid_vecs), p.target),
                "std": np.full(len(grid_vecs), abs(p.target) * 0.3 + 1.0),
                "trained": False,
            }
            for p in schema.properties
        }

    # Decode parameter values for axis labels
    param_x_def = schema.parameters[x_idx]
    param_y_def = schema.parameters[y_idx]
    x_vals = param_x_def.min_val + linspace * (param_x_def.max_val - param_x_def.min_val)
    y_vals = param_y_def.min_val + linspace * (param_y_def.max_val - param_y_def.min_val)

    cells = []
    for i, vec in enumerate(grid_vecs):
        xi_idx = i // resolution
        yi_idx = i % resolution
        cell = {
            "x": round(float(x_vals[xi_idx]), 4),
            "y": round(float(y_vals[yi_idx]), 4),
        }
        for pname, pred in raw_preds.items():
            cell[f"{pname}_mean"] = round(float(pred["mean"][i]), 4)
            cell[f"{pname}_std"] = round(float(pred["std"][i]), 4)
        cells.append(cell)

    return {
        "schema_id": schema_id,
        "param_x": param_x,
        "param_y": param_y,
        "resolution": resolution,
        "is_trained": model.is_ready(),
        "n_training_points": model.n_training_points(),
        "cells": cells,
        "properties": [p.name for p in schema.properties],
        "param_x_bounds": {
            "min": param_x_def.min_val,
            "max": param_x_def.max_val,
            "unit": param_x_def.unit,
            "name": param_x_def.name,
        },
        "param_y_bounds": {
            "min": param_y_def.min_val,
            "max": param_y_def.max_val,
            "unit": param_y_def.unit,
            "name": param_y_def.name,
        },
    }
