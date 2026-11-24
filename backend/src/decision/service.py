from src.decision.contracts import CycleDemand,SimulationScenario

PRESETS=("balanced","asymmetric","surge","overload","empty")

def scenario_for(preset):
    profiles={
        "balanced":[(30,30)]*8,
        "asymmetric":[(75,8)]*8,
        "surge":[(20,20)]*3+[(15,85)]*4+[(20,20)]*3,
        "overload":[(110,110)]*8,
        "empty":[(0,0)]*4,
    }
    return SimulationScenario(cycles=tuple(CycleDemand(a=a,b=b) for a,b in profiles[preset]))

def status():
    return {"state":"simulation_available","origin":"synthetic","physical_actuation":False,
            "operationally_validated":False,"operational_decision":"abstain",
            "presets":list(PRESETS),"live_input_used_for_simulation":False}

def eligibility(analytics,history,source):
    snapshot=analytics.latest(source)
    reason="visual_data_not_operationally_validated" if snapshot is not None else "no_current_analytics"
    return {"source_id":source,"state":"abstain","reason":reason,
            "operationally_validated":False,"physical_actuation":False,
            "snapshot_available":snapshot is not None,
            "purpose":snapshot.purpose if snapshot is not None else None,
            "analytics_epoch":str(snapshot.analytics_epoch) if snapshot is not None else None,
            "history_state":history.status()["state"],
            "missing_evidence":["calibrated_arrival_demand","validated_detector_and_counts",
                "approved_intersection_geometry_and_conflicts","calibrated_queue_state_and_storage",
                "validated_dynamic_x_cost_weights","pedestrian_and_clearance_study",
                "independent_traffic_engineering_review"]}
