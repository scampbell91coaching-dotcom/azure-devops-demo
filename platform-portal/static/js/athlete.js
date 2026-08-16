(() => {
  const page = document.body.dataset.athletePage;
  document.querySelectorAll('[data-nav-page]').forEach((link) => {
    if (link.dataset.navPage === page) link.setAttribute('aria-current', 'page');
  });
  document.querySelectorAll('.athlete-mobile-nav a, .session-card').forEach((link) => {
    link.addEventListener('click', () => link.setAttribute('aria-busy', 'true'));
  });

  const more = document.querySelector('[data-athlete-more]');
  if (more) {
    const summary = more.querySelector('summary');
    document.addEventListener('click', (event) => {
      if (more.open && !more.contains(event.target)) more.removeAttribute('open');
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape' || !more.open) return;
      more.removeAttribute('open');
      summary?.focus();
    });
  }

  const template = document.querySelector('#extra-set-template');
  document.querySelectorAll('[data-exercise]').forEach((exercise) => {
    exercise.querySelector('[data-add-set]')?.addEventListener('click', () => {
      const prescriptionId = exercise.dataset.prescriptionId;
      const setOrder = Number(exercise.dataset.nextSet);
      if (!template || !prescriptionId || !Number.isInteger(setOrder)) return;
      const row = template.content.firstElementChild.cloneNode(true);
      row.querySelector('[data-set-label]').textContent = `Extra set ${setOrder}`;
      row.querySelectorAll('[data-field]').forEach((field) => {
        field.name = field.dataset.field === 'row'
          ? `row-${prescriptionId}-${setOrder}`
          : `set-${prescriptionId}-${setOrder}-${field.dataset.field}`;
      });
      exercise.querySelector('[data-set-list]').append(row);
      exercise.dataset.nextSet = String(setOrder + 1);
      row.querySelector('input[type="number"]')?.focus();
    });
  });

  document.querySelector('[data-training-form]')?.addEventListener('change', (event) => {
    const checkbox = event.target.closest('input[type="checkbox"]');
    if (!checkbox) return;
    const row = checkbox.closest('[data-set-row]');
    const completed = row.querySelector('input[name$="-completed"]');
    const skipped = row.querySelector('input[name$="-skipped"]');
    if (checkbox === completed && completed.checked) skipped.checked = false;
    if (checkbox === skipped && skipped.checked) completed.checked = false;
    row.classList.toggle('is-skipped', skipped.checked);
  });

  document.querySelector('[data-finish-session]')?.addEventListener('click', (event) => {
    if (!window.confirm('Finish this session? Your submitted training will become read-only.')) {
      event.preventDefault();
    }
  });
})();
