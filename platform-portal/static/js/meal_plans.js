document.querySelector('[data-meal-create-toggle]')?.addEventListener('click', function () {
  const panel = document.getElementById(this.getAttribute('aria-controls'));
  const open = this.getAttribute('aria-expanded') === 'true';

  this.setAttribute('aria-expanded', String(!open));
  panel.hidden = open;

  if (!open) {
    panel.querySelector('input')?.focus();
  }
});
