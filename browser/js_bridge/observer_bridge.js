/**
 * V.O.I.D.E. Browser JS Bridge & Mutation Observer
 * 
 * Provides:
 * - Debounced mutation queuing to avoid remap storms
 * - Significance classification (cosmetic, text-only, local-subtree, structural)
 * - Semantic element attribute extraction
 */

(function() {
  if (window.__voide_bridge_installed) return;
  window.__voide_bridge_installed = true;

  const CONFIG = {
    debounceMs: 250,
    maxBatchSize: 100
  };

  let mutationQueue = [];
  let debounceTimer = null;
  let mappingVersion = 1;

  function classifyMutation(mutation) {
    if (mutation.type === 'characterData') {
      return 'text-only';
    }
    if (mutation.type === 'attributes') {
      const attr = mutation.attributeName;
      if (['class', 'style', 'tabindex'].includes(attr)) {
        return 'cosmetic';
      }
      if (attr && (attr.startsWith('aria-') || ['role', 'name', 'placeholder', 'id', 'disabled'].includes(attr))) {
        return 'structural';
      }
      return 'cosmetic';
    }
    if (mutation.type === 'childList') {
      const added = Array.from(mutation.addedNodes);
      const removed = Array.from(mutation.removedNodes);
      const elements = [...added, ...removed].filter(n => n.nodeType === Node.ELEMENT_NODE);
      
      const hasActionable = elements.some(el => {
        const tag = el.tagName.toLowerCase();
        return ['button', 'input', 'textarea', 'form', 'a', 'select'].includes(tag) ||
               el.getAttribute('role') || el.getAttribute('aria-label');
      });

      if (hasActionable) {
        return 'structural';
      }
      return 'local-subtree';
    }
    return 'cosmetic';
  }

  function processBatch() {
    if (mutationQueue.length === 0) return;

    const classifications = mutationQueue.map(classifyMutation);
    mutationQueue = [];

    const hasStructural = classifications.includes('structural');
    const hasLocal = classifications.includes('local-subtree');
    const hasText = classifications.includes('text-only');

    let overallType = 'cosmetic';
    if (hasStructural) {
      overallType = 'structural';
      mappingVersion += 1;
    } else if (hasLocal) {
      overallType = 'local-subtree';
    } else if (hasText) {
      overallType = 'text-only';
    }

    const payload = {
      event: 'DOM_MUTATION',
      mutation_type: overallType,
      mapping_version: mappingVersion,
      timestamp: Date.now()
    };

    if (window.__voide_on_mutation) {
      window.__voide_on_mutation(payload);
    }
  }

  const observer = new MutationObserver(mutations => {
    for (let i = 0; i < mutations.length; i++) {
      mutationQueue.push(mutations[i]);
      if (mutationQueue.length >= CONFIG.maxBatchSize) {
        clearTimeout(debounceTimer);
        processBatch();
        return;
      }
    }
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(processBatch, CONFIG.debounceMs);
  });

  observer.observe(document.body || document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    characterData: true,
    attributeFilter: ['class', 'style', 'role', 'aria-label', 'disabled', 'placeholder', 'id', 'name']
  });

  window.__voide_bridge = {
    getVersion: () => mappingVersion,
    
    extractCandidates: () => {
      const nodes = Array.from(document.querySelectorAll('button, input, textarea, [role="button"], [role="textbox"], [contenteditable="true"], form, [aria-label]'));
      return nodes.map((el, idx) => {
        const rect = el.getBoundingClientRect();
        return {
          uid: 'elem-' + idx + '-' + Math.random().toString(36).substr(2, 6),
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role') || el.tagName.toLowerCase(),
          ariaLabel: el.getAttribute('aria-label') || '',
          placeholder: el.getAttribute('placeholder') || '',
          text: (el.innerText || el.value || el.textContent || '').trim().slice(0, 100),
          id: el.id || '',
          classes: el.className || '',
          disabled: el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true',
          visible: rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden',
          bounds: {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height
          }
        };
      });
    }
  };
})();
