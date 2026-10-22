"""HomeGuard Voice-First Assistant Engine.

Supports voice and conversational troubleshooting in plain English and Hindi (हिंदी).
Parses natural language speech transcripts, tracks conversation context,
answers follow-up questions, and generates spoken voice responses.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

LanguageType = Literal["en", "hi"]


@dataclass
class ChatMessage:
    id: str
    role: Literal["user", "assistant", "system"]
    text: str
    language: LanguageType
    intent: str | None = None
    structured_data: dict[str, Any] | None = None
    spoken_audio_url: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class VoiceAssistant:
    """Conversational assistant supporting Hindi and English smart home troubleshooting."""

    def __init__(self) -> None:
        self.history: list[ChatMessage] = []

    def detect_language(self, text: str) -> LanguageType:
        # Check Devanagari script unicode range
        if re.search(r"[\u0900-\u097F]", text):
            return "hi"
        hindi_keywords = ["kya", "theek", "hua", "hai", "karo", "nahi", "haan", "samashya", "namaste"]
        words = text.lower().split()
        if any(w in hindi_keywords for w in words):
            return "hi"
        return "en"

    def parse_intent(self, text: str) -> str:
        t = text.lower().strip()
        words = set(re.findall(r"\w+", t))

        # Confirmation intents
        confirm_phrases = ["go ahead", "restart it", "do it", "theek hai", "karo", "करो", "रीस्टार्ट"]
        confirm_words = {"yes", "approve", "confirm", "proceed", "haan", "ha", "हाँ", "हां", "करो"}
        if any(p in t for p in confirm_phrases) or any(w in words for w in confirm_words):
            return "APPROVE_FIX"

        # Cancellation intents
        cancel_phrases = ["ruk jao", "rehne do", "don't", "dont", "रहने दो", "मत करो"]
        cancel_words = {"no", "cancel", "stop", "abort", "nahi", "नहीं", "ना"}
        if any(p in t for p in cancel_phrases) or any(w in words for w in cancel_words):
            return "CANCEL_FIX"

        # Rollback intents
        rollback_phrases = ["pehle jaisa", "undo that", "पहले जैसा", "वापस करो"]
        rollback_words = {"rollback", "undo", "revert", "restore", "wapas", "वापस"}
        if any(p in t for p in rollback_phrases) or any(w in words for w in rollback_words):
            return "ROLLBACK_FIX"

        # Question / Explanation intents
        why_phrases = ["why", "explain", "reason", "kyun", "kaise", "क्यों", "कैसे", "कारण"]
        if any(p in t for p in why_phrases):
            return "EXPLAIN_REASON"

        # Diagnosis / Status intents
        diag_phrases = ["kya hua", "what's wrong", "what is wrong", "what is happening", "क्या हुआ", "क्या समस्या है"]
        diag_words = {"check", "status", "wrong", "problem", "issue", "diagnose", "dekho", "network", "जांच", "स्थिति"}
        if any(p in t for p in diag_phrases) or any(w in words for w in diag_words):
            return "DIAGNOSE_HOME"

        return "GENERAL_QUERY"

    def add_message(
        self,
        role: Literal["user", "assistant", "system"],
        text: str,
        language: LanguageType = "en",
        intent: str | None = None,
        structured_data: dict[str, Any] | None = None,
    ) -> ChatMessage:
        import uuid
        msg = ChatMessage(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            role=role,
            text=text,
            language=language,
            intent=intent,
            structured_data=structured_data,
        )
        self.history.append(msg)
        return msg

    def get_contextual_response(
        self,
        user_text: str,
        diagnosis_data: dict[str, Any],
        proposal_data: dict[str, Any] | None = None,
        language: LanguageType | None = None,
    ) -> tuple[str, str, str]:
        """Generate response text and spoken string in requested language.
        
        Returns: (intent, display_text, spoken_text)
        """
        detected_lang = language or self.detect_language(user_text)
        intent = self.parse_intent(user_text)

        has_incident = diagnosis_data.get("has_incident", False)
        root_name = diagnosis_data.get("root_cause_name", "Device")
        clean_root = root_name.replace(" (Simulated)", "") if root_name else "Device"
        victims = diagnosis_data.get("victim_names", [])
        clean_victims = [v.replace(" (Simulated)", "") for v in victims]

        if intent == "APPROVE_FIX":
            if detected_lang == "hi":
                text = f"मैंने {clean_root} को रीस्टार्ट करने की प्रक्रिया शुरू कर दी है। कृपया स्थिरता जांच पूरी होने तक प्रतीक्षा करें।"
                spoken = f"ठीक है, मैं {clean_root} को रीस्टार्ट कर रहा हूँ।"
            else:
                text = f"Authorized: Initiating safe restart of {clean_root}. Running 3-tick stabilization verification..."
                spoken = f"Restarting your {clean_root} now. Please wait while I verify all devices recover."
            return intent, text, spoken

        if intent == "CANCEL_FIX":
            if detected_lang == "hi":
                text = "मरम्मत रद्द कर दी गई है। कोई भी बदलाव नहीं किया गया है।"
                spoken = "ठीक है, मैंने रीस्टार्ट रद्द कर दिया है। कुछ भी नहीं बदला गया।"
            else:
                text = "Fix proposal cancelled. No changes were applied to your home network."
                spoken = "Understood. I have cancelled the restart. All settings remain unchanged."
            return intent, text, spoken

        if intent == "ROLLBACK_FIX":
            if detected_lang == "hi":
                text = "पूर्व स्थिति पुनर्स्थापित की जा रही है (Rollback)।"
                spoken = "मैं आपके उपकरणों को पिछली स्थिति में वापस ला रहा हूँ।"
            else:
                text = "Reverting network state to pre-fix snapshot..."
                spoken = "Rolling back changes now and restoring previous device configurations."
            return intent, text, spoken

        if intent == "EXPLAIN_REASON":
            if not has_incident:
                if detected_lang == "hi":
                    text = "आपके घर का नेटवर्क पूरी तरह ठीक है। कोई खराबी नहीं मिली है।"
                    spoken = "सब कुछ सामान्य रूप से काम कर रहा है।"
                else:
                    text = "All devices are currently healthy and responding within normal latency thresholds."
                    spoken = "All 5 devices in your home are online and functioning normally."
                return intent, text, spoken

            if detected_lang == "hi":
                text = (
                    f"कारण विश्लेषण: {clean_root} ऑफ़लाइन हो गया है। क्योंकि {', '.join(clean_victims[:2])} "
                    f"इंटरनेट के लिए {clean_root} पर निर्भर हैं, वे भी बंद हो गए। मुख्य गेटवे सामान्य चल रहा है।"
                )
                spoken = f"{clean_root} के बंद होने के कारण उससे जुड़े उपकरण भी बंद हो गए हैं।"
            else:
                text = (
                    f"Root-cause analysis: {clean_root} stopped responding, but its upstream router is healthy. "
                    f"Because {', '.join(clean_victims[:2])} route through {clean_root}, they lost connectivity simultaneously."
                )
                spoken = f"Your {clean_root} failed, cutting off network access for its connected downstream devices."
            return intent, text, spoken

        # Default / DIAGNOSE_HOME
        if not has_incident:
            if detected_lang == "hi":
                text = "आपके सभी 5 स्मार्ट उपकरण ऑनलाइन हैं और सामान्य गति से काम कर रहे हैं।"
                spoken = "नमस्ते! आपका होम नेटवर्क पूरी तरह ठीक है। सभी उपकरण ऑनलाइन जुड़े हैं।"
            else:
                text = "All 5 simulated devices are online and working normally."
                spoken = "Your home is running smoothly. All simulated devices are connected and online."
            return intent, text, spoken

        if detected_lang == "hi":
            text = (
                f"समस्या मिली: आपका {clean_root} ऑफ़लाइन है। "
                f"इसके कारण {len(clean_victims)} उपकरण ({', '.join(clean_victims[:2])}) भी बंद हैं। "
                "क्या आप चाहते हैं कि मैं इसे सुरक्षित रूप से रीस्टार्ट करूँ?"
            )
            spoken = (
                f"समस्या का पता चल गया है। आपका {clean_root} काम नहीं कर रहा है। "
                f"इस कारण {', '.join(clean_victims[:2])} भी बंद हैं। क्या मैं इसे रीस्टार्ट करूँ?"
            )
        else:
            text = (
                f"Issue identified: Your {clean_root} is offline, causing {len(clean_victims)} downstream devices "
                f"({', '.join(clean_victims[:2])}) to drop. I recommend restarting it. Would you like me to proceed?"
            )
            spoken = (
                f"I found the issue. Your {clean_root} is offline. "
                f"It is causing {len(clean_victims)} other devices to fail. Should I go ahead with the restart?"
            )

        return intent, text, spoken
