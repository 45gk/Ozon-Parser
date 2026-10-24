(() => {
  const form = document.getElementById("search-form");
  const sourceSelect = document.getElementById("search-source");
  const statusElement = document.getElementById("search-form-status");
  const submitButton = document.getElementById("search-submit");

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

  async function createSearch(payload) {
    const response = await fetch("/api/searches", {
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
      throw new Error(detail || `Не удалось создать поиск (HTTP ${response.status})`);
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
        limit: Number(data.get("limit") || 20),
        parse_products: data.get("parse_products") === "on",
        headless: data.get("headless") === "on",
      };

      if (submitButton) submitButton.disabled = true;
      showStatus("Создаю задачу…");
      try {
        const run = await createSearch(payload);
        window.location.href = `/searches/${run.id}`;
      } catch (error) {
        showStatus(error.message || "Не удалось создать поиск", true);
        if (submitButton) submitButton.disabled = false;
      }
    });
  }

  if (window.__SEARCH_RUN_ID__) {
    const runId = window.__SEARCH_RUN_ID__;
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/searches/${runId}`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const run = await response.json();
        if (run.status === "success" || run.status === "failed") {
          clearInterval(timer);
          window.location.reload();
        }
      } catch (_) {
        // Next polling tick will retry.
      }
    }, 1500);
  }

  document.querySelectorAll("[data-search-rerun-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "Создаю…";
      try {
        const run = await createSearch({
          url: button.dataset.searchRerunUrl,
          source: button.dataset.searchRerunSource || "cdp",
          cdp_url: button.dataset.searchRerunCdpUrl || null,
          limit: Number(button.dataset.searchRerunLimit || 20),
          parse_products: button.dataset.searchRerunParseProducts !== "false",
          headless: button.dataset.searchRerunHeadless === "true",
          timeout: 45,
          challenge_timeout: 120,
        });
        window.location.href = `/searches/${run.id}`;
      } catch (error) {
        button.disabled = false;
        button.textContent = originalText;
        alert(error.message || "Не удалось повторить поиск");
      }
    });
  });
})();
