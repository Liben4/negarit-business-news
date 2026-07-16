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

(function readingProgress() {
  var bar = document.getElementById('reading-progress');
  var article = document.querySelector('.article__body');
  if (!bar || !article) return;

  function update() {
    var rect = article.getBoundingClientRect();
    var articleHeight = rect.height - window.innerHeight;
    var scrolled = -rect.top;
    var pct = articleHeight > 0 ? Math.min(Math.max(scrolled / articleHeight, 0), 1) * 100 : 0;
    bar.style.width = pct + '%';
  }

  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  update();
})();

(function clapButton() {
  var btn = document.getElementById('clap-button');
  var countEl = document.getElementById('clap-count');
  var bar = document.querySelector('.share-bar');
  if (!btn || !countEl || !bar) return;
  var slug = bar.getAttribute('data-article-slug');

  btn.addEventListener('click', function () {
    if (btn.disabled) return;
    var tokenMeta = document.querySelector('meta[name="csrf-token"]');
    fetch('/article/' + encodeURIComponent(slug) + '/clap', {
      method: 'POST',
      headers: tokenMeta ? { 'X-CSRF-Token': tokenMeta.getAttribute('content') } : {}
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        countEl.textContent = data.claps;
        btn.classList.add('clap-button--done', 'clap-button--bump');
        btn.disabled = true;
        setTimeout(function () { btn.classList.remove('clap-button--bump'); }, 400);
      })
      .catch(function () { /* network hiccup — button just stays clickable */ });
  });
})();

(function copyLink() {
  var btn = document.getElementById('copy-link-btn');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var url = window.location.href;
    var done = function () {
      var original = btn.textContent;
      btn.textContent = 'Copied';
      btn.classList.add('share-link--copied');
      setTimeout(function () {
        btn.textContent = original;
        btn.classList.remove('share-link--copied');
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(function () {
        window.prompt('Copy this link:', url);
      });
    } else {
      window.prompt('Copy this link:', url);
    }
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
