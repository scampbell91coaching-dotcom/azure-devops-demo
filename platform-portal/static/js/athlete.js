(() => {
  const page = document.body.dataset.athletePage;
  document.querySelectorAll('[data-nav-page]').forEach((link) => {
    if (link.dataset.navPage === page) link.setAttribute('aria-current', 'page');
  });
  document.querySelectorAll('.athlete-mobile-nav a, .session-card').forEach((link) => {
    link.addEventListener('click', () => link.setAttribute('aria-busy', 'true'));
  });
})();
