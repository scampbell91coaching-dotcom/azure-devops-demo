document.addEventListener("DOMContentLoaded", () => {
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
