from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from openai import OpenAI
except Exception:  # optional dependency
    OpenAI = None


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEMORY_FILE = BASE_DIR / "incident_memory.json"


@dataclass
class IncidentState:
    incident_id: str
    site_id: str
    service: str
    severity: str
    symptoms: List[str]
    metrics: Dict[str, float]
    users_impacted: int
    status: str = "DETECTED"
    root_cause: str = ""
    confidence: float = 0.0
    actions: List[str] = field(default_factory=list)
    action_results: List[Dict[str, Any]] = field(default_factory=list)
    customer_message: str = ""
    validation: Dict[str, Any] = field(default_factory=dict)
    iterations: int = 0
    started_at: float = field(default_factory=time.time)


class ToolRegistry:
    """Simulated telecom tools. Safe for a hackathon demo; no real network is touched."""

    def __init__(self, state: IncidentState):
        self.state = state

    def get_network_snapshot(self) -> Dict[str, Any]:
        return {"site_id": self.state.site_id, **self.state.metrics}

    def get_customer_impact(self) -> Dict[str, Any]:
        severity_factor = {"CRITICAL": 1.0, "HIGH": 0.75, "MEDIUM": 0.4, "LOW": 0.1}[self.state.severity]
        return {
            "users_impacted": self.state.users_impacted,
            "estimated_sessions_at_risk": int(self.state.users_impacted * severity_factor),
            "service": self.state.service,
        }

    def execute_action(self, action: str) -> Dict[str, Any]:
        # Deliberately deterministic simulator so the demo is repeatable.
        before = dict(self.state.metrics)
        success = True
        note = ""

        if action == "reroute_backhaul":
            if self.state.metrics["backhaul_utilization_pct"] >= 90:
                self.state.metrics["backhaul_utilization_pct"] = 58
                self.state.metrics["packet_loss_pct"] = max(0.4, self.state.metrics["packet_loss_pct"] * 0.16)
                self.state.metrics["latency_ms"] = max(24, self.state.metrics["latency_ms"] * 0.23)
                note = "Traffic rerouted to an alternate backhaul path."
            else:
                success = False
                note = "Reroute not required by current telemetry."

        elif action == "restart_edge_router":
            # Recovery action is designed to work even when the first action fails.
            self.state.metrics["packet_loss_pct"] = max(0.2, self.state.metrics["packet_loss_pct"] * 0.08)
            self.state.metrics["latency_ms"] = max(22, self.state.metrics["latency_ms"] * 0.30)
            self.state.metrics["availability_pct"] = min(99.95, self.state.metrics["availability_pct"] + 12.8)
            note = "Edge router restart completed successfully."

        elif action == "scale_packet_core":
            self.state.metrics["core_utilization_pct"] = max(42, self.state.metrics["core_utilization_pct"] * 0.58)
            self.state.metrics["latency_ms"] = max(20, self.state.metrics["latency_ms"] * 0.42)
            note = "Packet-core capacity automatically scaled out."

        elif action == "refresh_service_profile":
            self.state.metrics["activation_success_pct"] = min(99.9, self.state.metrics["activation_success_pct"] + 10.0)
            self.state.metrics["api_error_rate_pct"] = max(0.3, self.state.metrics["api_error_rate_pct"] * 0.20)
            note = "Customer service profile refreshed and re-synchronised."

        elif action == "restart_otp_gateway":
            self.state.metrics["otp_success_pct"] = min(99.9, self.state.metrics["otp_success_pct"] + 20.0)
            self.state.metrics["api_error_rate_pct"] = max(0.2, self.state.metrics["api_error_rate_pct"] * 0.08)
            note = "OTP gateway restarted and health check passed."

        elif action == "rebalance_cell_load":
            self.state.metrics["cell_utilization_pct"] = max(62, self.state.metrics["cell_utilization_pct"] * 0.70)
            self.state.metrics["throughput_mbps"] = min(95, self.state.metrics["throughput_mbps"] * 2.4)
            self.state.metrics["latency_ms"] = max(25, self.state.metrics["latency_ms"] * 0.60)
            note = "Users rebalanced across adjacent cells."

        elif action == "notify_customer":
            note = "Proactive service message queued for impacted customers."

        else:
            success = False
            note = f"Action '{action}' is not on the approved playbook."

        result = {
            "action": action,
            "success": success,
            "note": note,
            "before": before,
            "after": dict(self.state.metrics),
            "timestamp": time.time(),
        }
        self.state.action_results.append(result)
        if success:
            self.state.actions.append(action)
        return result


