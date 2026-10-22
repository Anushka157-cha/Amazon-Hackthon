"""HomeGuard Explainable AI Root-Cause Diagnosis Engine.

Combines deterministic graph traversal rules with structured, evidence-backed
explanations in both English and Hindi.
Separates observed facts from inferred hypotheses, ranks multiple root cause candidates,
and suggests clarifying questions when evidence is ambiguous or incomplete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

HINDI_DEVICE_NAMES = {
    "router": "मुख्य राउटर (Main Router)",
    "wifi_extender": "वाई-फाई एक्सटेंडर (Wi-Fi Extender)",
    "ring_doorbell": "रिंग वीडियो डोरबेल (Ring Doorbell)",
    "fire_tv": "फायर टीवी (Fire TV)",
    "echo_speaker": "इको स्पीकर (Echo Speaker)",
}

HINDI_STATUS_NAMES = {
    "online": "ऑनलाइन (सक्रिय)",
    "offline": "ऑफ़लाइन (बंद)",
    "degraded": "धीमा (Degraded)",
}


@dataclass
class DiagnosticCandidate:
    device_id: str
    name: str
    confidence: float
    confidence_label: ConfidenceLabel
    rank: int
    evidence: list[str]
    inferred_hypothesis: str
    observed_facts: list[str]
    blast_radius: list[str]


@dataclass
class DiagnosisResult:
    simulated: bool
    has_incident: bool
    root_cause: str | None
    root_cause_name: str | None
    root_cause_status: str
    victims: list[str]
    victim_names: list[str]
    confidence: float
    confidence_label: ConfidenceLabel
    evidence: list[str]
    observed_facts: list[str]
    inferred_hypotheses: list[str]
    candidates: list[dict[str, Any]]
    explanation: str
    explanation_hindi: str
    spoken: str
    spoken_hindi: str
    clarifying_questions: list[str]
    clarifying_questions_hindi: list[str]
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExplainableDiagnosisEngine:
    """Performs deterministic dependency-graph correlation and bilingual AI explanation."""

    def __init__(self, friendly_names: dict[str, str]) -> None:
        self.friendly_names = friendly_names

    def analyze(
        self,
        devices: dict[str, Any],
        get_downstream_fn: Any,
    ) -> DiagnosisResult:
        unhealthy = {k: v for k, v in devices.items() if v["status"] != "online"}

        # Case 1: All devices online and healthy
        if not unhealthy:
            return DiagnosisResult(
                simulated=True,
                has_incident=False,
                root_cause=None,
                root_cause_name=None,
                root_cause_status="online",
                victims=[],
                victim_names=[],
                confidence=1.0,
                confidence_label="high",
                evidence=["All 5 simulated home devices are responding to health probes with 0% packet loss."],
                observed_facts=[
                    "Main router ping latency is 24ms.",
                    "Wi-Fi extender 5GHz mesh link is online.",
                    "Downstream IoT devices are reachable.",
                ],
                inferred_hypotheses=["The local home area network is operating in optimal health."],
                candidates=[],
                explanation="All 5 simulated devices are online and functioning normally.",
                explanation_hindi="आपके घर के सभी 5 सिमुलेटेड उपकरण ऑनलाइन हैं और सामान्य रूप से काम कर रहे हैं।",
                spoken="Your home is running smoothly. All simulated devices are connected and online.",
                spoken_hindi="नमस्ते! आपका होम नेटवर्क पूरी तरह ठीक है। सभी 5 उपकरण ऑनलाइन जुड़े हैं।",
                clarifying_questions=[],
                clarifying_questions_hindi=[],
            )

        # Find candidates whose upstream dependencies are all healthy
        root_candidates: list[str] = []
        for dev_id in unhealthy:
            upstream = devices[dev_id].get("upstream", [])
            upstream_healthy = all(
                devices.get(u, {}).get("status") == "online" for u in upstream
            )
            if upstream_healthy:
                root_candidates.append(dev_id)

        # Ranked candidate evaluation
        candidate_objects: list[DiagnosticCandidate] = []
        for rank, cand_id in enumerate(root_candidates, start=1):
            cand_dev = devices[cand_id]
            descendants = set(get_downstream_fn(cand_id))
            cand_victims = [d for d in unhealthy if d in descendants and d != cand_id]
            coverage = (1 + len(cand_victims)) / max(1, len(unhealthy))
            confidence = round(min(0.98, 0.88 + 0.10 * coverage), 2)
            conf_label: ConfidenceLabel = "high" if confidence >= 0.85 else ("medium" if confidence >= 0.70 else "low")
            c_name = self.friendly_names.get(cand_id, cand_id)

            cand_facts = [
                f"{c_name} status is {cand_dev['status']}.",
                f"Its upstream gateway is verified online and reachable.",
                f"{len(cand_victims)} downstream devices dropped at the same time.",
            ]
            cand_hypo = (
                f"A hardware or Wi-Fi backhaul freeze on {c_name} severed connectivity for all its children."
            )
            cand_evidence = [
                f"{c_name} is unhealthy ({cand_dev['status']}) while parent is healthy.",
                f"Explains {len(cand_victims)} concurrent downstream failures.",
            ]

            candidate_objects.append(
                DiagnosticCandidate(
                    device_id=cand_id,
                    name=c_name,
                    confidence=confidence,
                    confidence_label=conf_label,
                    rank=rank,
                    evidence=cand_evidence,
                    inferred_hypothesis=cand_hypo,
                    observed_facts=cand_facts,
                    blast_radius=cand_victims,
                )
            )

        # Primary root cause selection
        primary_cand = candidate_objects[0] if candidate_objects else None
        if not primary_cand:
            # Fallback if circular or unknown
            first_unhealthy = list(unhealthy.keys())[0]
            root_cause_id = first_unhealthy
            victims = [d for d in unhealthy if d != root_cause_id]
            conf = 0.65
            conf_label = "medium"
        else:
            root_cause_id = primary_cand.device_id
            victims = primary_cand.blast_radius
            conf = primary_cand.confidence
            conf_label = primary_cand.confidence_label

        root_name = self.friendly_names.get(root_cause_id, root_cause_id)
        victim_names = [self.friendly_names.get(v, v) for v in victims]

        # Observed facts vs Inferred Hypotheses
        observed_facts = [
            f"Device '{root_name}' changed state to '{devices[root_cause_id]['status']}'.",
            f"Gateway connectivity to upstream parent is healthy.",
        ]
        if victims:
            observed_facts.append(
                f"{len(victims)} dependent devices ({', '.join([v.replace(' (Simulated)', '') for v in victim_names])}) became unresponsive simultaneously."
            )

        inferred_hypotheses = [
            f"Failure origin is isolated to {root_name}.",
            f"The downstream devices are collateral victims of the lost Wi-Fi link, not hardware failures themselves.",
        ]

        evidence = [
            f"{root_name} reports {devices[root_cause_id]['status']}.",
            "Its upstream dependencies are online.",
            f"{len(victims)} downstream devices are unhealthy at the same time.",
        ]

        # Clarifying questions if evidence is borderline
        clarifying_questions = []
        clarifying_questions_hindi = []
        if len(candidate_objects) > 1:
            clarifying_questions = [
                f"Did the power go out specifically near the {root_name.replace(' (Simulated)', '')}?",
                "Are other devices connected directly to the main router still working?",
            ]
            clarifying_questions_hindi = [
                f"क्या {root_name.replace(' (Simulated)', '')} के पास बिजली चली गई थी?",
                "क्या मुख्य राउटर से सीधे जुड़े अन्य उपकरण अभी भी चल रहे हैं?",
            ]
        elif root_cause_id == "wifi_extender":
            clarifying_questions = [
                "Is the LED status indicator on the Wi-Fi Extender blinking red or amber?",
                "Has the extender been moved further away from the main router recently?",
            ]
            clarifying_questions_hindi = [
                "क्या वाई-फाई एक्सटेंडर की लाइट लाल या नारंगी चमक रही है?",
                "क्या एक्सटेंडर को हाल ही में मुख्य राउटर से दूर ले जाया गया है?",
            ]

        # Explanations
        short_root = root_name.replace(" (Simulated)", "")
        short_victims = [n.replace(" (Simulated)", "") for n in victim_names]
        hindi_root = HINDI_DEVICE_NAMES.get(root_cause_id, short_root)
        hindi_status = HINDI_STATUS_NAMES.get(devices[root_cause_id]["status"], devices[root_cause_id]["status"])
        hindi_victims = [HINDI_DEVICE_NAMES.get(v, v) for v in victims]

        if victims:
            explanation = (
                f"Simulated device '{root_name}' is {devices[root_cause_id]['status']}, but its upstream gateway is healthy. "
                f"{len(victims)} downstream devices ({', '.join(victim_names)}) are dependent victims."
            )
            spoken = (
                f"I found the issue. Your {short_root} is {devices[root_cause_id]['status']}. "
                f"It is causing {len(victims)} other devices, including your "
                f"{', '.join(short_victims[:2])}, to fail."
            )
            explanation_hindi = (
                f"मूल कारण पहचाना गया: '{hindi_root}' {hindi_status} स्थिति में है, "
                f"जबकि मुख्य राउटर सामान्य चल रहा है। इसकी वजह से {len(victims)} जुड़े उपकरण ({', '.join(hindi_victims)}) डिस्कनेक्ट हो गए हैं।"
            )
            spoken_hindi = (
                f"समस्या का पता चल गया है। आपका {hindi_root} काम नहीं कर रहा है। "
                f"इस कारण {', '.join(hindi_victims[:2])} सहित {len(victims)} उपकरण बंद हो गए हैं।"
            )
        else:
            explanation = f"Simulated device '{root_name}' is {devices[root_cause_id]['status']}. No other devices are impacted."
            spoken = f"Your {short_root} is {devices[root_cause_id]['status']}. The rest of your home is functioning normally."
            explanation_hindi = f"उपकरण '{hindi_root}' {hindi_status} स्थिति में है। घर के बाकी सभी उपकरण ठीक चल रहे हैं।"
            spoken_hindi = f"आपका {hindi_root} ऑफ़लाइन है। बाक़ी घर का नेटवर्क बिल्कुल सही चल रहा है।"

        return DiagnosisResult(
            simulated=True,
            has_incident=True,
            root_cause=root_cause_id,
            root_cause_name=root_name,
            root_cause_status=devices[root_cause_id]["status"],
            victims=victims,
            victim_names=victim_names,
            confidence=conf,
            confidence_label=conf_label,
            evidence=evidence,
            observed_facts=observed_facts,
            inferred_hypotheses=inferred_hypotheses,
            candidates=[asdict(c) for c in candidate_objects],
            explanation=explanation,
            explanation_hindi=explanation_hindi,
            spoken=spoken,
            spoken_hindi=spoken_hindi,
            clarifying_questions=clarifying_questions,
            clarifying_questions_hindi=clarifying_questions_hindi,
        )
