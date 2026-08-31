const initialiseBlockFactory = () => {
  const form = document.querySelector("#block-factory-form");
  const factory = document.querySelector("[data-factory-accessories]");
  if (!form || !factory) return;
  const preview = document.querySelector("[data-factory-preview]");
  const accept = document.querySelector("[data-accept-proposal]");
  const staleNotice = document.querySelector("[data-preview-stale]");
  const reasonWrap = document.querySelector("[data-override-reason]");
  const state = document.querySelector("[data-factory-state]");
  const reason = form.elements.namedItem("override_reason");
  let dirty = preview?.classList.contains("is-stale") || false;

  const startFrom = form.querySelector("[data-start-from]");
  const goldenField = form.querySelector("[data-golden-programme-field]");
  const goldenSelect = form.querySelector("[data-golden-programme]");
  const showGoldenChoice = () => {
    if (goldenField) goldenField.hidden = startFrom?.value !== "golden";
  };
  startFrom?.addEventListener("change", showGoldenChoice);
  goldenSelect?.addEventListener("change", () => {
    const selected = goldenSelect.selectedOptions[0];
    if (!selected?.dataset.prefill) return;
    const values = JSON.parse(selected.dataset.prefill);
    for (const name of ["split", "goal", "training_days", "squat_frequency", "bench_frequency", "deadlift_frequency"]) {
      const control = form.elements.namedItem(name);
      if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement) {
        control.value = String(values[name]);
        control.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  });
  showGoldenChoice();

  const markPreviewStale = () => {
    if (!preview || dirty) return;
    dirty = true;
    preview.classList.add("is-stale");
    if (staleNotice) staleNotice.hidden = false;
    if (accept) {
      accept.disabled = true;
      accept.setAttribute("aria-disabled", "true");
    }
    if (state) {
      state.textContent = "Preview stale";
      state.classList.remove("is-ready", "is-error");
      state.classList.add("is-dirty");
    }
    if (reasonWrap) reasonWrap.hidden = false;
    if (reason instanceof HTMLTextAreaElement) reason.required = true;
  };

  // Install the safety boundary before optional factory UI setup. Delegation on
  // the canonical form also covers controls added or replaced after preview.
  const invalidateForMaterialInput = (event) => {
    if (event.target.name !== "override_reason") markPreviewStale();
  };
  form.addEventListener("input", invalidateForMaterialInput);
  form.addEventListener("change", invalidateForMaterialInput);

  const rows = factory.querySelector("[data-accessory-rows]");
  const template = factory.querySelector("[data-accessory-template]");
  const summary = factory.querySelector("[data-accessory-summary]");
  const updateSummary = () => {
    const count = rows.querySelectorAll(".factory-accessory-row").length;
    summary.textContent = count
      ? `${count} coach-selected assistance exercise${count === 1 ? "" : "s"}; manual choices replace automatic suggestions.`
      : "No assistance selected.";
  };
  const bind = (row) => {
    row.querySelector("[data-remove-accessory]").onclick = () => { row.remove(); updateSummary(); markPreviewStale(); };
    row.querySelector("[data-move-up]").onclick = () => { if (row.previousElementSibling) { rows.insertBefore(row, row.previousElementSibling); markPreviewStale(); } };
    row.querySelector("[data-move-down]").onclick = () => { if (row.nextElementSibling) { rows.insertBefore(row.nextElementSibling, row); markPreviewStale(); } };
  };
  rows.querySelectorAll(".factory-accessory-row").forEach(bind);
  factory.querySelector("[data-add-accessory]").onclick = () => {
    const row = template.content.firstElementChild.cloneNode(true);
    rows.append(row); bind(row); updateSummary(); markPreviewStale(); row.querySelector("select").focus();
  };
  factory.querySelector("[data-accessory-filter]").addEventListener("input", (event) => {
    const query = event.target.value.toLowerCase();
    factory.querySelectorAll("option[data-search]").forEach((option) => option.hidden = !option.dataset.search.toLowerCase().includes(query));
  });
  const errorSummary = form.querySelector("[data-error-summary]");
  if (errorSummary) {
    errorSummary.focus();
    const invalid = form.querySelector('[aria-invalid="true"]');
    errorSummary.querySelector("a")?.addEventListener("click", (event) => {
      event.preventDefault();
      invalid?.focus();
    });
    if (reason instanceof HTMLTextAreaElement && reason.getAttribute("aria-invalid") === "true") {
      reasonWrap.hidden = false;
      reason.required = true;
      reason.focus();
    }
  }
  updateSummary();
};

// `defer` normally runs before DOMContentLoaded. Initialise immediately when
// the form has already been parsed so input produced by another DOMContentLoaded
// observer cannot beat the dirty-state listener. Keep a fallback for non-defer
// or asynchronously injected use of this script.
if (document.readyState === "loading" && !document.querySelector("#block-factory-form")) {
  document.addEventListener("DOMContentLoaded", initialiseBlockFactory, { once: true });
} else {
  initialiseBlockFactory();
}