class KnowledgeAgent:
    def __init__(self):
        self.documents = json.loads((DATA_DIR / "knowledge_base.json").read_text())

    def retrieve(self, state: IncidentState, top_k: int = 3) -> List[Dict[str, Any]]:
        query_terms = set(" ".join(state.symptoms + [state.service, state.root_cause]).lower().split())
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for doc in self.documents:
            text = (doc["title"] + " " + doc["symptoms"] + " " + doc["cause"]).lower()
            score = sum(1 for term in query_terms if term in text)
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scored[:top_k] if score > 0] or self.documents[:top_k]


class SignalMonitoringAgent:
    name = "Signal Monitoring Agent"

    def run(self, state: IncidentState) -> Dict[str, Any]:
        state.status = "CORRELATED"
        return {
            "agent": self.name,
            "finding": f"Telemetry anomaly detected at {state.site_id}",
            "signals": state.symptoms,
            "snapshot": dict(state.metrics),
        }


class CorrelationAgent:
    name = "Incident Correlation Agent"

    def run(self, state: IncidentState) -> Dict[str, Any]:
        m = state.metrics
        correlated = []
        if m.get("packet_loss_pct", 0) > 5 and m.get("latency_ms", 0) > 100:
            correlated.append("packet loss + latency spike")
        if m.get("availability_pct", 100) < 95:
            correlated.append("availability degradation")
        if m.get("backhaul_utilization_pct", 0) > 90:
            correlated.append("backhaul saturation")
        if m.get("cell_utilization_pct", 0) > 92:
            correlated.append("cell overload")
        if m.get("otp_success_pct", 100) < 92:
            correlated.append("OTP delivery degradation")
        if m.get("api_error_rate_pct", 0) > 5:
            correlated.append("API error surge")
        return {"agent": self.name, "correlated_signals": correlated, "correlation_count": len(correlated)}


class RootCauseAgent:
    name = "RCA + Knowledge Agent"

    def __init__(self, knowledge: KnowledgeAgent):
        self.knowledge = knowledge

    def run(self, state: IncidentState) -> Dict[str, Any]:
        m = state.metrics
        if m.get("backhaul_utilization_pct", 0) > 90 and m.get("packet_loss_pct", 0) > 5:
            cause = "Backhaul congestion causing packet loss and latency degradation"
            conf = 0.96
        elif m.get("cell_utilization_pct", 0) > 92 and m.get("throughput_mbps", 100) < 40:
            cause = "Cell overload causing throughput collapse"
            conf = 0.92
        elif m.get("core_utilization_pct", 0) > 94 and m.get("latency_ms", 0) > 120:
            cause = "Packet-core capacity saturation"
            conf = 0.94
        elif m.get("otp_success_pct", 100) < 92 and m.get("api_error_rate_pct", 0) > 5:
            cause = "OTP gateway instability"
            conf = 0.95
        elif m.get("activation_success_pct", 100) < 90 and m.get("api_error_rate_pct", 0) > 5:
            cause = "Service-provisioning profile synchronisation failure"
            conf = 0.93
        else:
            cause = "Unknown multi-factor telecom degradation"
            conf = 0.62

        state.root_cause = cause
        state.confidence = conf
        evidence = self.knowledge.retrieve(state)
        return {
            "agent": self.name,
            "root_cause": cause,
            "confidence": conf,
            "evidence": evidence,
        }


class CustomerImpactAgent:
    name = "Customer Impact Agent"

    def run(self, state: IncidentState, tools: ToolRegistry) -> Dict[str, Any]:
        impact = tools.get_customer_impact()
        state.customer_message = (
            f"We detected a {state.service} service issue affecting approximately "
            f"{impact['users_impacted']:,} users in {state.site_id}. Automated recovery is in progress."
        )
        return {"agent": self.name, **impact, "message": state.customer_message}


