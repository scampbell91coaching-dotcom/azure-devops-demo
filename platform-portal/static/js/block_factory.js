document.addEventListener("DOMContentLoaded", () => {
  const factory = document.querySelector("[data-factory-accessories]");
  if (!factory) return;
  const rows = factory.querySelector("[data-accessory-rows]");
  const template = factory.querySelector("[data-accessory-template]");
  const summary = factory.querySelector("[data-accessory-summary]");
  const updateSummary = () => {
    const count = rows.querySelectorAll(".factory-accessory-row").length;
    summary.textContent = count
      ? `${count} coach-selected assistance exercise${count === 1 ? "" : "s"}; no quota is applied.`
      : "No assistance selected. Zero assistance is valid.";
  };
  const bind = (row) => {
    row.querySelector("[data-remove-accessory]").onclick = () => { row.remove(); updateSummary(); };
    row.querySelector("[data-move-up]").onclick = () => row.previousElementSibling && rows.insertBefore(row, row.previousElementSibling);
    row.querySelector("[data-move-down]").onclick = () => row.nextElementSibling && rows.insertBefore(row.nextElementSibling, row);
  };
  rows.querySelectorAll(".factory-accessory-row").forEach(bind);
  factory.querySelector("[data-add-accessory]").onclick = () => {
    const row = template.content.firstElementChild.cloneNode(true);
    rows.append(row); bind(row); updateSummary(); row.querySelector("select").focus();
  };
  factory.querySelector("[data-accessory-filter]").addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase();
    factory.querySelectorAll("option[data-search]").forEach((option) => option.hidden = !option.dataset.search.toLowerCase().includes(query));
  });
  updateSummary();
});
