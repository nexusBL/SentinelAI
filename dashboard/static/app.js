document.addEventListener("DOMContentLoaded", () => {
  const submitButton = document.querySelector("[data-run-submit]");
  const runForm = document.querySelector("[data-run-form]");
  if (runForm && submitButton) {
    runForm.addEventListener("submit", () => {
      submitButton.disabled = true;
      submitButton.textContent = "Running SentinelAI...";
    });
  }

  document.querySelectorAll("[data-copy-text]").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy-text") || "";
      try {
        await navigator.clipboard.writeText(text);
        const original = button.textContent;
        button.textContent = "Copied";
        setTimeout(() => {
          button.textContent = original;
        }, 1200);
      } catch (error) {
        console.error("copy failed", error);
      }
    });
  });

  const filterInput = document.getElementById("run-filter");
  if (filterInput) {
    filterInput.addEventListener("input", () => {
      const query = filterInput.value.trim().toLowerCase();
      document.querySelectorAll("#runs-table tbody tr").forEach((row) => {
        const haystack = (row.getAttribute("data-filter-text") || "").toLowerCase();
        row.style.display = haystack.includes(query) ? "" : "none";
      });
    });
  }
});
