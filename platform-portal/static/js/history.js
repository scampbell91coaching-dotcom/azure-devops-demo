async function loadHistory() {
  const response = await fetch("/api/v1/history", { cache: "no-store" });
  if (!response.ok) throw new Error("Unable to load history");
  return response.json();
}

loadHistory()
  .then(data => {
    document.getElementById("history-status").textContent =
      `${data.items.length} items loaded`;
  })
  .catch(error => {
    document.getElementById("history-status").textContent = error.message;
  });
