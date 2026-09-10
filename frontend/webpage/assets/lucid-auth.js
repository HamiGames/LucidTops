/**
 * lucid-auth.js — TokenID session storage, role detection, route guards.
 */
(function (global) {
  "use strict";

  const STORAGE_KEY = "lucid.session";
  const MODE_KEY = "lucid.mode";

  function readStore(remember) {
    try {
      if (remember === false) return null;
      const raw = localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function getSession() {
    return readStore(true);
  }

  function setSession(session, remember) {
    const payload = {
      userId: session.userId || session.UserID || "",
      tokenId: session.tokenId || session.TokenID || session.IDToken || "",
      role: session.role || session.Role || "user",
      tierSelected: session.tierSelected ?? session.Tier_selected ?? null,
      email: session.email || "",
      savedAt: new Date().toISOString(),
    };
    const raw = JSON.stringify(payload);
    sessionStorage.setItem(STORAGE_KEY, raw);
    if (remember) {
      localStorage.setItem(STORAGE_KEY, raw);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    return payload;
  }

  function clearSession() {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(MODE_KEY);
  }

  function detectRole(payload) {
    if (!payload) return "user";
    if (payload.role) return String(payload.role).toLowerCase();
    const tier = Number(payload.tierSelected);
    if (tier === 8) return "admin";
    if (tier === 7) return "masteruser";
    if (payload.nodeId || payload.NodeID) return "node";
    return "user";
  }

  function homeForRole(role) {
    const pages = global.LucidConfig.runtime().pages;
    switch (String(role || "").toLowerCase()) {
      case "admin":
        return pages.adminHome;
      case "masteruser":
      case "master":
        return pages.masterUserDashboard;
      default:
        return pages.dashboard;
    }
  }

  function requireAuth(options) {
    const session = getSession();
    if (!session || !session.tokenId || !session.userId) {
      global.location.href = global.LucidConfig.page("login");
      return null;
    }
    if (options && options.roles && options.roles.length) {
      const role = detectRole(session);
      if (!options.roles.map((r) => r.toLowerCase()).includes(role)) {
        global.location.href = homeForRole(role);
        return null;
      }
    }
    return session;
  }

  function getMode() {
    return sessionStorage.getItem(MODE_KEY) || "user";
  }

  function setMode(mode) {
    const allowed = ["user", "node", "admin", "masteruser"];
    const next = String(mode || "user").toLowerCase();
    if (!allowed.includes(next)) {
      throw new Error("invalid operating mode");
    }
    sessionStorage.setItem(MODE_KEY, next);
    return next;
  }

  global.LucidAuth = {
    getSession,
    setSession,
    clearSession,
    detectRole,
    homeForRole,
    requireAuth,
    getMode,
    setMode,
  };
})(typeof window !== "undefined" ? window : globalThis);
