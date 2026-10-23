(() => {
  const form = document.getElementById("run-form");
  const sourceSelect = document.getElementById("source");
  const statusElement = document.getElementById("form-status");
  const submitButton = document.getElementById("run-submit");

  function syncSourceFields() {
    if (!sourceSelect) return;
    const source = sourceSelect.value || "cdp";
    document.querySelectorAll("[data-source-field]").forEach((element) => {
      element.classList.toggle("hidden", element.dataset.sourceField !== source);
    });
  }

  function showStatus(message, isError = false) {
    if (!statusElement) return;
    statusElement.textContent = message;
    statusElement.classList.toggle("error", isError);
  }

  if (sourceSelect) {
    sourceSelect.addEventListener("change", syncSourceFields);
    syncSourceFields();
  }

  async function createRun(payload) {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      const detail = Array.isArray(error.detail)
        ? error.detail.map((item) => item.msg || item).join("; ")
        : error.detail;
      throw new Error(detail || `Не удалось создать задачу (HTTP ${response.status})`);
    }
    return response.json();
  }

  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const payload = {
        url: String(data.get("url") || "").trim(),
        source: String(data.get("source") || "cdp"),
        cdp_url: String(data.get("cdp_url") || "").trim() || null,
        timeout: Number(data.get("timeout") || 45),
        challenge_timeout: Number(data.get("challenge_timeout") || 120),
        headless: data.get("headless") === "on",
      };

      if (submitButton) submitButton.disabled = true;
      showStatus("Создаю задачу…");
      try {
        const run = await createRun(payload);
        window.location.href = `/runs/${run.id}`;
      } catch (error) {
        showStatus(error.message || "Не удалось создать задачу", true);
        if (submitButton) submitButton.disabled = false;
      }
    });
  }

  if (window.__RUN_ID__) {
    const runId = window.__RUN_ID__;
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/runs/${runId}`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const run = await response.json();
        if (run.status === "success" || run.status === "failed") {
          clearInterval(timer);
          window.location.reload();
        }
      } catch (_) {
        // Network hiccup: the next tick will retry.
      }
    }, 1500);
  }

  document.querySelectorAll("[data-rerun-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "Создаю…";
      try {
        const run = await createRun({
          url: button.dataset.rerunUrl,
          source: button.dataset.rerunSource || "cdp",
          cdp_url: button.dataset.rerunCdpUrl || null,
          timeout: 45,
          challenge_timeout: 120,
          headless: button.dataset.rerunHeadless === "true",
        });
        window.location.href = `/runs/${run.id}`;
      } catch (error) {
        button.disabled = false;
        button.textContent = originalText;
        alert(error.message || "Не удалось повторить парсинг");
      }
    });
  });
})();
