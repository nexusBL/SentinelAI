document.addEventListener("DOMContentLoaded", () => {
  const submitButton = document.querySelector("[data-run-submit]");
  const runForm = document.querySelector("[data-run-form]");
  if (runForm && submitButton) {
    runForm.addEventListener("submit", () => {
      submitButton.disabled = true;
      submitButton.textContent = "Queueing Run...";
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

  const jobWatch = document.querySelector("[data-job-watch]");
  if (jobWatch) {
    const jobId = jobWatch.getAttribute("data-job-watch");
    const progressBar = document.querySelector("[data-job-progress-bar]");
    const progressLabel = document.querySelector("[data-job-progress-label]");
    const message = document.querySelector("[data-job-message]");
    const statusBadge = document.querySelector("[data-job-status-badge]");
    const startedAt = document.querySelector("[data-job-started]");
    const completedAt = document.querySelector("[data-job-completed]");
    const failure = document.querySelector("[data-job-failure]");
    const jsonBlock = document.querySelector("[data-job-json]");

    const updateJob = async () => {
      const response = await fetch(`/api/jobs/${jobId}`);
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      const job = payload.job;
      const percent = job.progress?.percent || 0;

      if (progressBar) progressBar.style.width = `${percent}%`;
      if (progressLabel) progressLabel.textContent = `${percent}%`;
      if (message) message.textContent = job.progress?.message || job.status;
      if (startedAt) startedAt.textContent = job.started_at || "Pending";
      if (completedAt) completedAt.textContent = job.completed_at || "Pending";
      if (statusBadge) {
        statusBadge.textContent = job.status.toUpperCase();
        statusBadge.className = `badge ${job.status}`;
      }
      if (failure && job.failure_reason) {
        failure.textContent = job.failure_reason;
        failure.classList.remove("hidden");
      }
      if (jsonBlock) {
        jsonBlock.textContent = JSON.stringify(job, null, 2);
      }
      if (job.run_id && (job.status === "completed" || job.status === "failed")) {
        const actions = document.querySelector(".header-actions");
        if (actions && !actions.querySelector("[data-open-run-link]")) {
          const link = document.createElement("a");
          link.className = "button primary";
          link.href = `/runs/${job.run_id}`;
          link.textContent = "Open Run Detail";
          link.setAttribute("data-open-run-link", "true");
          actions.appendChild(link);
        }
      }
      if (["completed", "failed", "cancelled"].includes(job.status)) {
        clearInterval(interval);
      }
    };

    const interval = setInterval(updateJob, 2500);
    updateJob().catch((error) => console.error("job polling failed", error));
  }

  document.querySelectorAll("[data-cancel-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = button.getAttribute("data-cancel-job");
      button.disabled = true;
      await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
      button.textContent = "Cancel Requested";
    });
  });
});
