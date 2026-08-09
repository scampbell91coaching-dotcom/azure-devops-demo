(() => {
  const field = document.querySelector('[data-account-token]');
  const form = document.querySelector('[data-account-token-form]');
  if (!field || !form) return;
  const token = window.location.hash.slice(1);
  if (/^[A-Za-z0-9_-]{43,200}$/.test(token)) {
    field.value = token;
    history.replaceState(null, '', window.location.pathname);
    return;
  }
  form.querySelectorAll('input, button').forEach((control) => {
    control.disabled = true;
  });
  const notice = document.createElement('p');
  notice.setAttribute('role', 'alert');
  notice.textContent = 'This link is incomplete. Ask your coach for a new link.';
  form.prepend(notice);
})();
