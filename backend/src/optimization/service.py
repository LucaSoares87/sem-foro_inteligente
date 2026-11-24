from src.optimization.engine import evaluate

class OptimizationService:
    def __init__(self):
        self.results={}
        self.failed=0

    def consume(self,snapshot):
        try:
            result=evaluate(snapshot)
            self.results[snapshot.source_id]=result
            return result
        except Exception:
            self.results.pop(snapshot.source_id,None)
            self.failed+=1
            return None

    def clear(self):
        self.results.clear()

    def latest(self,source):
        return self.results.get(source)

    def status(self):
        results=[value.model_dump(mode="json") for _,value in sorted(self.results.items())]
        return {"state":"available" if results else "idle","algorithm":"dynamic_clear_first_v1",
                "cost_model":"continuity_queue_cost_v1","failed":self.failed,"sources":results,
                "engineering_weights_validated":False,"operationally_validated":False,
                "physical_actuation":False,"operational_decision":"abstain"}

    def health_status(self):
        return {"state":"available" if self.results else "idle","algorithm":"dynamic_clear_first_v1",
                "failed":self.failed,"engineering_weights_validated":False,
                "operationally_validated":False,"physical_actuation":False,
                "operational_decision":"abstain"}
