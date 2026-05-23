(function () {
  const STORAGE_KEY = "rrt-docs-theme";
  const root = document.documentElement;

  const safeStorageRead = () => {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  };

  const safeStorageWrite = (theme) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Best-effort persistence only.
    }
  };

  const safeStorageRemove = () => {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Best-effort persistence only.
    }
  };

  const readStoredTheme = () => {
    const value = safeStorageRead();
    return value === "light" || value === "dark" ? value : null;
  };

  const applyTheme = (theme) => {
    if (theme === "light" || theme === "dark") {
      root.dataset.theme = theme;
      return;
    }
    if (theme === "auto") {
      delete root.dataset.theme;
      return;
    }
    delete root.dataset.theme;
  };

  const currentTheme = () => {
    if (root.dataset.theme === "light" || root.dataset.theme === "dark") {
      return root.dataset.theme;
    }
    return readStoredTheme() || "auto";
  };

  const nextTheme = (theme) => {
    if (theme === "auto") return "dark";
    if (theme === "dark") return "light";
    return "auto";
  };

  const iconForTheme = (theme) => {
    if (theme === "dark") return "☾";
    if (theme === "light") return "☀";
    return "◐";
  };

  const labelForTheme = (theme) => {
    if (theme === "dark") return "Switch to light theme";
    if (theme === "light") return "Switch to auto theme";
    return "Switch to dark theme";
  };

  const renderButton = () => {
    if (document.getElementById("reto-theme-toggle")) return;
    const button = document.createElement("button");
    button.id = "reto-theme-toggle";
    button.type = "button";

    const syncButton = () => {
      const theme = currentTheme();
      button.textContent = iconForTheme(theme);
      button.setAttribute("aria-label", labelForTheme(theme));
      button.title = labelForTheme(theme);
    };

    button.addEventListener("click", () => {
      const theme = nextTheme(currentTheme());
      if (theme === "auto") {
        safeStorageRemove();
        applyTheme("auto");
      } else {
        safeStorageWrite(theme);
        applyTheme(theme);
      }
      syncButton();
    });

    syncButton();
    document.body.appendChild(button);
  };

  applyTheme(readStoredTheme() || "auto");
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderButton, { once: true });
  } else {
    renderButton();
  }
})();
