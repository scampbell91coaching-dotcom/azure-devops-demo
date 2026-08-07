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

  const closeNavigation = () => {
    navigation.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
  };

  navigation.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("a") && window.matchMedia("(max-width: 1080px)").matches) {
      closeNavigation();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const navigationWasOpen = navigation.classList.contains("is-open");
      const openMore = document.querySelector("[data-coach-more][open]");
      closeNavigation();
      document.querySelectorAll("[data-coach-more][open]").forEach((menu) => menu.removeAttribute("open"));
      if (navigationWasOpen) button.focus();
      else if (openMore) openMore.querySelector("summary")?.focus();
    }
  });

  document.addEventListener("click", (event) => {
    document.querySelectorAll("[data-coach-more][open]").forEach((menu) => {
      if (event.target instanceof Node && !menu.contains(event.target)) menu.removeAttribute("open");
    });
  });

  window.addEventListener("resize", () => {
    if (!window.matchMedia("(max-width: 1080px)").matches) closeNavigation();
  });
});
