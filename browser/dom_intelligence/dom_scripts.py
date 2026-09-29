"""In-Page DOM Intelligence Scripts for V.O.I.D.E.

Ported from Alex Browser v2 (arc-telemetry) on-device runtime.
Provides:
- DOM Discovery Engine extracting rich descriptors (identity, accessibility, state, geometry, selectors)
- Safe Action Engine (scrollIntoView, native click dispatch, prototype value setters for React/SPA, focus, clear)
- Pulsing Element Reveal & Highlight Overlay
- Interactive Inspection Mode
"""

from __future__ import annotations
from typing import Optional


DOM_DISCOVERY_SCRIPT = r"""
(function() {
    try {
        var candidates = Array.from(document.querySelectorAll(
            'button, input, textarea, select, a[href], [role="button"], [role="textbox"], ' +
            '[role="link"], [role="menuitem"], [role="tab"], [contenteditable="true"], form, [aria-label]'
        ));

        var results = [];
        var idx = 0;

        for (var i = 0; i < candidates.length; i++) {
            var el = candidates[i];
            var rect = el.getBoundingClientRect();
            var isVisible = rect.width > 0 && rect.height > 0 &&
                            window.getComputedStyle(el).visibility !== 'hidden' &&
                            window.getComputedStyle(el).display !== 'none';

            var tag = el.tagName.toLowerCase();
            var ariaLabel = el.getAttribute('aria-label') || '';
            var placeholder = el.getAttribute('placeholder') || '';
            var text = (el.innerText || el.value || el.textContent || '').trim().slice(0, 150);
            var role = el.getAttribute('role') || tag;
            var isDisabled = el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';

            var cssSel = el.id ? '#' + CSS.escape(el.id) : (tag + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''));

            results.push({
                uid: 'elem-' + idx + '-' + Math.random().toString(36).substr(2, 6),
                tag: tag,
                id: el.id || '',
                role: role,
                aria_label: ariaLabel,
                placeholder: placeholder,
                text: text,
                is_visible: isVisible,
                is_disabled: isDisabled,
                css_selector: cssSel,
                identity: {
                    tag: tag,
                    id: el.id || '',
                    class_list: el.className && typeof el.className === 'string' ? el.className.trim().split(/\s+/) : [],
                    inner_text: text,
                    placeholder: placeholder,
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || '',
                    value: el.value || '',
                    href: el.getAttribute('href') || '',
                    src: el.getAttribute('src') || ''
                },
                accessibility: {
                    aria_label: ariaLabel,
                    aria_role: role,
                    aria_disabled: isDisabled
                },
                state: {
                    visible: isVisible,
                    enabled: !isDisabled,
                    clickable: isVisible && !isDisabled
                },
                geometry: {
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                },
                selectors: {
                    css: cssSel,
                    xpath: '//' + tag
                }
            });
            idx++;
        }
        return JSON.stringify({ success: true, count: results.length, elements: results });
    } catch (e) {
        return JSON.stringify({ success: false, error: e.toString(), elements: [] });
    }
})();
"""


