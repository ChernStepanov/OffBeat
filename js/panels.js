// Links to a folded panel must expose it before the browser follows the anchor.
(() => {
  function reveal(hash) {
    if (!hash || hash[0] !== '#') return;
    const target = document.getElementById(hash.slice(1));
    const panel = target?.closest('details.panel-disclosure');
    if (panel) panel.open = true;
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (link) reveal(link.getAttribute('href'));
  });
  window.addEventListener('hashchange', () => reveal(location.hash));
  reveal(location.hash);
})();
