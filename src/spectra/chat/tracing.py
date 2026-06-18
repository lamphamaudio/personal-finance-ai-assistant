"""Hierarchical tracing and structured JSON logging for LLM and tool operations."""

from __future__ import annotations

import contextvars
import json
import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Generator, Optional
from uuid import uuid4

from spectra.chat.redaction import redact_payload
from spectra.config import load_settings

logger = logging.getLogger("spectra.chat.tracing")

# ContextVar store to propagate trace identifiers down the call hierarchy
current_trace_id = contextvars.ContextVar("current_trace_id", default=None)
current_session_id = contextvars.ContextVar("current_session_id", default=None)
current_user_id = contextvars.ContextVar("current_user_id", default=None)
current_parent_span_id = contextvars.ContextVar("current_parent_span_id", default=None)
current_langsmith_tree = contextvars.ContextVar("current_langsmith_tree", default=None)

_OTEL_INITIALIZED = False


def _init_otel(settings: Any) -> None:
    global _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        return
    endpoint = getattr(settings, "otel_exporter_otlp_endpoint", "")
    if endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider()
            if "http" in endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpExporter
                exporter = OTLPHttpExporter(endpoint=endpoint)
            else:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcExporter
                exporter = OTLPGrpcExporter(endpoint=endpoint)

            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
        except Exception as e:
            logger.warning("Failed to initialize OpenTelemetry OTLP exporter: %s", e)
    _OTEL_INITIALIZED = True


def get_otel_tracer() -> Any:
    try:
        from opentelemetry import trace
        return trace.get_tracer("spectra.chat")
    except ImportError:
        return None


class SpanRecord:
    """Object to capture dynamic outputs and statuses during span execution."""
    def __init__(self) -> None:
        self.outputs: Any = None
        self.error: Optional[str] = None
        self.status: str = "success"


@contextmanager
def start_trace(
    *,
    user_id: str,
    session_id: Optional[str] = None,
    name: str = "chat_request",
    inputs: Any = None,
) -> Generator[SpanRecord, None, None]:
    """Root context manager to initialize a new trace transaction."""
    trace_id = f"trace_{uuid4().hex}"
    
    # Initialize ContextVars for this call stack
    token_trace = current_trace_id.set(trace_id)
    token_session = current_session_id.set(session_id)
    token_user = current_user_id.set(user_id)
    token_parent = current_parent_span_id.set(None)

    try:
        with trace_span(name, "chain", inputs) as rec:
            yield rec
    finally:
        # Reset trace ContextVars
        current_trace_id.reset(token_trace)
        current_session_id.reset(token_session)
        current_user_id.reset(token_user)
        current_parent_span_id.reset(token_parent)


@contextmanager
def trace_span(name: str, span_type: str, inputs: Any) -> Generator[SpanRecord, None, None]:
    """Context manager to trace a nested execution block (e.g. LLM call, Tool call)."""
    trace_id = current_trace_id.get()
    session_id = current_session_id.get()
    user_id = current_user_id.get()
    parent_span_id = current_parent_span_id.get()
    langsmith_parent = current_langsmith_tree.get()

    span_id = f"span_{uuid4().hex[:16]}"
    start_time = time.time()

    # Update context so children know this span is their parent
    token_parent = current_parent_span_id.set(span_id)

    settings = load_settings()

    # LangSmith Run creation (root or child)
    langsmith_run = None
    token_ls = None
    if getattr(settings, "langsmith_api_key", None):
        try:
            if langsmith_parent:
                langsmith_run = langsmith_parent.create_child(
                    name=name,
                    run_type=span_type,
                    inputs=inputs or {},
                )
            else:
                from langsmith.run_trees import RunTree
                langsmith_run = RunTree(
                    name=name,
                    run_type=span_type,
                    inputs=inputs or {},
                    project_name=settings.langsmith_project or "spectra-chatbot",
                    api_url="https://api.smith.langchain.com",
                    api_key=settings.langsmith_api_key,
                )
            token_ls = current_langsmith_tree.set(langsmith_run)
        except Exception:
            pass

    # OpenTelemetry Span creation
    otel_span = None
    if getattr(settings, "otel_exporter_otlp_endpoint", None):
        try:
            _init_otel(settings)
            tracer = get_otel_tracer()
            if tracer:
                otel_span = tracer.start_span(name)
                otel_span.set_attribute("span_id", span_id)
                if trace_id:
                    otel_span.set_attribute("trace_id", trace_id)
                if session_id:
                    otel_span.set_attribute("session_id", session_id)
                if user_id:
                    otel_span.set_attribute("user_id", user_id)
        except Exception:
            pass

    rec = SpanRecord()
    try:
        yield rec
    except Exception as e:
        rec.error = str(e)
        rec.status = "error"
        raise
    finally:
        latency_ms = (time.time() - start_time) * 1000.0

        # End OpenTelemetry Span
        if otel_span:
            try:
                from opentelemetry import trace
                if rec.error:
                    otel_span.record_exception(Exception(rec.error))
                    otel_span.set_status(trace.StatusCode.ERROR, rec.error)
                otel_span.end()
            except Exception:
                pass

        # End LangSmith Span
        if langsmith_run:
            try:
                langsmith_run.end(outputs=rec.outputs, error=rec.error)
                langsmith_run.post()
            except Exception:
                pass

        # Restore context state
        current_parent_span_id.reset(token_parent)
        if token_ls:
            current_langsmith_tree.reset(token_ls)

        # Output unified structured JSON log
        log_data = {
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "name": name,
            "span_type": span_type,
            "inputs": redact_payload(inputs),
            "outputs": redact_payload(rec.outputs) if rec.outputs else None,
            "status": rec.status,
            "error": rec.error,
            "latency_ms": round(latency_ms, 2),
            "session_id": session_id,
            "user_id": user_id,
        }
        logger.info(json.dumps(log_data, ensure_ascii=False))
