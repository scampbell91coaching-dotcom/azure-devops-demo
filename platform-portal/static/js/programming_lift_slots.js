document.querySelectorAll("[data-lift-slot-editor]").forEach((editor) => {
  const family = editor.querySelector("[data-lift-family]");
  const backToggle = editor.querySelector("[data-back-off-toggle]");
  const backFields = editor.querySelector("[data-back-off-fields]");

  const syncFamily = () => {
    editor.querySelectorAll("[data-family-exercise]").forEach((select) => {
      Array.from(select.options).forEach((option) => {
        const allowed = !option.dataset.family || option.dataset.family === family.value;
        option.hidden = !allowed;
        option.disabled = !allowed;
      });
      if (select.selectedOptions[0]?.disabled) {
        select.value = select.querySelector(`option[data-family="${family.value}"]`)?.value || "";
      }
    });
  };
  const syncBackOff = () => {
    backFields.hidden = !backToggle.checked;
    backFields.querySelectorAll("input, select").forEach((field) => {
      field.disabled = !backToggle.checked;
    });
  };
  const syncRpe = (select) => {
    const group = select.closest("fieldset, [data-back-off-fields]");
    group.querySelectorAll("[data-rpe-target]").forEach((field) => {
      field.hidden = select.value === "range";
      field.querySelector("input").disabled = select.value === "range";
    });
    group.querySelectorAll("[data-rpe-range]").forEach((field) => {
      field.hidden = select.value !== "range";
      field.querySelector("input").disabled = select.value !== "range";
    });
  };

  family.addEventListener("change", syncFamily);
  backToggle.addEventListener("change", syncBackOff);
  editor.querySelectorAll("[data-rpe-mode]").forEach((select) => {
    select.addEventListener("change", () => syncRpe(select));
    syncRpe(select);
  });
  syncFamily();
  syncBackOff();
});
