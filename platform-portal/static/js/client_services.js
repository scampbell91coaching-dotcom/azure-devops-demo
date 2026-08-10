document.querySelectorAll('[data-client-services-form]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    const disablesService = Array.from(form.querySelectorAll('select')).some(
      (field) => {
        const initial = field.dataset.initialValue;
        return initial !== field.value && ['no', 'none'].includes(field.value);
      },
    );
    if (
      disablesService &&
      !window.confirm(
        'Disable this service? Future access will stop, but all existing programmes, check-ins, reviews and notes will be retained.',
      )
    ) {
      event.preventDefault();
    }
  });
});