class DecisionAgent:
    name = "Autonomous Decision & Remediation Agent"

    def plan(self, state: IncidentState) -> List[str]:
        m = state.metrics
        if "Backhaul congestion" in state.root_cause:
            return ["reroute_backhaul", "restart_edge_router", "notify_customer"]
        if "Cell overload" in state.root_cause:
            return ["rebalance_cell_load", "notify_customer"]
        if "Packet-core capacity" in state.root_cause:
            return ["scale_packet_core", "notify_customer"]
        if "OTP gateway" in state.root_cause:
            return ["restart_otp_gateway", "notify_customer"]
        if "Service-provisioning" in state.root_cause:
            return ["refresh_service_profile", "notify_customer"]
        return ["notify_customer"]


class ValidationAgent:
    name = "Recovery Validation Agent"

    def run(self, state: IncidentState) -> Dict[str, Any]:
        m = state.metrics
        checks: Dict[str, bool] = {}

        # Validate only KPIs relevant to the diagnosed failure domain.
        if "Backhaul congestion" in state.root_cause:
            checks = {
                "packet_loss_ok": m.get("packet_loss_pct", 0) <= 3,
                "latency_ok": m.get("latency_ms", 0) <= 60,
                "availability_ok": m.get("availability_pct", 100) >= 98,
                "backhaul_utilization_ok": m.get("backhaul_utilization_pct", 0) <= 85,
            }
        elif "Cell overload" in state.root_cause:
            checks = {
                "cell_utilization_ok": m.get("cell_utilization_pct", 0) <= 90,
                "throughput_ok": m.get("throughput_mbps", 0) >= 70,
                "latency_ok": m.get("latency_ms", 0) <= 80,
            }
        elif "Packet-core capacity" in state.root_cause:
            checks = {
                "core_utilization_ok": m.get("core_utilization_pct", 0) <= 90,
                "latency_ok": m.get("latency_ms", 0) <= 80,
            }
        elif "OTP gateway" in state.root_cause:
            checks = {
                "otp_success_ok": m.get("otp_success_pct", 100) >= 97,
                "api_error_ok": m.get("api_error_rate_pct", 0) <= 2,
            }
        elif "Service-provisioning" in state.root_cause:
            checks = {
                "activation_ok": m.get("activation_success_pct", 100) >= 97,
                "api_error_ok": m.get("api_error_rate_pct", 0) <= 2,
            }
        else:
            checks = {
                "availability_ok": m.get("availability_pct", 100) >= 98,
                "latency_ok": m.get("latency_ms", 0) <= 80,
            }

        recovered = all(checks.values())
        state.validation = {"recovered": recovered, "checks": checks, "final_metrics": dict(m)}
        state.status = "RESOLVED" if recovered else "REMEDIATION_REQUIRED"
        return {"agent": self.name, **state.validation}


