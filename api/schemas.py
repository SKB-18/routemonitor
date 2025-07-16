"""Pydantic v2 request/response schemas for RouteMonitor API."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# ─── Helpers ──────────────────────────────────────────────────────────────────

CIDR_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}/([0-9]|[1-2][0-9]|3[0-2])$")
IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _validate_ipv4(v: str) -> str:
    if not IPV4_RE.match(v):
        raise ValueError(f"Invalid IPv4 address: {v!r}")
    parts = v.split(".")
    if any(int(p) > 255 for p in parts):
        raise ValueError(f"Invalid IPv4 address: {v!r}")
    return v


def _validate_cidr(v: str) -> str:
    if v is None:
        return v
    if not CIDR_RE.match(v):
        raise ValueError(f"Invalid CIDR prefix: {v!r}")
    ip_part = v.split("/")[0]
    _validate_ipv4(ip_part)
    return v


def _validate_asn(v: int) -> int:
    if not (1 <= v <= 4294967295):
        raise ValueError(f"ASN must be 1–4294967295, got {v}")
    return v


# ─── BGPSpeaker ───────────────────────────────────────────────────────────────


class BGPSpeakerRequest(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    router_id: str = Field(..., description="IPv4 router ID, e.g. 10.0.0.1")
    local_asn: int = Field(..., ge=1, le=4294967295)
    bmp_listen_address: str = Field(
        ..., description="IP:port the speaker sends BMP from"
    )

    @field_validator("router_id")
    @classmethod
    def validate_router_id(cls, v: str) -> str:
        return _validate_ipv4(v)

    @field_validator("bmp_listen_address")
    @classmethod
    def validate_bmp_address(cls, v: str) -> str:
        # Accept "IP:port" or bare IP
        if ":" in v:
            ip, port = v.rsplit(":", 1)
            _validate_ipv4(ip)
            if not (1 <= int(port) <= 65535):
                raise ValueError(f"Invalid port: {port}")
        else:
            _validate_ipv4(v)
        return v


class BGPSpeakerResponse(BaseModel):
    id: UUID
    hostname: str
    router_id: str
    local_asn: int
    bmp_listen_address: str
    status: str
    last_seen: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── RouteEvent ───────────────────────────────────────────────────────────────


class RouteEventResponse(BaseModel):
    id: UUID
    speaker_id: UUID
    timestamp: datetime
    event_type: str
    prefix: Optional[str]
    path_attributes: Optional[Dict[str, Any]]
    withdrawn_prefixes: Optional[List[str]]
    neighbor_ip: str
    neighbor_asn: int
    sequence_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RouteEventQueryParams(BaseModel):
    """Query parameters for filtering route events."""

    speaker_id: Optional[UUID] = None
    prefix: Optional[str] = None
    neighbor_ip: Optional[str] = None
    event_type: Optional[str] = None  # UPDATE | WITHDRAW | STATE_CHANGE
    limit: int = Field(100, ge=1, le=10000)
    offset: int = Field(0, ge=0)

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_cidr(v)
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"UPDATE", "WITHDRAW", "STATE_CHANGE"}
        if v is not None and v.upper() not in allowed:
            raise ValueError(f"event_type must be one of {allowed}")
        return v.upper() if v else v


# ─── Anomaly ──────────────────────────────────────────────────────────────────


class AnomalyResponse(BaseModel):
    id: UUID
    speaker_id: UUID
    prefix: Optional[str]
    neighbor_ip: Optional[str]
    anomaly_type: str
    severity: str
    detected_at: datetime
    resolved_at: Optional[datetime]
    details: Optional[Dict[str, Any]]
    acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class AnomalyAcknowledgeRequest(BaseModel):
    acknowledged_by: str = Field(..., min_length=1, max_length=100)


# ─── Alert / Webhook subscription ─────────────────────────────────────────────


class AlertWebhookRequest(BaseModel):
    """Register a webhook to receive anomaly alerts."""

    target_url: str = Field(..., description="HTTP(S) endpoint to POST alerts to")
    severity_min: str = Field(
        "WARNING", description="Minimum severity: INFO | WARNING | CRITICAL"
    )
    anomaly_types: List[str] = Field(
        default_factory=lambda: ["ROUTE_FLAP", "UNUSUAL_CHURN", "CORRELATED_FAILURE"],
        description="Anomaly types to subscribe to",
    )

    @field_validator("target_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("target_url must start with http:// or https://")
        return v

    @field_validator("severity_min")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        allowed = {"INFO", "WARNING", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"severity_min must be one of {allowed}")
        return v.upper()


class AlertResponse(BaseModel):
    id: UUID
    anomaly_id: UUID
    alert_type: str
    target_url: str
    severity: str
    delivery_status: str
    retry_count: int
    sent_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Telemetry Metrics ────────────────────────────────────────────────────────


class TelemetryMetricsResponse(BaseModel):
    speaker_id: str
    prefix: Optional[str]
    time_range: str
    data_points: List[
        Dict[str, Any]
    ]  # [{time, flap_count, route_count, path_diversity, ...}]


# ─── Health ───────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    services: Dict[str, str]  # {db: "ok", redis: "ok", influxdb: "ok"}
