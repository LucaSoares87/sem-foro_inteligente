from dataclasses import asdict

import pytest

from src.benchmarking.pimcat_midblock import assess


def sample(**updates):
    inputs = dict(now=0, waiting="empty", crossing="clear", phase="vehicle",
                  topology_confirmed=True, clearance_complete=True)
    inputs.update(updates)
    r = assess(**inputs)
    assert r.origin == "synthetic" and r.operational_decision == "abstain"
    assert r.physical_actuation is False and r.operationally_validated is False
    return r


def test_no_periodic_interruption_with_confirmed_empty_crossing_for_24_hours():
    for t in range(86400):
        r = sample(now=t)
        assert r.preference_in_simulation == "hold_vehicle_preference"
        assert r.oldest_request is None and r.remaining_seconds is None


@pytest.mark.parametrize("source", ["camera", "button"])
def test_one_request_is_sufficient_without_waiting_for_group(source):
    r = sample(now=86500, waiting="demand" if source == "camera" else "empty",
               button=source == "button")
    assert r.preference_in_simulation == "evaluate_protected_service"
    assert r.oldest_request == 86500 and r.remaining_seconds == 120


def test_new_arrivals_and_missing_detection_do_not_reset_deadline():
    r = sample(now=10, waiting="demand")
    for t in (40, 80, 130, 131):
        r = sample(now=t, oldest_request=r.oldest_request,
                   waiting="unknown" if t == 80 else "demand")
        assert r.oldest_request == 10
        assert r.remaining_seconds == 130 - t
    assert r.deadline_exceeded
    assert r.reason == "deadline_due_or_exceeded"
    assert sample(now=90, oldest_request=10, waiting="empty").preference_in_simulation == "evaluate_protected_service"


@pytest.mark.parametrize("updates", [
    {"waiting": "unknown"}, {"crossing": "unknown"}, {"phase": "unknown"},
    {"phase": "transition"}, {"topology_confirmed": False}, {"other_obligation": True},
])
def test_unknown_or_other_obligation_never_infers_green(updates):
    assert sample(**updates).preference_in_simulation == "abstain"


def test_occupied_or_incomplete_clearance_blocks_vehicle_preference():
    for phase in ("vehicle", "pedestrian", "transition"):
        assert sample(phase=phase, crossing="occupied").preference_in_simulation == "preserve_protection"
        assert sample(phase=phase, clearance_complete=False).preference_in_simulation == "preserve_protection"
    r = sample(now=200, oldest_request=0, crossing="occupied")
    assert r.deadline_exceeded and r.preference_in_simulation == "preserve_protection"


def test_return_requires_independent_admission_and_clearance():
    r = sample(now=40, phase="pedestrian", oldest_request=10, clearance_complete=False,
               all_prior_requests_admitted=True, crossing="occupied")
    assert r.oldest_request is None
    assert r.preference_in_simulation == "preserve_protection"
    assert sample(now=41, phase="pedestrian", crossing="unknown").preference_in_simulation == "abstain"
    assert sample(now=42, phase="pedestrian").preference_in_simulation == "evaluate_vehicle_return"
    assert sample(now=42, phase="pedestrian", oldest_request=10).preference_in_simulation == "evaluate_protected_service"
    assert sample(now=42, phase="vehicle", oldest_request=10,
                  all_prior_requests_admitted=True).oldest_request == 10
    assert sample(now=42, phase="pedestrian", oldest_request=10,
                  all_prior_requests_admitted=True, button=True).oldest_request == 10


def test_configurable_experimental_limit_and_determinism():
    a = sample(now=61, oldest_request=1, pedestrian_limit=60)
    assert a.remaining_seconds == 0 and not a.deadline_exceeded
    assert asdict(a) == asdict(sample(now=61, oldest_request=1, pedestrian_limit=60))
    for updates in ({"now": -1}, {"oldest_request": 1}, {"pedestrian_limit": 0},
                    {"waiting": "not_known"}, {"clearance_complete": None}):
        with pytest.raises(ValueError):
            sample(**updates)
