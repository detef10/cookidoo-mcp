#!/usr/bin/env python3
"""OpenTelemetry setup for Cookidoo MCP — exports to Dash0."""

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource


def setup_tracing() -> trace.Tracer:
    """Initialise OTel tracing and return a configured Tracer.

    Environment variables (optional — hard-coded defaults are used as fallback):
      DASH0_AUTH_TOKEN              Dash0 ingestion token
      OTEL_EXPORTER_OTLP_ENDPOINT  Base URL of the OTLP HTTP endpoint
      ENV                          Deployment environment label (default: production)
    """
    dash0_token = os.environ.get(
        "DASH0_AUTH_TOKEN",
        "auth_rn5JPdNaNFiMLB8OKuQWxtcaa7kc9khC",
    )
    otel_endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "https://ingress.europe-west4.gcp.dash0.com",
    )
    environment = os.environ.get("ENV", "production")

    resource = Resource.create({
        "service.name": "cookidoo-mcp",
        "service.version": "1.0.0",
        "deployment.environment": environment,
    })

    exporter = OTLPSpanExporter(
        endpoint=f"{otel_endpoint}/v1/traces",
        headers={
            "Authorization": f"Bearer {dash0_token}",
            "Dash0-Dataset": "default",
        },
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    return trace.get_tracer("cookidoo-mcp", "1.0.0")
