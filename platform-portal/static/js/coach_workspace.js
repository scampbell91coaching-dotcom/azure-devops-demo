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


document.addEventListener("change", (event) => {
  const select = event.target.closest("select[data-auto-submit]");
  if (!select || !select.form) {
    return;
  }

  const form = select.form;

  if ((form.method || "get").toLowerCase() === "get") {
    const params = new URLSearchParams(new FormData(form));
    params.delete("csrf_token");

    const url = new URL(form.action || window.location.href, window.location.href);
    url.search = params.toString();
    window.location.assign(url.toString());
    return;
  }

  form.requestSubmit();
});
