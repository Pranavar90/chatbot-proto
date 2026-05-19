"""
twin_routes.py — FastAPI router for Digital Twin endpoints.

All routes are under /api/twin prefix.

Endpoints:
  POST /api/twin/{schema_id}/predict       — Interactive simulator
  POST /api/twin/{schema_id}/virtual-run   — N BO iterations on GP oracle
  POST /api/twin/{schema_id}/space-map     — 2D property grid for heatmap
  POST /api/twin/objective/validate        — Validate a custom scoring expression
  POST /api/twin/hook/test                 — Test a simulation hook script
  GET  /api/twin/{schema_id}/training-data — Explored training points for space map overlay

Import and register in main.py:
  from twin_routes import twin_router
  app.include_router(twin_router)
"""

import asyncio
import functools
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

twin_router = APIRouter(prefix="/api/twin", tags=["digital-twin"])


# ── Shared helper ─────────────────────────────────────────────────────────────

async def _in_thread(fn, *args, **kwargs):
    """Run a blocking function in a thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


# ── Request / Response Models ─────────────────────────────────────────────────

class PredictRequest(BaseModel):
    composition: Dict[str, float] = Field(..., description="Parameter values in original units")
    sim_hook_path: Optional[str] = Field(None, description="Absolute path to simulation script")
    hook_timeout: int = Field(60, ge=5, le=300, description="Hook timeout in seconds")


class VirtualRunRequest(BaseModel):
    n_iterations: int = Field(10, ge=1, le=50, description="Number of virtual iterations")
    seed: int = Field(42, description="Random seed for BO candidate pool")
    persist: bool = Field(False, description="If true, add virtual observations to the real GP model")
    custom_objective: Optional[str] = Field(None, description="Custom scoring expression")


class SpaceMapRequest(BaseModel):
    param_x: str = Field(..., description="Parameter for the X axis")
    param_y: str = Field(..., description="Parameter for the Y axis")
    resolution: int = Field(20, ge=5, le=30, description="Grid resolution (resolution × resolution cells)")
    fixed_params: Optional[Dict[str, float]] = Field(None, description="Fixed values for non-axis parameters")


class ValidateObjectiveRequest(BaseModel):
    expression: str = Field(..., description="Scoring expression to validate")
    property_names: List[str] = Field(..., description="Available property names")


class HookTestRequest(BaseModel):
    script_path: str = Field(..., description="Absolute path to the simulation script")
    composition: Dict[str, float] = Field(..., description="Sample composition to test with")
    timeout: int = Field(30, ge=5, le=300)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@twin_router.post("/{schema_id}/predict")
async def predict_formulation(schema_id: str, req: PredictRequest):
    """
    Instantly predict all schema properties for a given formulation using the GP surrogate.
    Optionally blends GP predictions with a simulation hook script.
    """
    try:
        from twin import interactive_predict
        result = await _in_thread(
            interactive_predict,
            schema_id,
            req.composition,
            req.sim_hook_path,
            req.hook_timeout,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[TwinRoutes] predict error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@twin_router.post("/{schema_id}/virtual-run")
async def run_virtual_experiment(schema_id: str, req: VirtualRunRequest):
    """
    Run N BO iterations using the GP as the experimental oracle.
    Returns a convergence trajectory. Does NOT modify the real GP unless persist=True.
    """
    try:
        from twin import virtual_run
        result = await _in_thread(
            virtual_run,
            schema_id,
            req.n_iterations,
            req.seed,
            req.persist,
            req.custom_objective,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[TwinRoutes] virtual-run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@twin_router.post("/{schema_id}/space-map")
async def get_space_map(schema_id: str, req: SpaceMapRequest):
    """
    Build a 2D grid of GP predictions over two parameter dimensions.
    Returns cells for heatmap rendering on the frontend.
    """
    try:
        from twin import space_map
        result = await _in_thread(
            space_map,
            schema_id,
            req.param_x,
            req.param_y,
            req.resolution,
            req.fixed_params,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[TwinRoutes] space-map error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@twin_router.post("/objective/validate")
async def validate_objective(req: ValidateObjectiveRequest):
    """
    Validate a custom scoring expression without evaluating it.
    Returns {valid, symbols, warnings} or {valid, error}.
    """
    from custom_objective import validate_expression
    return validate_expression(req.expression, req.property_names)


@twin_router.post("/hook/test")
async def test_hook(req: HookTestRequest):
    """
    Test a simulation hook script with a sample composition.
    Returns {success, predictions, stderr, runtime_s}.
    """
    try:
        from sim_hook import call_simulation_hook
        result = await _in_thread(
            call_simulation_hook,
            req.script_path,
            req.composition,
            req.timeout,
        )
        return result
    except Exception as e:
        logger.error(f"[TwinRoutes] hook/test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@twin_router.get("/{schema_id}/training-data")
async def get_training_data(schema_id: str):
    """
    Return all training points for a schema (for space map overlay).
    Each point includes the normalized X vector, decoded composition, and Y values.
    """
    try:
        from surrogate.registry import get_surrogate_registry
        from surrogate.encoder import decode
        from qdrant_store import get_store

        store = get_store()
        schema = store.get_schema(schema_id)
        if schema is None:
            raise HTTPException(status_code=404, detail=f"Schema '{schema_id}' not found")

        registry = get_surrogate_registry()
        X, Y = registry.get_training_data(schema_id)

        if len(X) == 0:
            return {
                "schema_id": schema_id,
                "n_points": 0,
                "points": [],
                "parameter_names": [p.name for p in schema.parameters],
                "property_names": [p.name for p in schema.properties],
            }

        points = []
        for i in range(len(X)):
            x_vec = X[i]
            composition = decode(x_vec, schema)
            props = {}
            for j, prop in enumerate(schema.properties):
                val = float(Y[i, j]) if Y.ndim == 2 else float(Y[i])
                if val == val:  # not NaN
                    props[prop.name] = round(val, 4)

            # Normalize each parameter to [0,1] for overlay positioning
            x_normalized = [round(float(v), 4) for v in x_vec]

            points.append({
                "x_normalized": x_normalized,
                "composition": {k: round(v, 4) if isinstance(v, float) else v
                                for k, v in composition.items()},
                "properties": props,
            })

        return {
            "schema_id": schema_id,
            "n_points": len(points),
            "points": points,
            "parameter_names": [p.name for p in schema.parameters],
            "property_names": [p.name for p in schema.properties],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TwinRoutes] training-data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
