document.addEventListener("DOMContentLoaded", () => {
  const builder = document.querySelector("[data-session-builder]");

  if (!builder) {
    return;
  }

  const sessionId = builder.dataset.sessionId;
  const list = builder.querySelector("[data-prescription-list]");
  const newRowForm = builder.querySelector("[data-new-prescription-form]");
  const status = builder.querySelector("[data-autosave-status]");
  const suggestions = builder.querySelector("[data-exercise-suggestions]");
  let draggedRow = null;
  let saveTimer = null;

  const setStatus = (message, state = "") => {
    status.textContent = message;
    status.classList.remove("is-saving", "is-error");

    if (state) {
      status.classList.add(state);
    }
  };

  const api = async (url, options = {}) => {
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    if (response.status === 204) {
      return null;
    }

    return response.json();
  };

  const rowPayload = (row) => {
    const payload = {};

    row.querySelectorAll("[data-autosave-field]").forEach((field) => {
      payload[field.name] = field.value;
    });

    return payload;
  };

  const saveRow = async (row) => {
    setStatus("Saving…", "is-saving");

    try {
      await api(
        `/programming/api/prescriptions/${row.dataset.prescriptionId}`,
        {
          method: "PATCH",
          body: JSON.stringify(rowPayload(row)),
        }
      );

      setStatus("Saved");
    } catch {
      setStatus("Save failed", "is-error");
    }
  };

  const scheduleSave = (row) => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveRow(row), 450);
  };

  const saveOrder = async () => {
    const ids = Array.from(
      list.querySelectorAll("[data-prescription-row]")
    ).map((row) => Number(row.dataset.prescriptionId));

    if (!ids.length) {
      return;
    }

    try {
      await api(`/programming/api/sessions/${sessionId}/reorder`, {
        method: "POST",
        body: JSON.stringify({ prescription_ids: ids }),
      });
      setStatus("Saved");
    } catch {
      setStatus("Order failed", "is-error");
    }
  };

  const bindRow = (row) => {
    row.querySelectorAll("[data-autosave-field]").forEach((field) => {
      field.addEventListener("input", () => scheduleSave(row));
      field.addEventListener("change", () => scheduleSave(row));
    });

    row.querySelector("[data-delete-prescription]")?.addEventListener(
      "click",
      async () => {
        if (!confirm("Delete this exercise?")) {
          return;
        }

        try {
          await api(
            `/programming/api/prescriptions/${row.dataset.prescriptionId}`,
            { method: "DELETE" }
          );
          row.remove();
          await saveOrder();
          setStatus("Saved");
        } catch {
          setStatus("Delete failed", "is-error");
        }
      }
    );

    row.addEventListener("dragstart", () => {
      draggedRow = row;
      row.classList.add("is-dragging");
    });

    row.addEventListener("dragend", async () => {
      row.classList.remove("is-dragging");
      draggedRow = null;
      await saveOrder();
    });

    row.addEventListener("dragover", (event) => {
      event.preventDefault();

      if (!draggedRow || draggedRow === row) {
        return;
      }

      const bounds = row.getBoundingClientRect();
      const after = event.clientY > bounds.top + bounds.height / 2;

      list.insertBefore(
        draggedRow,
        after ? row.nextSibling : row
      );
    });
  };

  const makeRow = (item) => {
    const row = document.createElement("div");
    row.className = "programming-sheet__row";
    row.draggable = true;
    row.dataset.prescriptionRow = "";
    row.dataset.prescriptionId = item.id;

    row.innerHTML = `
      <div class="sheet-exercise-cell">
        <button class="drag-handle" type="button">⋮⋮</button>
        <input name="exercise_name" list="exercise-suggestions" data-autosave-field>
      </div>
      <input name="sets" type="number" data-autosave-field>
      <input name="reps" data-autosave-field>
      <input name="load_kg" type="number" step="0.5" data-autosave-field>
      <input name="percentage" type="number" step="0.1" data-autosave-field>
      <input name="rpe" type="number" step="0.5" data-autosave-field>
      <input name="tempo" data-autosave-field>
      <input name="rest_seconds" type="number" data-autosave-field>
      <textarea name="notes" rows="1" data-autosave-field></textarea>
      <button class="sheet-delete-button" type="button" data-delete-prescription>×</button>
    `;

    Object.entries(item).forEach(([name, value]) => {
      const field = row.querySelector(`[name="${name}"]`);

      if (field && value !== null) {
        field.value = value;
      }
    });

    return row;
  };

  newRowForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const payload = Object.fromEntries(new FormData(newRowForm).entries());
    setStatus("Adding…", "is-saving");

    try {
      const item = await api(
        `/programming/api/sessions/${sessionId}/prescriptions`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );

      const row = makeRow(item);
      list.appendChild(row);
      bindRow(row);
      newRowForm.reset();
      newRowForm.elements.exercise_name.focus();
      setStatus("Saved");
    } catch {
      setStatus("Add failed", "is-error");
    }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();

      const activeRow = document.activeElement?.closest(
        "[data-prescription-row]"
      );

      if (activeRow) {
        saveRow(activeRow);
      }
    }
  });

  let suggestionTimer = null;

  builder.addEventListener("input", (event) => {
    if (event.target.name !== "exercise_name") {
      return;
    }

    clearTimeout(suggestionTimer);

    suggestionTimer = setTimeout(async () => {
      try {
        const names = await api(
          `/programming/api/exercises?q=${encodeURIComponent(event.target.value)}`
        );

        suggestions.innerHTML = "";

        names.forEach((name) => {
          const option = document.createElement("option");
          option.value = name;
          suggestions.appendChild(option);
        });
      } catch {
        // Suggestions are optional.
      }
    }, 200);
  });

  list.querySelectorAll("[data-prescription-row]").forEach(bindRow);
});
