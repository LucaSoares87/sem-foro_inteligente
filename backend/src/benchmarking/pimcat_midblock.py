"""RP-07 research-only advisory rule for a single-stage isolated midblock crossing.

No runtime import, timings, signal commands, or field controller integration.
Input states are synthetic or independently validated abstractions, not raw camera detections.
"""
from dataclasses import dataclass

from src.benchmarking.pimcat_local import PED_LIMIT, latch_request


@dataclass(frozen=True)
class Assessment:
    preference_in_simulation: str
    reason: str
    oldest_request: int | None
    remaining_seconds: int | None
    deadline_exceeded: bool
    origin: str = "synthetic"
    operational_decision: str = "abstain"
    physical_actuation: bool = False
    operationally_validated: bool = False


def assess(*, now: int, waiting: str, crossing: str, phase: str,
           topology_confirmed: bool, clearance_complete: bool,
           oldest_request: int | None = None, button: bool = False,
           all_prior_requests_admitted: bool = False,
           other_obligation: bool = False, pedestrian_limit: int = PED_LIMIT):
    """Classify a synthetic preference, never prescribe a phase duration.

    topology_confirmed means the modeled node is a single-stage midblock
    crossing and all conflicting vehicle movements are represented together.
    clearance_complete is independent evidence of completed required protection
    (or verified absence of any outstanding protection at initialization).
    waiting=empty must be positively established; unknown is not empty.
    all_prior_requests_admitted is independent service evidence, not absence
    of a detection. The caller must preserve request timestamps across samples.
    """
    if (type(now) is not int or now < 0 or type(pedestrian_limit) is not int
        or not 1 <= pedestrian_limit <= 600 or
        (oldest_request is not None and
         (type(oldest_request) is not int or not 0 <= oldest_request <= now))):
        raise ValueError("invalid research clock or request timestamp")
    if waiting not in ("empty", "demand", "unknown") or crossing not in ("clear", "occupied", "unknown"):
        raise ValueError("invalid observation state")
    if phase not in ("vehicle", "pedestrian", "transition", "unknown"):
        raise ValueError("invalid abstract phase")
    if any(type(value) is not bool for value in (
        topology_confirmed, clearance_complete, button,
        all_prior_requests_admitted, other_obligation)):
        raise ValueError("explicit boolean evidence required")

    # A completed request is cleared only with independent proof and confirmed
    # waiting-area emptiness during pedestrian service; a new call wins over reset.
    oldest = oldest_request
    if (all_prior_requests_admitted and topology_confirmed and phase == "pedestrian"
        and waiting == "empty" and not button):
        oldest = None
    oldest = latch_request(oldest, now, waiting, button)
    remaining = None if oldest is None else pedestrian_limit - (now - oldest)

    def result(preference, reason):
        return Assessment(preference, reason, oldest, remaining,
                          remaining is not None and remaining < 0)

    if not topology_confirmed:
        return result("abstain", "topology_unconfirmed")
    if crossing == "occupied" or not clearance_complete:
        return result("preserve_protection", "crossing_occupied_or_clearance_pending")
    if crossing == "unknown" or waiting == "unknown":
        return result("abstain", "observation_unknown")
    if phase in ("transition", "unknown") or other_obligation:
        return result("abstain", "other_constraint_or_phase_unknown")
    if oldest is not None:
        # A request requires assessment immediately. The caller must consider
        # protected opportunities before the deadline, not wait until zero.
        return result("evaluate_protected_service",
                      "deadline_due_or_exceeded" if remaining <= 0 else "request_pending")
    if waiting != "empty":
        return result("abstain", "inconsistent_request")
    if phase == "vehicle":
        return result("hold_vehicle_preference", "confirmed_no_pedestrian_demand")
    return result("evaluate_vehicle_return", "confirmed_empty_and_protection_complete")
