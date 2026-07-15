/* Negarit Business Review — site-wide progressive enhancement.
   Every block below checks that its target elements exist before doing
   anything, so this file is safe to include on every page. */

(function themeToggle() {
  var toggle = document.getElementById('theme-toggle');
  if (!toggle) return;
  toggle.addEventListener('click', function () {
    var current = document.documentElement.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (e) { /* storage unavailable; theme still applies for this view */ }
  });
})();
