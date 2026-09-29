"""Self-Healing Semantic DOM Resolver for V.O.I.D.E.

Ported from Alex Browser v2 (arc-telemetry) on-device runtime.
Implements:
- 8-Signal Weighted Scoring:
    - Semantic (0.22)
    - Context (0.18)
    - Role & Accessibility (0.15)
    - Structure (0.14)
    - Historical Fingerprint (0.11)
    - Selector (0.10)
    - State / Visibility (0.05)
    - Geometry (0.05)
- Ambiguity Margin Detector (Δ < 0.05 flags AMBIGUOUS)
- Health Status Lifecycle (HEALTHY, RECOVERED, DEGRADED, AMBIGUOUS)
- Explainable Resolution Telemetry
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional


class ConfidenceBand:
    EXACT = "EXACT"         # >= 0.95
    STRONG = "STRONG"       # 0.80 - 0.94
    RECOVERED = "RECOVERED" # 0.65 - 0.79
    AMBIGUOUS = "AMBIGUOUS" # Delta < 0.05 between top candidates
    WEAK = "WEAK"           # 0.40 - 0.64
    UNRESOLVED = "UNRESOLVED" # < 0.40

    # Backward compatibility aliases
    HIGH = "STRONG"
    PROBABLE = "RECOVERED"
    UNCERTAIN = "WEAK"
    REJECT = "UNRESOLVED"


class MappingHealthStatus:
    HEALTHY = "HEALTHY"
    RECOVERED = "RECOVERED"
    DEGRADED = "DEGRADED"
    AMBIGUOUS = "AMBIGUOUS"


class ScoredCandidate:
    def __init__(
        self,
        element: Dict[str, Any],
        score: float,
        confidence_band: str,
        signals: Dict[str, float],
        health: str = MappingHealthStatus.HEALTHY,
        explanation: str = "",
    ) -> None:
        self.element: Dict[str, Any] = element
        self.score: float = round(score, 4)
        self.confidence_band: str = confidence_band
        self.signals: Dict[str, float] = signals
        self.health: str = health
        self.explanation: str = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element": self.element,
            "score": self.score,
            "confidence_band": self.confidence_band,
            "signals": self.signals,
            "health": self.health,
            "explanation": self.explanation,
        }


class SemanticResolver:
    """Multi-signal semantic element scorer with Alex Browser v2 8-signal architecture."""

    # 8 Configurable signal weights (Sum = 1.00)
    WEIGHT_SEMANTIC = 0.22
    WEIGHT_CONTEXT = 0.18
    WEIGHT_ROLE_A11Y = 0.15
    WEIGHT_STRUCTURE = 0.14
    WEIGHT_HISTORICAL = 0.11
    WEIGHT_SELECTOR = 0.10
    WEIGHT_STATE = 0.05
    WEIGHT_GEOMETRY = 0.05

    # Thresholds
    AMBIGUITY_MARGIN = 0.05
    THRESHOLD_EXACT = 0.95
    THRESHOLD_STRONG = 0.80
    THRESHOLD_RECOVERED = 0.65
    THRESHOLD_MINIMUM = 0.40

    TARGET_PROFILES: Dict[str, Dict[str, Any]] = {
        "MESSAGE_INPUT": {
            "expected_roles": ["textbox", "textarea", "input"],
            "expected_tags": ["textarea", "input", "div"],
            "keywords": ["message", "prompt", "ask", "chat", "type", "search"],
            "is_input": True,
        },
        "SEND_BUTTON": {
            "expected_roles": ["button"],
            "expected_tags": ["button", "svg", "div", "a"],
            "keywords": ["send", "submit", "arrow", "generate", "enter"],
            "is_input": False,
        },
        "STOP_BUTTON": {
            "expected_roles": ["button"],
            "expected_tags": ["button", "div"],
            "keywords": ["stop", "cancel", "pause", "halt"],
            "is_input": False,
        },
        "REGENERATE_BUTTON": {
            "expected_roles": ["button"],
            "expected_tags": ["button", "div", "a"],
            "keywords": ["retry", "regenerate", "try again"],
            "is_input": False,
        },
    }

    def __init__(self) -> None:
        self.history: Dict[str, Dict[str, Any]] = {}

    def score_element(
        self,
        element: Dict[str, Any],
        semantic_role: str,
        spatial_context: Optional[Dict[str, Any]] = None,
    ) -> ScoredCandidate:
        profile = self.TARGET_PROFILES.get(semantic_role, {
            "expected_roles": [semantic_role.lower()],
            "expected_tags": ["button", "input", "a", "div", "textarea"],
            "keywords": [semantic_role.lower()],
            "is_input": False,
        })

        # Support both flat and nested descriptors (from DomScripts)
        ident = element.get("identity", element)
        a11y = element.get("accessibility", {})
        state = element.get("state", {})
        geom = element.get("geometry", element.get("bounds", {}))

        is_visible = state.get("visible", element.get("visible", True))
        is_disabled = element.get("disabled", False) or a11y.get("aria_disabled", False)

        if not is_visible:
            return ScoredCandidate(
                element=element,
                score=0.0,
                confidence_band=ConfidenceBand.UNRESOLVED,
                signals={"state": 0.0},
                health=MappingHealthStatus.DEGRADED,
                explanation="Element is not visible in the DOM viewport",
            )

        tag = (ident.get("tag") or "").lower()
        role = (a11y.get("aria_role") or ident.get("role") or tag).lower()
        text = (ident.get("inner_text") or ident.get("text") or ident.get("value") or "").lower()
        aria_label = (a11y.get("aria_label") or ident.get("ariaLabel") or "").lower()
        placeholder = (ident.get("placeholder") or "").lower()
        elem_id = (ident.get("id") or "").lower()
        classes = " ".join(ident.get("class_list", [])) if isinstance(ident.get("class_list"), list) else (ident.get("classes") or "")

        # 1. Semantic Signal (0.22)
        semantic_score = 0.0
        accessible_name = aria_label or placeholder or text
        keywords = profile.get("keywords", [])
        for kw in keywords:
            if kw == accessible_name or kw in accessible_name:
                semantic_score = 1.0
                break
            elif any(part in accessible_name for part in kw.split()):
                semantic_score = max(semantic_score, 0.75)

        # 2. Context Signal (0.18)
        context_score = 0.4
        for kw in keywords:
            if kw in classes.lower() or kw in elem_id:
                context_score = 1.0
                break

        # 3. Role & Accessibility Signal (0.15)
        role_score = 0.0
        if role in profile.get("expected_roles", []):
            role_score = 1.0
        elif tag in profile.get("expected_tags", []):
            role_score = 0.8

        # 4. Structure Signal (0.14)
        structure_score = 0.6 if tag in profile.get("expected_tags", []) else 0.2

        # 5. Historical Signal (0.11)
        prior = self.history.get(semantic_role)
        historical_score = 0.5
        if prior:
            if prior.get("tag") == tag and prior.get("id") == elem_id and elem_id != "":
                historical_score = 1.0
            elif prior.get("tag") == tag:
                historical_score = 0.75

        # 6. Selector Match Signal (0.10)
        selector_score = 0.5
        if elem_id and any(kw in elem_id for kw in keywords):
            selector_score = 1.0

        # 7. State Signal (0.05)
        state_score = 1.0 if (not is_disabled and is_visible) else 0.2

        # 8. Geometry Signal (0.05)
        geometry_score = 0.5
        if spatial_context and geom:
            ref_x = spatial_context.get("x", 0)
            ref_y = spatial_context.get("y", 0)
            dist = math.hypot(geom.get("x", 0) - ref_x, geom.get("y", 0) - ref_y)
            geometry_score = max(0.0, 1.0 - (dist / 1200.0))

        # Composite Weighted Score
        total_score = (
            self.WEIGHT_SEMANTIC * semantic_score +
            self.WEIGHT_CONTEXT * context_score +
            self.WEIGHT_ROLE_A11Y * role_score +
            self.WEIGHT_STRUCTURE * structure_score +
            self.WEIGHT_HISTORICAL * historical_score +
            self.WEIGHT_SELECTOR * selector_score +
            self.WEIGHT_STATE * state_score +
            self.WEIGHT_GEOMETRY * geometry_score
        )
        total_score = min(1.0, max(0.0, total_score))

        # Confidence Class & Health Classification
        if total_score >= self.THRESHOLD_EXACT:
            band = ConfidenceBand.EXACT
            health = MappingHealthStatus.HEALTHY
        elif total_score >= self.THRESHOLD_STRONG:
            band = ConfidenceBand.STRONG
            health = MappingHealthStatus.HEALTHY
        elif total_score >= self.THRESHOLD_RECOVERED:
            band = ConfidenceBand.RECOVERED
            health = MappingHealthStatus.RECOVERED
        elif total_score >= self.THRESHOLD_MINIMUM:
            band = ConfidenceBand.WEAK
            health = MappingHealthStatus.DEGRADED
        else:
            band = ConfidenceBand.UNRESOLVED
            health = MappingHealthStatus.DEGRADED

        signals = {
            "semantic": semantic_score,
            "context": context_score,
            "role_a11y": role_score,
            "structure": structure_score,
            "historical": historical_score,
            "selector": selector_score,
            "state": state_score,
            "geometry": geometry_score,
        }

        explanation = f"Matched role={role} (score={total_score:.2f}) with semantic={semantic_score:.2f}, role={role_score:.2f}"
        return ScoredCandidate(element, total_score, band, signals, health, explanation)

    def resolve(
        self,
        candidates: List[Dict[str, Any]],
        semantic_role: str,
        spatial_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[ScoredCandidate]:
        if not candidates:
            return None

        scored = [self.score_element(c, semantic_role, spatial_context) for c in candidates]
        valid = [s for s in scored if s.confidence_band != ConfidenceBand.UNRESOLVED]
        if not valid:
            return None

        valid.sort(key=lambda x: x.score, reverse=True)
        winner = valid[0]

        # Ambiguity Margin Detector (from Alex Browser v2)
        if len(valid) >= 2:
            delta = valid[0].score - valid[1].score
            if delta < self.AMBIGUITY_MARGIN:
                winner.confidence_band = ConfidenceBand.AMBIGUOUS
                winner.health = MappingHealthStatus.AMBIGUOUS
                winner.explanation = f"Ambiguous match: delta={delta:.3f} < {self.AMBIGUITY_MARGIN} against second candidate"

        # Update historical memory
        ident = winner.element.get("identity", winner.element)
        self.history[semantic_role] = {
            "tag": ident.get("tag"),
            "id": ident.get("id"),
            "classes": ident.get("classes"),
        }
        return winner
