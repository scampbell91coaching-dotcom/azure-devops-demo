document.addEventListener("DOMContentLoaded", () => {
  const button = document.querySelector("[data-public-menu]");
  const navigation = document.querySelector("[data-public-navigation]");

  if (!button || !navigation) return;

  const closeMenu = ({ returnFocus = false } = {}) => {
    button.setAttribute("aria-expanded", "false");
    navigation.classList.remove("is-open");
    document.body.classList.remove("public-menu-open");
    if (returnFocus) button.focus();
  };

  button.addEventListener("click", () => {
    const willOpen = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(willOpen));
    navigation.classList.toggle("is-open", willOpen);
    document.body.classList.toggle("public-menu-open", willOpen);
  });

  navigation.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navigation.classList.contains("is-open")) {
      closeMenu({ returnFocus: true });
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 760) closeMenu();
  });
});
