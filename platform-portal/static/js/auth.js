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
    form.addEventListener('submit', () => {
      if (!form.checkValidity()) return;
      // Disabling the native submitter during the submit event can cancel the
      // form navigation in WebKit. The page is navigating, so an announced
      // busy state is sufficient to prevent an apparent second action.
      form.setAttribute('aria-busy', 'true');
      submit.classList.add('is-loading');
      submit.querySelector('[data-button-label]').textContent = 'Signing in…';
    });
  }
})();
