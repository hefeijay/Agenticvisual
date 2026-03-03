"""
VIS Demo Web Server
FastAPI backend with SSE streaming for the agentic visualization system.

Usage:
    uvicorn web_server:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import io
import json
import shutil
import sys
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

sys.path.insert(0, str(Path(__file__).parent))

from config import validate_config
from config.settings import Settings
from core import get_session_manager
from core.vlm_service import get_vlm_service
from csv_to_vega import VegaConverter
from db import get_db

# ---------------------------------------------------------------------------
# App & globals
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VIS Demo – Agentic Visualization System",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

_executor = ThreadPoolExecutor(max_workers=4)

# ---------------------------------------------------------------------------
# Serve built frontend (only if dist/ exists after `npm run build`)
# ---------------------------------------------------------------------------
_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateSessionBody(BaseModel):
    dataset_id: Optional[str] = None
    spec: Optional[Dict] = None
    chart_type: Optional[str] = "scatter"
    encoding: Optional[Dict] = None
    width: Optional[int] = 600
    height: Optional[int] = 400
    title: Optional[str] = None


class QueryBody(BaseModel):
    query: str
    run_mode: Optional[str] = "cooperative"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_analysis_summary(result: Dict) -> str:
    """Build a short text summary of what the agent did, for suggestion generation."""
    parts = []
    mode = result.get("mode", "")
    iterations = result.get("iterations") or result.get("explorations") or []
    for it in iterations[-3:]:
        tool_exec = it.get("tool_execution", {})
        tool_name = tool_exec.get("tool_name", "")
        if tool_name:
            parts.append(f"Tool call: {tool_name}")
        analysis = it.get("analysis_summary", {})
        for insight in (analysis.get("key_insights") or [])[:2]:
            parts.append(f"Insight: {insight}")
    report = result.get("final_report", {})
    if isinstance(report, dict) and report.get("summary"):
        parts.append(f"Summary: {report['summary'][:200]}")
    return "\n".join(parts) if parts else f"Completed {mode} analysis"


def _generate_suggestions_via_vlm(
    result: Dict,
    current_spec: Dict | None,
    conversation_history: List[Dict] | None = None,
) -> List[Dict]:
    """Use VLM to generate 4 context-aware, directly actionable suggestions."""
    try:
        vlm = get_vlm_service()
    except Exception:
        return _generate_suggestions_fallback()

    analysis_summary = _build_analysis_summary(result)

    spec_brief = ""
    if current_spec and isinstance(current_spec, dict):
        mark = current_spec.get("mark")
        if isinstance(mark, dict):
            mark = mark.get("type", "unknown")
        encoding = current_spec.get("encoding", {})
        enc_desc = ", ".join(
            f'{ch}={chd.get("field","?")}'
            for ch, chd in encoding.items()
            if isinstance(chd, dict) and "field" in chd
        )
        data_vals = current_spec.get("data", {}).get("values", [])
        fields = list(data_vals[0].keys()) if data_vals else []
        spec_brief = (
            f"Chart type: {mark}\n"
            f"Encoding: {enc_desc}\n"
            f"Data fields: {', '.join(fields)}\n"
            f"Row count: {len(data_vals)}"
        )

    # summarise prior rounds so VLM knows what's already been done
    history_block = ""
    if conversation_history:
        history_lines = []
        for entry in conversation_history[-5:]:
            q = entry.get("query", "")
            intent = entry.get("intent", "")
            history_lines.append(f"- [{intent}] {q}")
        if history_lines:
            history_block = "Prior analysis history (do NOT repeat these):\n" + "\n".join(history_lines) + "\n\n"

    prompt = (
        "You are a visualization analysis assistant. The user just completed an analysis round. "
        "Based on the current analysis results and data context, provide exactly 4 specific, "
        "directly actionable next-step analysis suggestions.\n\n"
        "Requirements:\n"
        "1. Each suggestion must be a complete analysis instruction that the agent can execute directly\n"
        "2. Suggestions should be grounded in the current data and results, referencing specific field names, categories, or value ranges\n"
        "3. The 4 suggestions should cover diverse directions (e.g., data filtering / chart transformation / deep analysis / comparison)\n"
        "4. Do not repeat previously completed analyses\n"
        "5. Match the language of the user's most recent query. If the user asked in Chinese, write suggestions in Chinese; if in English, write in English\n\n"
        f"Current chart info:\n{spec_brief}\n\n"
        f"{history_block}"
        f"This round's analysis results:\n{analysis_summary}\n\n"
        'Return strictly in the following JSON format (no other content):\n'
        '[\n'
        '  {"label": "Short title (4-8 words)", "description": "One-sentence description", "query": "Full analysis instruction"},\n'
        '  ...\n'
        ']'
    )

    response = vlm.call(
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        system_prompt="You are a visualization analysis suggestion generator. Return only a JSON array. Match the language of the user's query.",
        expect_json=True,
    )

    if response.get("success") and response.get("parsed_json"):
        parsed = response["parsed_json"]
        items = parsed if isinstance(parsed, list) else parsed.get("suggestions", [])
        suggestions = []
        for i, item in enumerate(items[:4]):
            if isinstance(item, dict) and item.get("query"):
                suggestions.append({
                    "id": f"vlm_sug_{i}",
                    "label": item.get("label", f"Suggestion {i+1}"),
                    "description": item.get("description", ""),
                    "type": "direct",
                    "payload": item["query"],
                })
        if suggestions:
            return suggestions

    return _generate_suggestions_fallback()


def _generate_suggestions_fallback() -> List[Dict]:
    """Static fallback when VLM suggestion generation fails."""
    return [
        {
            "id": "fb_explore",
            "label": "Explore Data",
            "description": "Let the agent autonomously discover interesting patterns",
            "type": "direct",
            "payload": "Autonomously explore the current data and find the most valuable insights",
        },
        {
            "id": "fb_trend",
            "label": "Trend & Correlation",
            "description": "Analyze trends and correlations between variables",
            "type": "direct",
            "payload": "Analyze variable correlations and trend characteristics in the current data",
        },
        {
            "id": "fb_compare",
            "label": "Category Comparison",
            "description": "Compare differences across categories",
            "type": "direct",
            "payload": "Compare numerical differences and distribution characteristics across categories",
        },
        {
            "id": "fb_outlier",
            "label": "Outlier Detection",
            "description": "Find outliers and anomalies in the data",
            "type": "direct",
            "payload": "Detect and highlight outliers and anomalies in the data",
        },
    ]


_IMAGE_KEYS = frozenset({"images", "current_image", "final_image", "image_base64", "image_path"})
_LARGE_STR_KEYS = frozenset({"image", "image_base64", "image_path", "url"})
_MAX_DEPTH = 60


def _strip_images(obj: Any, _depth: int = 0) -> Any:
    """Recursively remove base64 image data from dicts/lists.

    Guards against deeply-nested or circular structures via a depth cap.
    """
    if _depth > _MAX_DEPTH:
        return None
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k in _IMAGE_KEYS:
                continue
            if k in _LARGE_STR_KEYS and isinstance(v, str) and len(v) > 1000:
                continue
            result[k] = _strip_images(v, _depth + 1)
        return result
    if isinstance(obj, list):
        return [_strip_images(i, _depth + 1) for i in obj]
    return obj


def _clean_result_for_sse(result: Dict) -> Dict:
    cleaned = _strip_images(result)
    cleaned.pop("final_image", None)
    return cleaned


def _persist_session(session_id: str, iteration_records: List[Dict] | None = None,
                     final_report: Dict | None = None) -> None:
    """Write current in-memory session state to SQLite."""
    db = get_db()
    session_mgr = get_session_manager()
    state = session_mgr.get_session_state(session_id)
    if state is None:
        return

    db_data = {
        "session_id": session_id,
        "dataset_id": session_mgr.get_session(session_id).get("dataset_id"),
        "created_at": state.get("created_at", time.time()),
        "last_activity": state.get("last_activity", time.time()),
        "chart_type": state.get("chart_type", ""),
        "current_spec": state.get("current_spec"),
        "spec_history": [],
        "conversation_history": state.get("conversation_history", []),
        "iteration_records": iteration_records or [],
        "final_report": final_report,
    }
    db.save_session(session_id, db_data)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    errors = validate_config()
    if errors:
        print("⚠️  Config warnings:")
        for e in errors:
            print(f"   - {e}")
    else:
        print("✅ Configuration validated")
    UPLOAD_DIR.mkdir(exist_ok=True)
    print("🚀 VIS Demo API started  →  http://localhost:8001")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    errors = validate_config()
    return {
        "status": "ok" if not errors else "degraded",
        "model_available": not bool(errors),
        "model": Settings.VLM_MODEL,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

@app.post("/api/files/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported")

    dataset_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{dataset_id}_{file.filename}"

    content = await file.read()
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    try:
        converter = VegaConverter(str(save_path))
    except Exception as exc:
        raise HTTPException(400, f"Failed to parse CSV: {exc}") from exc

    column_info = converter.get_column_info()
    preview = converter.df.head(5).to_dict(orient="records")
    row_count = len(converter.df)

    db = get_db()
    db.save_dataset(
        dataset_id=dataset_id,
        filename=file.filename,
        csv_path=str(save_path),
        column_info=column_info,
        row_count=row_count,
        preview=preview,
    )

    return {
        "dataset_id": dataset_id,
        "filename": file.filename,
        "row_count": row_count,
        "column_info": column_info,
        "preview": preview,
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
async def list_sessions():
    db = get_db()
    return {"sessions": db.list_sessions()}


@app.post("/api/sessions")
async def create_session(body: CreateSessionBody):
    session_mgr = get_session_manager()
    db = get_db()

    if body.spec:
        vega_spec = body.spec
        dataset_id = None
    elif body.dataset_id:
        ds = db.get_dataset(body.dataset_id)
        if not ds:
            raise HTTPException(404, "Dataset not found")

        encoding = body.encoding or {}
        try:
            converter = VegaConverter(ds["csv_path"])
            vega_spec = converter.convert(
                chart_type=body.chart_type or "scatter",
                x=encoding.get("x"),
                y=encoding.get("y"),
                color=encoding.get("color"),
                size=encoding.get("size"),
                columns=encoding.get("columns"),
                normalize=encoding.get("normalize", False),
                source=encoding.get("source"),
                target=encoding.get("target"),
                value=encoding.get("value"),
                title=body.title,
                width=body.width or 600,
                height=body.height or 400,
            )
        except Exception as exc:
            raise HTTPException(400, f"Spec generation failed: {exc}") from exc
        dataset_id = body.dataset_id
    else:
        raise HTTPException(400, "Provide either 'spec' or 'dataset_id'")

    loop = asyncio.get_running_loop()
    session_id = await loop.run_in_executor(_executor, session_mgr.create_session, vega_spec)
    if not session_id:
        raise HTTPException(500, "Session creation failed (check logs)")

    # attach dataset_id to session
    raw = session_mgr.get_session(session_id)
    if raw:
        raw["dataset_id"] = dataset_id

    # persist to SQLite
    await loop.run_in_executor(_executor, _persist_session, session_id)

    return {
        "session_id": session_id,
        "baseline_spec": vega_spec,
        "dataset_id": dataset_id,
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session_mgr = get_session_manager()
    state = session_mgr.get_session_state(session_id)
    if state:
        return state

    db = get_db()
    db_state = db.get_session(session_id)
    if db_state:
        return db_state

    raise HTTPException(404, "Session not found")


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    session_mgr = get_session_manager()
    if session_id in session_mgr.sessions:
        del session_mgr.sessions[session_id]
    db = get_db()
    db.delete_session(session_id)
    return {"success": True}


# ---------------------------------------------------------------------------
# Reset view
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/reset")
async def reset_view(session_id: str):
    session_mgr = get_session_manager()
    if session_id not in session_mgr.sessions:
        raise HTTPException(404, "Session not found")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, session_mgr.reset_view, session_id)
    if result.get("success"):
        session = session_mgr.get_session(session_id)
        current_spec = session.get("vega_spec") if session else None
        await loop.run_in_executor(_executor, _persist_session, session_id)
        return {"success": True, "message": result.get("message", "View reset"), "current_spec": current_spec}
    raise HTTPException(500, result.get("error", "Reset failed"))


# ---------------------------------------------------------------------------
# Query with SSE streaming
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/query")
async def query_stream(session_id: str, body: QueryBody):
    session_mgr = get_session_manager()
    if session_id not in session_mgr.sessions:
        # try to restore from SQLite
        db = get_db()
        db_state = db.get_session(session_id)
        if not db_state or not db_state.get("current_spec"):
            raise HTTPException(404, "Session not found")
        restored_id = await asyncio.get_running_loop().run_in_executor(
            _executor, session_mgr.create_session, db_state["current_spec"]
        )
        if restored_id != session_id:
            # remap key to original session_id
            session_mgr.sessions[session_id] = session_mgr.sessions.pop(restored_id)
            session_mgr.sessions[session_id]["session_id"] = session_id

    async def generate():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        done = asyncio.Event()
        iteration_records: List[Dict] = []
        spec_version_counter = [0]

        def event_cb(event_type: str, data: dict):
            nonlocal iteration_records
            clean = _strip_images(data)
            # track view updates with spec_id
            if event_type == "view.updated":
                spec_version_counter[0] += 1
                clean["spec_id"] = f"spec_{int(time.time()*1000)}_{spec_version_counter[0]}"
            if event_type == "iteration.finished":
                iteration_records.append(clean)
            loop.call_soon_threadsafe(
                queue.put_nowait,
                json.dumps({"event": event_type, "data": clean}),
            )

        async def _run():
            try:
                return await loop.run_in_executor(
                    _executor,
                    lambda: session_mgr.process_query(
                        session_id, body.query, event_callback=event_cb
                    ),
                )
            finally:
                done.set()

        task = asyncio.create_task(_run())

        # stream events while processing
        while not done.is_set() or not queue.empty():
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=0.4)
                yield {"data": payload}
            except asyncio.TimeoutError:
                if done.is_set():
                    break
                yield {"data": json.dumps({"event": "ping"})}

        # drain remaining
        while not queue.empty():
            yield {"data": queue.get_nowait()}

        # final result
        try:
            result = await task
        except Exception as exc:
            yield {"data": json.dumps({"event": "error", "data": {"message": str(exc)}})}
            return

        if not result.get("success"):
            yield {"data": json.dumps({"event": "error", "data": {"message": result.get("error", "Unknown error")}})}
            return

        _session_state = session_mgr.get_session_state(session_id) or {}
        _current_spec = _session_state.get("current_spec") or result.get("current_spec")
        _conv_history = _session_state.get("conversation_history", [])
        suggestions = await loop.run_in_executor(
            _executor,
            lambda: _generate_suggestions_via_vlm(result, _current_spec, _conv_history),
        )
        clean_result = _clean_result_for_sse(result)
        clean_result["next_action_suggestions"] = suggestions

        # persist
        final_report = result.get("final_report")
        await loop.run_in_executor(
            _executor, _persist_session, session_id, iteration_records, final_report
        )

        yield {"data": json.dumps({"event": "run.finished", "data": clean_result})}

    return EventSourceResponse(generate())


# ---------------------------------------------------------------------------
# Export session as zip
# ---------------------------------------------------------------------------

@app.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str):
    session_mgr = get_session_manager()
    db = get_db()

    state = session_mgr.get_session_state(session_id) or db.get_session(session_id)
    if not state:
        raise HTTPException(404, "Session not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # session.json  (strip any images just in case)
        session_json = json.dumps(_strip_images(state), ensure_ascii=False, indent=2)
        zf.writestr("session.json", session_json)

        # spec_history/
        current_spec = state.get("current_spec")
        if current_spec:
            zf.writestr(
                "spec_history/current_spec.json",
                json.dumps(current_spec, ensure_ascii=False, indent=2),
            )

        raw_session = session_mgr.get_session(session_id)
        spec_hist = (raw_session or {}).get("spec_history", [])
        for idx, spec in enumerate(spec_hist):
            zf.writestr(
                f"spec_history/v{idx + 1}.json",
                json.dumps(spec, ensure_ascii=False, indent=2),
            )

        # report.md
        lines = [
            f"# Session {session_id} – Analysis Report\n",
            f"**Chart type**: {state.get('chart_type', 'unknown')}  \n",
            f"**Exported at**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n",
        ]
        for rec in state.get("iteration_records", []):
            it = rec.get("iteration", "?")
            lines.append(f"## Iteration {it}\n")
            analysis = rec.get("analysis_summary", {})
            insights = analysis.get("key_insights", [])
            if insights:
                lines.append("**Key insights:**\n")
                for ins in insights:
                    lines.append(f"- {ins}\n")
            reasoning = analysis.get("reasoning", "")
            if reasoning:
                lines.append(f"\n**Reasoning:** {reasoning}\n")
            tool = rec.get("tool_name")
            if tool:
                lines.append(f"\n**Tool used:** `{tool}`\n")
            lines.append("\n")

        final_report = state.get("final_report") or {}
        if final_report:
            lines.append("## Summary\n")
            lines.append(f"{final_report.get('summary', '')}\n\n")
            all_insights = final_report.get("all_insights", [])
            if all_insights:
                lines.append("**All insights:**\n")
                for ins in all_insights:
                    lines.append(f"- {ins}\n")

        zf.writestr("report.md", "".join(lines))

    buf.seek(0)

    export_dir = Path(__file__).parent / "results"
    export_dir.mkdir(exist_ok=True)
    zip_path = export_dir / f"session_{session_id[:8]}_{int(time.time())}.zip"
    zip_path.write_bytes(buf.getvalue())

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )


# ---------------------------------------------------------------------------
# Serve SPA (catch-all) – only when frontend is built
# ---------------------------------------------------------------------------

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index = _FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Frontend not built. Run `npm run build` in ./frontend/"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
