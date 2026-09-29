"""Unit Tests for SemanticResolver and Browser Test Matrix."""

from voide.browser.dom_intelligence.semantic_resolver import (
    SemanticResolver,
    ConfidenceBand,
)


def test_baseline_fixture_resolution():
    resolver = SemanticResolver()

    # Extracted candidate nodes matching tests/browser_fixtures/baseline.html
    candidates = [
        {
            "uid": "el-1",
            "tag": "textarea",
            "role": "textbox",
            "ariaLabel": "",
            "placeholder": "Type a message...",
            "text": "",
            "id": "prompt-input",
            "classes": "chat-input",
            "visible": True,
            "disabled": False,
        },
        {
            "uid": "el-2",
            "tag": "button",
            "role": "button",
            "ariaLabel": "",
            "placeholder": "",
            "text": "Send",
            "id": "send-button",
            "classes": "btn-send",
            "visible": True,
            "disabled": False,
        },
    ]

    # Resolve MESSAGE_INPUT
    input_candidate = resolver.resolve(candidates, "MESSAGE_INPUT")
    assert input_candidate is not None
    assert input_candidate.element["id"] == "prompt-input"
    assert input_candidate.confidence_band in (ConfidenceBand.HIGH, ConfidenceBand.PROBABLE)

    # Resolve SEND_BUTTON
    send_candidate = resolver.resolve(candidates, "SEND_BUTTON")
    assert send_candidate is not None
    assert send_candidate.element["id"] == "send-button"
    assert send_candidate.confidence_band in (ConfidenceBand.HIGH, ConfidenceBand.PROBABLE)


def test_v2_obfuscated_classes_resilience():
    resolver = SemanticResolver()

    # Matching tests/browser_fixtures/v2_renamed_classes.html (randomized classes & IDs)
    candidates = [
        {
            "uid": "el-obf-1",
            "tag": "textarea",
            "role": "textbox",
            "ariaLabel": "",
            "placeholder": "Type a message...",
            "text": "",
            "id": "inp_rand_99",
            "classes": "inp_8721_obf",
            "visible": True,
            "disabled": False,
        },
        {
            "uid": "el-obf-2",
            "tag": "button",
            "role": "button",
            "ariaLabel": "",
            "placeholder": "",
            "text": "Send",
            "id": "btn_rand_33",
            "classes": "btn_act_44",
            "visible": True,
            "disabled": False,
        },
    ]

    # Resolver succeeds even with obfuscated classes because tag, placeholder, and text match
    input_candidate = resolver.resolve(candidates, "MESSAGE_INPUT")
    assert input_candidate is not None
    assert input_candidate.element["id"] == "inp_rand_99"

    send_candidate = resolver.resolve(candidates, "SEND_BUTTON")
    assert send_candidate is not None
    assert send_candidate.element["id"] == "btn_rand_33"


def test_v3_aria_repositioned_resolution():
    resolver = SemanticResolver()

    # Matching tests/browser_fixtures/v3_aria_repositioned.html (div role=textbox, SVG button with aria-label)
    candidates = [
        {
            "uid": "el-aria-1",
            "tag": "div",
            "role": "textbox",
            "ariaLabel": "Enter your prompt message",
            "placeholder": "",
            "text": "",
            "id": "",
            "classes": "editor-input",
            "visible": True,
            "disabled": False,
        },
        {
            "uid": "el-aria-2",
            "tag": "button",
            "role": "button",
            "ariaLabel": "Submit prompt to model",
            "placeholder": "",
            "text": "",
            "id": "",
            "classes": "primary-submit",
            "visible": True,
            "disabled": False,
        },
    ]

    input_candidate = resolver.resolve(candidates, "MESSAGE_INPUT")
    assert input_candidate is not None
    assert input_candidate.element["role"] == "textbox"

    send_candidate = resolver.resolve(candidates, "SEND_BUTTON")
    assert send_candidate is not None
    assert "Submit prompt" in send_candidate.element["ariaLabel"]


def test_invisible_or_disabled_element_rejection():
    resolver = SemanticResolver()

    candidates = [
        {
            "uid": "el-hidden",
            "tag": "button",
            "role": "button",
            "ariaLabel": "Send",
            "text": "Send",
            "visible": False,  # Invisible
            "disabled": False,
        }
    ]

    # Must reject invisible element
    candidate = resolver.resolve(candidates, "SEND_BUTTON")
    assert candidate is None


def test_v4_nested_wrappers_resolution():
    resolver = SemanticResolver()

    # Matching tests/browser_fixtures/v4_nested_wrappers.html
    candidates = [
        {
            "uid": "el-v4-1",
            "tag": "textarea",
            "role": "textbox",
            "ariaLabel": "Ask chat assistant",
            "placeholder": "Ask AI anything...",
            "text": "",
            "id": "dynamic-chat-input",
            "classes": "",
            "visible": True,
            "disabled": False,
        },
        {
            "uid": "el-v4-2",
            "tag": "button",
            "role": "button",
            "ariaLabel": "Send message",
            "placeholder": "",
            "text": "Send",
            "id": "dynamic-send-btn",
            "classes": "",
            "visible": True,
            "disabled": False,
        },
    ]

    input_cand = resolver.resolve(candidates, "MESSAGE_INPUT")
    assert input_cand is not None
    assert input_cand.element["id"] == "dynamic-chat-input"

    send_cand = resolver.resolve(candidates, "SEND_BUTTON")
    assert send_cand is not None
    assert send_cand.element["id"] == "dynamic-send-btn"

