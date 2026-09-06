document.querySelectorAll("[data-programme-revision]").forEach((workspace) => {
  const revision = workspace.dataset.programmeRevision;
  workspace.querySelectorAll('form[method="post"], form[method="POST"]').forEach((form) => {
    if (form.elements.namedItem("expected_revision")) return;
    const token = document.createElement("input");
    token.type = "hidden";
    token.name = "expected_revision";
    token.value = revision;
    form.appendChild(token);
  });
});
