import itertools
import os
import pytest

from src.benchmarking import pimcat_h2_gap as h2
from src.benchmarking import pimcat_i1a_advance_only as i1


def test_advance_only_exhaustive_counterfactual_states():
    changes = 0
    for kind, age, t, qa, qb, wa, wb, waiting, pw, bound in itertools.product(
        ("mid", "cross"), (5, 12, 45), (100, 101), (0, 1, 20), (0, 1),
        (0, 160), (0, 160), (0, 1, 5), (0, 99, 100),
        (None, float("nan"), -1, 0, 42, 43, 60),
    ):
        if kind == "mid" and (qb or wb):
            continue
        for phase in (("A",) if kind == "mid" else ("A", "B")):
            args = (kind, phase, age, t, [qa, qb], [wa, wb], waiting,
                    t-pw if waiting else None, (.1, .05, .04), 20, bound)
            base = h2.choose("compatible", *args)
            got = i1.choose(i1.CANDIDATE, *args)
            if got != base:
                changes += 1
                assert base == ("A", "await_compatible") and phase == "A"
                assert got == (("P" if kind == "mid" else "BP"), "gap_candidate")
                assert waiting and pw < 100 and max(wa, wb) < 160
                assert age >= 12 and t % 5 == 0 and bound >= 43
            assert got[1] != "gap_defer"
    assert changes > 0


def test_explicit_service_is_never_deferred_and_unknown_returns_baseline():
    args = ("mid", "A", 20, 20, [0, 0], [0, 0], 1, 0, (.1, 0, .04), 20)
    assert h2.choose("gap_guarded", *args, 4) == ("A", "gap_defer")
    assert i1.choose(i1.CANDIDATE, *args, 4) == ("P", "low_conflicting_demand")
    for bound in (None, float("nan"), -1, 0):
        assert i1.choose(i1.CANDIDATE, *args, bound) == h2.choose("compatible", *args, bound)
    args = ("mid", "A", 20, 20, [1, 0], [0, 0], 1, 0, (.1, 0, .04), 20)
    assert i1.choose(i1.CANDIDATE, *args, 43) == ("P", "gap_candidate")
    assert i1.choose(i1.CANDIDATE, *args, 42) == h2.choose("compatible", *args, 42)


@pytest.mark.skipif(os.environ.get("PIMCAT_I1A_SUMO_REQUIRED") != "1", reason="pinned microscopic CI only")
@pytest.mark.parametrize("family", ["mid_sparse", "cross_deadlines"])
def test_real_sumo_repeatability_and_original_default_parity(tmp_path, family):
    api = h2.ensure_version()
    seed = i1.SEEDS[0]
    default = h2.case(api, tmp_path / family, family, seed, h2.POLICIES)
    injected = h2.case(api, tmp_path / family, family, seed, h2.POLICIES, choose_fn=h2.choose)
    assert default == injected
    a = h2.case(api, tmp_path / family, family, seed, i1.POLICIES, choose_fn=i1.choose)
    b = h2.case(api, tmp_path / family, family, seed, i1.POLICIES, choose_fn=i1.choose)
    assert a == b
    for p in h2.POLICIES:
        assert a["metrics"][p] == default["metrics"][p]
    m = a["metrics"][i1.CANDIDATE]
    assert m["gap_deferred"] == m["red_entries"] == m["conflict_violations"] == 0
    assert m["vehicles_scheduled"] == m["vehicles_exited"] + m["vehicles_remaining"] + m["vehicles_uninserted"]
    assert m["pedestrians_scheduled"] == m["pedestrians_exited"] + m["pedestrians_remaining"] + m["pedestrians_uninserted"]