def build_action_script(target_selector: str, action_type: str, param: Optional[str] = None) -> str:
    """Build action execution script ported from Alex Browser ActionEngine."""
    safe_param = (
        (param or "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    safe_selector = target_selector.replace('"', '\\"')

    return f"""
    (function() {{
        try {{
            var el = document.querySelector("{safe_selector}");
            if (!el) return JSON.stringify({{ success: false, error: "ELEMENT_NOT_FOUND" }});

            el.scrollIntoView({{ behavior: "smooth", block: "center" }});

            if ("{action_type}" === "click") {{
                el.focus();
                var mouseEv = new MouseEvent("click", {{ bubbles: true, cancelable: true, view: window }});
                el.dispatchEvent(mouseEv);
                if (typeof el.click === "function") el.click();
                return JSON.stringify({{ success: true, action: "click", tag: el.tagName }});
            }} else if ("{action_type}" === "type") {{
                el.focus();
                var proto = (el instanceof HTMLTextAreaElement) ? window.HTMLTextAreaElement.prototype : (el instanceof HTMLInputElement ? window.HTMLInputElement.prototype : null);
                var desc = proto ? Object.getOwnPropertyDescriptor(proto, "value") : null;
                if (desc && desc.set) {{
                    desc.set.call(el, "{safe_param}");
                }} else {{
                    el.value = "{safe_param}";
                }}
                if (el.isContentEditable) {{
                    el.innerText = "{safe_param}";
                }}
                el.dispatchEvent(new InputEvent("input", {{ bubbles: true, inputType: "insertText", data: "{safe_param}" }}));
                el.dispatchEvent(new Event("change", {{ bubbles: true }}));
                return JSON.stringify({{ success: true, action: "type", valueLength: "{safe_param}".length }});
            }} else if ("{action_type}" === "clear") {{
                el.focus();
                el.value = "";
                el.dispatchEvent(new Event("input", {{ bubbles: true }}));
                el.dispatchEvent(new Event("change", {{ bubbles: true }}));
                return JSON.stringify({{ success: true, action: "clear" }});
            }} else if ("{action_type}" === "focus") {{
                el.focus();
                return JSON.stringify({{ success: true, action: "focus" }});
            }}
            return JSON.stringify({{ success: false, error: "UNKNOWN_ACTION" }});
        }} catch (e) {{
            return JSON.stringify({{ success: false, error: e.toString() }});
        }}
    }})();
    """


def build_highlight_script(target_selector: str, title: str) -> str:
    """Build visual reveal highlight overlay ported from Alex Browser."""
    safe_title = title.replace('"', '\\"')
    safe_selector = target_selector.replace('"', '\\"')

    return f"""
    (function() {{
        try {{
            var el = document.querySelector("{safe_selector}");
            if (!el) return JSON.stringify({{ success: false, error: "ELEMENT_NOT_FOUND" }});

            el.scrollIntoView({{ behavior: "smooth", block: "center" }});

            var existing = document.getElementById('__voide_preview_highlight__');
            if (existing) existing.remove();

            var rect = el.getBoundingClientRect();
            var box = document.createElement('div');
            box.id = '__voide_preview_highlight__';
            box.style.position = 'fixed';
            box.style.left = rect.left + 'px';
            box.style.top = rect.top + 'px';
            box.style.width = rect.width + 'px';
            box.style.height = rect.height + 'px';
            box.style.border = '2px solid #FFFFFF';
            box.style.borderRadius = '4px';
            box.style.backgroundColor = 'rgba(255, 255, 255, 0.15)';
            box.style.boxShadow = '0 0 12px rgba(255, 255, 255, 0.8)';
            box.style.zIndex = '2147483647';
            box.style.pointerEvents = 'none';
            box.style.transition = 'opacity 0.5s ease-out';

            var badge = document.createElement('div');
            badge.style.position = 'absolute';
            badge.style.top = '-26px';
            badge.style.left = '0';
            badge.style.background = '#000000';
            badge.style.color = '#FFFFFF';
            badge.style.border = '1px solid #FFFFFF';
            badge.style.fontSize = '10px';
            badge.style.fontWeight = 'bold';
            badge.style.fontFamily = 'monospace';
            badge.style.padding = '3px 6px';
            badge.style.borderRadius = '2px';
            badge.innerText = "{safe_title}";
            box.appendChild(badge);

            document.body.appendChild(box);

            setTimeout(function() {{
                box.style.opacity = '0';
                setTimeout(function() {{
                    if (box.parentNode) box.parentNode.removeChild(box);
                }}, 500);
            }}, 3000);

            return JSON.stringify({{ success: true, selector: "{safe_selector}" }});
        }} catch (e) {{
            return JSON.stringify({{ success: false, error: e.toString() }});
        }}
    }})();
    """
