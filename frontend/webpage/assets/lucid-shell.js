/**
 * lucid-shell.js — shared header/footer/nav chrome for LucidTops Noé Dark pages.
 */
(function (global) {
  "use strict";

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.entries(attrs).forEach(([key, value]) => {
        if (key === "className") node.className = value;
        else if (key === "text") node.textContent = value;
        else if (key.startsWith("on") && typeof value === "function") {
          node.addEventListener(key.slice(2).toLowerCase(), value);
        } else if (value !== undefined && value !== null) {
          node.setAttribute(key, value);
        }
      });
    }
    (children || []).forEach((child) => {
      if (child == null) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function statusChip() {
    const cfg = global.LucidConfig.runtime();
    const session = global.LucidAuth.getSession();
    const onion = cfg.frontendOnion;
    const chips = [];
    chips.push(
      el("span", {
        className: onion ? "noe-chip ok" : "noe-chip warn",
        text: onion ? `onion ready` : "onion pending",
      })
    );
    if (session && session.tokenId) {
      chips.push(
        el("span", {
          className: "noe-chip ok",
          text: `${session.role || "user"} · ${session.userId.slice(0, 6)}…`,
        })
      );
    }
    return chips;
  }

  function navLinks(active) {
    const pages = global.LucidConfig.runtime().pages;
    const session = global.LucidAuth.getSession();
    const links = [];
    if (!session) {
      links.push(["home", pages.home, "Home"]);
      links.push(["login", pages.login, "Login"]);
      links.push(["register", pages.register, "Register"]);
    } else {
      links.push(["dashboard", pages.dashboard, "Dashboard"]);
      links.push(["findPeer", pages.findPeer, "Sessions"]);
      links.push(["settings", pages.settings, "Settings"]);
      links.push(["lucidLedger", pages.lucidLedger, "Ledger"]);
      links.push(["lucidMarket", pages.lucidMarket, "Market"]);
      const role = global.LucidAuth.detectRole(session);
      if (role === "admin") links.push(["adminHome", pages.adminHome, "Admin"]);
      if (role === "masteruser" || role === "master") {
        links.push(["masterUserDashboard", pages.masterUserDashboard, "Master"]);
      }
      links.push(["logout", pages.logout, "Logout"]);
    }
    return links.map(([key, href, label]) =>
      el("a", { href, className: active === key ? "active" : "", text: label })
    );
  }

  function mountShell(options) {
    const opts = options || {};
    const brand = global.LucidConfig.brandName();
    const root = document.getElementById("app") || document.body;
    root.innerHTML = "";
    const main = el("main", { className: "noe-main", id: "noe-main" });
    const shell = el("div", { className: "noe-shell" }, [
      el("header", { className: "noe-header" }, [
        el("a", { className: "noe-brand", href: global.LucidConfig.page("home") }, [
          el("span", { text: brand }),
        ]),
        el("nav", { className: "noe-nav" }, navLinks(opts.active)),
        el("div", { className: "noe-nav" }, statusChip()),
      ]),
      main,
      el("footer", { className: "noe-footer" }, [
        el("span", { text: `${brand} · Tor self-hosted` }),
        el("span", {
          className: "noe-muted",
          text: global.LucidConfig.get("pulledAt")
            ? `ops ${String(global.LucidConfig.get("pulledAt")).slice(0, 19)}`
            : "",
        }),
      ]),
    ]);
    root.appendChild(shell);
    return main;
  }

  function setContent(node) {
    const main = document.getElementById("noe-main");
    if (!main) return;
    main.innerHTML = "";
    if (Array.isArray(node)) node.forEach((n) => main.appendChild(n));
    else if (node) main.appendChild(node);
  }

  function showError(target, message) {
    let box = target;
    if (!box) {
      box = document.createElement("p");
      box.className = "noe-error";
      const main = document.getElementById("noe-main");
      if (main) main.prepend(box);
    }
    box.className = "noe-error";
    box.textContent = message || "request failed";
    return box;
  }

  global.LucidShell = {
    el,
    mountShell,
    setContent,
    showError,
    statusChip,
  };
})(typeof window !== "undefined" ? window : globalThis);