class AutonomousTelcoOrchestrator:
    """Coordinates agents, executes approved actions, validates recovery, and retries autonomously."""

    def __init__(self, llm_enabled: bool | None = None):
        self.knowledge = KnowledgeAgent()
        self.monitor = SignalMonitoringAgent()
        self.correlation = CorrelationAgent()
        self.rca = RootCauseAgent(self.knowledge)
        self.impact = CustomerImpactAgent()
        self.decision = DecisionAgent()
        self.validator = ValidationAgent()
        self.llm_enabled = bool(os.getenv("OPENAI_API_KEY")) if llm_enabled is None else llm_enabled
        self.llm_client = OpenAI() if (self.llm_enabled and OpenAI is not None and os.getenv("OPENAI_API_KEY")) else None

    def _llm_summary(self, state: IncidentState) -> str:
        if not self.llm_client:
            return (
                f"Autonomous resolution completed for {state.site_id}. Root cause: {state.root_cause}. "
                f"Actions: {', '.join(state.actions)}. Recovery status: {state.status}."
            )
        prompt = {
            "incident": state.incident_id,
            "service": state.service,
            "site": state.site_id,
            "root_cause": state.root_cause,
            "confidence": state.confidence,
            "actions": state.actions,
            "validation": state.validation,
        }
        try:
            response = self.llm_client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
                input=[
                    {"role": "system", "content": "Summarize an already executed telecom incident workflow. Do not invent facts."},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
            )
            return response.output_text.strip()
        except Exception:
            return (
                f"Autonomous resolution completed for {state.site_id}. Root cause: {state.root_cause}. "
                f"Actions: {', '.join(state.actions)}. Recovery status: {state.status}."
            )

    def run(self, raw_incident: Dict[str, Any], max_iterations: int = 4) -> Dict[str, Any]:
        state = IncidentState(
            incident_id=raw_incident["incident_id"],
            site_id=raw_incident["site_id"],
            service=raw_incident["service"],
            severity=raw_incident["severity"],
            symptoms=raw_incident["symptoms"],
            metrics=dict(raw_incident["metrics"]),
            users_impacted=raw_incident["users_impacted"],
        )
        tools = ToolRegistry(state)
        trace: List[Dict[str, Any]] = []

        trace.append(self.monitor.run(state))
        trace.append(self.correlation.run(state))
        trace.append(self.rca.run(state))
        trace.append(self.impact.run(state, tools))

        plan = self.decision.plan(state)
        trace.append({"agent": self.decision.name, "planned_actions": plan})

        action_cursor = 0
        while state.iterations < max_iterations and not state.validation.get("recovered", False):
            state.iterations += 1
            if action_cursor >= len(plan):
                break
            action = plan[action_cursor]
            action_cursor += 1

            # Guardrail: autonomous actions are only drawn from a fixed playbook.
            approved = {
                "reroute_backhaul", "restart_edge_router", "scale_packet_core",
                "refresh_service_profile", "restart_otp_gateway", "rebalance_cell_load",
                "notify_customer",
            }
            if action not in approved:
                trace.append({"agent": "Guardrail", "blocked_action": action})
                continue

            trace.append({"agent": "Action Executor", "result": tools.execute_action(action)})
            trace.append(self.validator.run(state))

            if state.status == "RESOLVED":
                break

        # One autonomous re-plan pass if recovery did not pass.
        if state.status != "RESOLVED" and state.iterations < max_iterations:
            if "restart_edge_router" not in state.actions:
                fallback_action = "restart_edge_router"
                if "OTP gateway" in state.root_cause:
                    fallback_action = "restart_otp_gateway"
                trace.append({"agent": "Autonomous Re-planner", "decision": f"Executing fallback recovery action: {fallback_action}"})
                trace.append({"agent": "Action Executor", "result": tools.execute_action(fallback_action)})
                trace.append(self.validator.run(state))

        if state.status != "RESOLVED":
            state.status = "ESCALATED"

        summary = self._llm_summary(state)
        result = {
            "incident": asdict(state),
            "trace": trace,
            "summary": summary,
            "autonomy": {
                "human_intervention_required": False,
                "tools_used": sorted({x.get("agent") for x in trace if x.get("agent")} ),
                "guardrail_active": True,
                "simulation_only": True,
            },
        }
        self._save_memory(result)
        return result

    def _save_memory(self, result: Dict[str, Any]) -> None:
        existing: List[Dict[str, Any]] = []
        if MEMORY_FILE.exists():
            try:
                existing = json.loads(MEMORY_FILE.read_text())
            except Exception:
                existing = []
        existing.append(result)
        MEMORY_FILE.write_text(json.dumps(existing[-50:], indent=2))


def load_incidents() -> List[Dict[str, Any]]:
    return json.loads((DATA_DIR / "telecom_incidents.json").read_text())


def run_demo(incident_id: str = "INC-1001") -> Dict[str, Any]:
    incidents = load_incidents()
    incident = next(item for item in incidents if item["incident_id"] == incident_id)
    return AutonomousTelcoOrchestrator().run(incident)


if __name__ == "__main__":
    result = run_demo()
    inc = result["incident"]
    print("=" * 80)
    print("TELCO AUTONOMOUS RESOLVE-X")
    print("=" * 80)
    print(result["summary"])
    print(f"Status: {inc['status']}")
    print(f"Root cause: {inc['root_cause']} ({inc['confidence']:.0%})")
    print(f"Actions executed: {', '.join(inc['actions'])}")
    print(f"Validation recovered: {inc['validation'].get('recovered')}")
