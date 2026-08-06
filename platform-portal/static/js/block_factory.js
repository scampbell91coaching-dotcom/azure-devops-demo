document.addEventListener("DOMContentLoaded", () => {
  const factory = document.querySelector("[data-factory-accessories]");
  if (!factory) return;
  const rows = factory.querySelector("[data-accessory-rows]");
  const template = factory.querySelector("[data-accessory-template]");
  const volume = factory.querySelector("[data-accessory-volume]");
  const customCount = factory.querySelector("[data-custom-count]");
  const summary = factory.querySelector("[data-accessory-summary]");
  const volumeLabels = {
    minimal: "1–2 accessories per session",
    standard: "3–4 accessories per session (lift-aware defaults may use 2–5)",
    high: "5–6 accessories per session",
    custom: "the custom count or range below",
  };
  const updateVolume = () => {
    const custom = volume.value === "custom";
    customCount.hidden = !custom;
    customCount.querySelectorAll("input").forEach((input, index) => {
      input.required = custom && index === 0;
      input.disabled = !custom;
    });
    summary.textContent = `Preview will show roles and ${volumeLabels[volume.value]}.`;
  };
  const bind = (row) => {
    row.querySelector("[data-remove-accessory]").onclick = () => row.remove();
    row.querySelector("[data-move-up]").onclick = () => row.previousElementSibling && rows.insertBefore(row, row.previousElementSibling);
    row.querySelector("[data-move-down]").onclick = () => row.nextElementSibling && rows.insertBefore(row.nextElementSibling, row);
  };
  rows.querySelectorAll(".factory-accessory-row").forEach(bind);
  factory.querySelector("[data-add-accessory]").onclick = () => {
    const row = template.content.firstElementChild.cloneNode(true);
    rows.append(row); bind(row); row.querySelector("select").focus();
  };
  factory.querySelector("[data-accessory-filter]").addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase();
    factory.querySelectorAll("option[data-search]").forEach((option) => option.hidden = !option.dataset.search.toLowerCase().includes(query));
  });
  volume.addEventListener("change", updateVolume);
  updateVolume();
});
