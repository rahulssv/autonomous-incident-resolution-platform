"""Correlation must use the alert's identifiers, not the monitoring model's prose.

The monitoring agent only sees the incident title, so for "OOMKilled in checkout
worker" it reports affected_service="checkout worker". Interpolated raw, that
produced https://github.com/AIRP-client/checkout worker and every GitHub
evidence lookup 404'd.
"""
from __future__ import annotations

from airp.agents.correlation import CorrelationAgent, _repository_slug
from airp.core.config import Settings

_SETTINGS = Settings(_env_file=None, client_github_org="AIRP-client")


def _state(**overrides) -> dict:
    state = {
        "incident_id": "inc-1",
        "monitoring_assessment": {"affected_service": "checkout worker"},
    }
    state.update(overrides)
    return state


def test_alert_service_label_beats_monitoring_prose() -> None:
    result = CorrelationAgent(_SETTINGS).correlate(
        _state(workload_context={"service_name": "checkout-worker", "source": "alert_labels"})
    )
    assert result.service_name == "checkout-worker"
    assert result.repository_url == "https://github.com/AIRP-client/checkout-worker"


def test_deployment_label_is_used_when_service_label_is_absent() -> None:
    result = CorrelationAgent(_SETTINGS).correlate(
        _state(workload_context={"deployment": "checkout-worker", "source": "alert_labels"})
    )
    assert result.service_name == "checkout-worker"


def test_repository_url_is_well_formed_even_from_prose() -> None:
    """Fallback path: no alert labels, so the model's prose is all there is."""
    result = CorrelationAgent(_SETTINGS).correlate(_state())
    assert result.repository_url == "https://github.com/AIRP-client/checkout-worker"
    assert " " not in result.repository_url


def test_alert_derived_context_is_not_reported_as_a_catalog_match() -> None:
    result = CorrelationAgent(_SETTINGS).correlate(
        _state(workload_context={"namespace": "shopfast", "source": "alert_labels"})
    )
    assert result.workload_match is False
    assert result.namespace == "shopfast"


def test_catalog_workload_still_counts_as_a_match() -> None:
    result = CorrelationAgent(_SETTINGS).correlate(
        _state(workload_context={"namespace": "shopfast", "pod_name": "p-1"})
    )
    assert result.workload_match is True


def test_catalog_service_name_wins_over_everything() -> None:
    result = CorrelationAgent(_SETTINGS).correlate(
        _state(
            service_context={"name": "catalog-name", "repository_url": "https://git/x/y"},
            workload_context={"service_name": "checkout-worker", "source": "alert_labels"},
        )
    )
    assert result.service_name == "catalog-name"
    assert result.repository_url == "https://git/x/y"


def test_repository_slug_folds_characters_github_disallows() -> None:
    assert _repository_slug("checkout worker") == "checkout-worker"
    assert _repository_slug("  Checkout   Worker  ") == "checkout-worker"
    assert _repository_slug("payments/api") == "payments-api"
    assert _repository_slug("svc_v2.1") == "svc_v2.1"
    assert _repository_slug("!!!") == ""
