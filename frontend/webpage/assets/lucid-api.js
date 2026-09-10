/**
 * lucid-api.js — browser client to MasterServer/RDP/Node via same-origin nginx → Proxy.
 * Proxy auth headers are injected by nginx from secrets; browser sends UserID/TokenID only.
 */
(function (global) {
  "use strict";

  function joinPath(base, path) {
    const b = String(base || "").replace(/\/+$/, "");
    const p = String(path || "");
    if (!p) return b;
    return `${b}${p.startsWith("/") ? p : `/${p}`}`;
  }

  function authHeaders() {
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    const session = global.LucidAuth && global.LucidAuth.getSession();
    if (session) {
      if (session.userId) headers["X-Lucid-UserID"] = session.userId;
      if (session.tokenId) headers["X-Lucid-TokenID"] = session.tokenId;
      if (session.role) headers["X-Lucid-Role"] = session.role;
    }
    const source = global.LucidConfig && global.LucidConfig.get("proxySource");
    if (source) headers["X-Lucid-Proxy-Source"] = source;
    return headers;
  }

  async function request(target, routePath, options) {
    const cfg = global.LucidConfig.runtime();
    const bases = {
      backend: cfg.proxyBackendPath,
      rdp: cfg.proxyRdpPath,
      node: cfg.proxyNodePath,
    };
    const base = bases[target];
    if (!base) {
      throw new Error(`proxy path for target '${target}' missing from runtime config`);
    }
    const method = (options && options.method) || (options && options.body ? "POST" : "GET");
    const url = joinPath(base, routePath);
    const init = {
      method,
      headers: { ...authHeaders(), ...((options && options.headers) || {}) },
      credentials: "same-origin",
    };
    if (options && options.body !== undefined) {
      init.body =
        typeof options.body === "string" ? options.body : JSON.stringify(options.body);
    }
    const response = await fetch(url, init);
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (_) {
      data = { raw: text };
    }
    if (!response.ok) {
      const err = new Error(
        (data && (data.detail || data.error || data.message)) ||
          `request failed (${response.status})`
      );
      err.status = response.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function backend(routePath, options) {
    return request("backend", routePath, options);
  }

  function rdp(routePath, options) {
    return request("rdp", routePath, options);
  }

  function node(routePath, options) {
    return request("node", routePath, options);
  }

  function named(apiName, options) {
    const path = global.LucidConfig.apiRoute(apiName);
    return backend(path, options);
  }

  global.LucidApi = {
    request,
    backend,
    rdp,
    node,
    named,
    joinPath,
  };
})(typeof window !== "undefined" ? window : globalThis);
