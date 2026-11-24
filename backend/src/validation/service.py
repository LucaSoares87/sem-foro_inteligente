from src.validation.contracts import PILOT_REQUIRED

GATES=(
    ("synthetic_demo_dataset","not_run","Vídeos de demonstração serão adicionados posteriormente."),
    ("authorized_model","blocked","Modelo candidato ainda exige evidência métrica autorizada."),
    ("physical_camera","blocked","Captura física autorizada ainda exige evidência de campo."),
    ("calibration","blocked","Calibração deve ser executada no cruzamento real."),
    ("field_ground_truth","blocked","Ground truth real ainda não foi fornecido."),
    ("hardware_benchmark","not_run","Benchmark deve ser executado no hardware-alvo."),
    ("recovery_drill","not_run","Recovery deve ser repetido no hardware-alvo."),
    ("human_acceptance","pending_human","Aceite humano não pode ser automatizado."),
)

class ValidationService:
    def __init__(self,video,vision,evidence=(),error=None):
        self.video=video
        self.vision=vision
        self.evidence={item.gate:item for item in evidence}
        self.error=error

    def _runtime(self):
        vision=self.vision.status()
        physical=[session for session in self.video.sessions.values()
                  if session.spec.kind in {"webcam","rtsp"}]
        return {
            "authorized_candidate_model_loaded": bool(vision.get("configured") and vision.get("purpose")=="authorized_candidate"),
            "physical_sources_configured": len(physical),
            "physical_sources_running": sum(1 for session in physical if session.state=="running"),
        }

    def health_status(self):
        status=self.status()
        return {
            "state":status["state"],
            "framework_ready":status["framework_ready"],
            "pilot_ready":status["pilot_ready"],
            "pilot_decision":status["pilot_decision"],
            "missing_evidence_count":len(status["missing_evidence"]),
            "physical_actuation":False,
            "operational_decision":"abstain",
        }

    def status(self):
        runtime=self._runtime()
        gates=[]
        for gate,default_state,default_note in GATES:
            evidence=self.evidence.get(gate)
            if evidence:
                state=evidence.state
                note=evidence.note or default_note
                item={
                    "gate":gate,"state":state,"origin":evidence.origin,
                    "reference":evidence.reference,"artifact_sha256":evidence.artifact_sha256,
                    "executed_at":evidence.executed_at.isoformat() if evidence.executed_at else None,
                    "note":note,
                }
            else:
                item={"gate":gate,"state":default_state,"origin":None,"reference":None,
                      "artifact_sha256":None,"executed_at":None,"note":default_note}
            gates.append(item)
        ready={item["gate"] for item in gates if item["state"]=="ready"}
        missing=sorted(PILOT_REQUIRED-ready)
        return {
            "state":"error" if self.error else "available",
            "framework_ready":self.error is None,
            "pilot_ready":self.error is None and not missing,
            "pilot_decision":"ready_for_supervised_pilot" if self.error is None and not missing else "blocked_by_field_evidence",
            "missing_evidence":missing,
            "runtime_observation":runtime,
            "gates":gates,
            "error_code":self.error,
            "physical_actuation":False,
            "operational_decision":"abstain",
        }
