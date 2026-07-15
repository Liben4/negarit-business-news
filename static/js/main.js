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

(function heroTilt() {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var target = document.querySelector('.hero__image');
  if (!target || reduceMotion) return;

  var strength = 8; // max degrees of rotation — subtle, not a gimmick

  target.addEventListener('mousemove', function (e) {
    target.style.transition = 'transform 0.1s ease-out';
    var rect = target.getBoundingClientRect();
    var px = (e.clientX - rect.left) / rect.width - 0.5;
    var py = (e.clientY - rect.top) / rect.height - 0.5;
    target.style.transform =
      'perspective(1000px) rotateY(' + (px * strength).toFixed(2) + 'deg) ' +
      'rotateX(' + (-py * strength).toFixed(2) + 'deg) scale3d(1.02, 1.02, 1.02)';
  });

  target.addEventListener('mouseleave', function () {
    target.style.transition = 'transform 0.5s cubic-bezier(0.22, 1, 0.36, 1)';
    target.style.transform = '';
  });
})();

(function scrollReveal() {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var items = document.querySelectorAll('.reveal');
  if (!items.length) return;

  if (reduceMotion || !('IntersectionObserver' in window)) {
    items.forEach(function (el) { el.classList.add('is-visible'); });
    return;
  }

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

  items.forEach(function (el) { observer.observe(el); });
})();
