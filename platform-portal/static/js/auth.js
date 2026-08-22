(() => {
  const toggle = document.querySelector('[data-password-toggle]');
  const password = document.querySelector('#password');
  if (toggle && password) {
    toggle.addEventListener('click', () => {
      const visible = password.type === 'text';
      password.type = visible ? 'password' : 'text';
      toggle.setAttribute('aria-pressed', String(!visible));
      toggle.setAttribute('aria-label', visible ? 'Show password' : 'Hide password');
      password.focus();
    });
  }

  const form = document.querySelector('[data-auth-form]');
  const submit = document.querySelector('[data-submit-button]');
  if (form && submit) {
    form.addEventListener('submit', event => {
      if (!form.checkValidity()) return;
      if (form.getAttribute('aria-busy') === 'true') {
        event.preventDefault();
        return;
      }
      // Disabling the native submitter during the submit event can cancel the
      // form navigation in WebKit. Keep it enabled for the first native
      // submission and reject any later submit event with the busy guard.
      form.setAttribute('aria-busy', 'true');
      submit.classList.add('is-loading');
      submit.querySelector('[data-button-label]').textContent = 'Signing in…';
    });
  }
})();
