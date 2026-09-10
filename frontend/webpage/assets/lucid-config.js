/**
 * lucid-config.js — read runtime values generated at time of operation.
 * Source: /assets/runtime-config.js → window.__LUCID_RUNTIME__
 */
(function (global) {
  "use strict";

  function runtime() {
    const cfg = global.__LUCID_RUNTIME__;
    if (!cfg || typeof cfg !== "object") {
      throw new Error(
        "Lucid runtime config missing — run bootstrap_frontend / pull_information at time of operation"
      );
    }
    return cfg;
  }

  function get(path, fallback) {
    const parts = String(path).split(".");
    let cur = runtime();
    for (const part of parts) {
      if (cur == null || typeof cur !== "object" || !(part in cur)) {
        return fallback;
      }
      cur = cur[part];
    }
    return cur === undefined ? fallback : cur;
  }

  function page(name) {
    const pages = runtime().pages || {};
    const href = pages[name];
    if (!href) {
      throw new Error(`page route '${name}' missing from runtime config`);
    }
    return href;
  }

  function apiRoute(name) {
    const routes = runtime().apiRoutes || {};
    const path = routes[name];
    if (!path) {
      throw new Error(`api route '${name}' missing from runtime config`);
    }
    return path;
  }

  global.LucidConfig = {
    runtime,
    get,
    page,
    apiRoute,
    brandName() {
      return get("brandName", "LucidTops");
    },
    tiers() {
      return get("tiers", []);
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
