from types import SimpleNamespace
from uuid import uuid4
from src.optimization.engine import evaluate
from src.optimization.routes import current_result
from tests.test_queue_optimization import snapshot, approach


def test_only_current_queue_epoch_and_frame_is_exposed():
    original=snapshot((approach("A","GA",34,.35,.6,50),approach("B","GB",6,.08,.5,20)))
    result=evaluate(original)
    state=SimpleNamespace(queue_intelligence=SimpleNamespace(latest=lambda _:original),
                          optimization=SimpleNamespace(latest=lambda _:result))
    assert current_result(state,original.source_id)==result
    state.queue_intelligence.latest=lambda _:None
    assert current_result(state,original.source_id) is None
    state.queue_intelligence.latest=lambda _:original.model_copy(update={"queue_epoch":uuid4()})
    assert current_result(state,original.source_id) is None
    state.queue_intelligence.latest=lambda _:original.model_copy(update={"frame_sequence":original.frame_sequence+1})
    assert current_result(state,original.source_id) is None
