// W95FA, like the MS Sans Serif it copies, has no typographic dashes, middle dots or maths signs.
// Browsers fill such gaps from another font, which breaks the look mid-sentence. This swaps them
// for the plain forms a 1998 dialog would have used, for text already on the page and text added later.
(function () {
  const MAP = { "–": "-", "—": "-", "−": "-", "·": ",", "≤": "<=", "≥": ">=",
    "±": "+/-", "×": "x", "²": "2", "…": "...", "©": "(c)", "°": " deg",
    "µ": "u", "σ": "sd", "Δ": "d", "→": "->", "←": "<-", "≈": "~",
    "′": "'", "″": "\"", "«": "\"", "»": "\"", "▶": ">", "■": "" };
  const RE = new RegExp("[" + Object.keys(MAP).join("") + "]", "g");
  // " · " reads best as ", "; a lone middle dot inside a word stays a comma too
  const fix = t => t.replace(/[\s\u00a0]*\u00b7[\s\u00a0]*/g, ", ").replace(RE, c => MAP[c]);
  const skip = n => n.parentElement && n.parentElement.closest("script, style, textarea, code, pre, #place-results");

  function clean(root) {
    if (root.nodeType === 3) { if (!skip(root) && RE.test(root.data)) { RE.lastIndex = 0; root.data = fix(root.data); } RE.lastIndex = 0; return; }
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (w.nextNode()) {
      const n = w.currentNode;
      if (skip(n)) continue;
      if (RE.test(n.data)) n.data = fix(n.data);
      RE.lastIndex = 0;
    }
  }

  function start() {
    clean(document.body);
    new MutationObserver(list => {
      for (const m of list) {
        if (m.type === "characterData") clean(m.target);
        else m.addedNodes.forEach(clean);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
