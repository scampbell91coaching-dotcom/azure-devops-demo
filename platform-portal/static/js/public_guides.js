document.addEventListener("DOMContentLoaded", () => {
  const placeholder = document.querySelector(".video-placeholder__button");

  if (!placeholder) {
    return;
  }

  placeholder.addEventListener("click", () => {
    placeholder.querySelector("small").textContent =
      "Add your video URL in the guide content JSON.";
  });
});
