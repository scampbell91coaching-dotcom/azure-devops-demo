document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  const button = document.querySelector("[data-coach-menu-button]");
  const navigation = document.querySelector("[data-coach-navigation]");

  if (!button || !navigation) {
    return;
  }

  button.addEventListener("click", () => {
    const open = navigation.classList.toggle("is-open");

    button.setAttribute("aria-expanded", open ? "true" : "false");
  });
});
