/**
 * AdminHome.js — AdminID home: modes, ops CLI (operations only), approvals sidebar.
 * Node_mode requires hash key verification.
 */
(function () {
  "use strict";

  function nowParts() {
    const d = new Date();
    return {
      date: d.toLocaleDateString(),
      time: d.toLocaleTimeString(),
    };
  }

  function render() {
    const { el, mountShell, showError } = LucidShell;
    const session = LucidAuth.requireAuth({ roles: ["admin"] });
    if (!session) return;
    mountShell({ active: "adminHome" });

    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const modeLabel = el("span", { className: "noe-chip", text: `mode: ${LucidAuth.getMode()}` });
    const clock = el("span", { className: "noe-chip", text: "" });
    const reports = el("div", { className: "noe-panel", text: "No pending system reports." });
    const cliOut = el("pre", { className: "noe-cli", text: "" });
    const cliIn = el("input", {
      id: "cli",
      placeholder: "operations command (no blockchain)",
    });
    const hashKey = el("input", { id: "nodeHash", type: "password", placeholder: "Node_mode hash key" });

    function tick() {
      const parts = nowParts();
      clock.textContent = `${parts.date} · ${parts.time}`;
    }
    tick();
    window.setInterval(tick, 1000);

    function setMode(mode) {
      err.hidden = true;
      if (mode === "node") {
        const key = hashKey.value.trim();
        if (!key) {
          err.hidden = false;
          showError(err, "Node_mode requires hash key verification");
          return;
        }
        sessionStorage.setItem("lucid.nodeModeHashVerified", "1");
      }
      LucidAuth.setMode(mode);
      modeLabel.textContent = `mode: ${mode}`;
    }

    const modeRow = el("div", { className: "noe-switch-row" }, [
      el("button", {
        className: "noe-btn noe-btn-ghost",
        type: "button",
        text: "User",
        "aria-pressed": "false",
        onclick: () => setMode("user"),
      }),
      el("button", {
        className: "noe-btn noe-btn-ghost",
        type: "button",
        text: "Node",
        "aria-pressed": "false",
        onclick: () => setMode("node"),
      }),
      el("button", {
        className: "noe-btn noe-btn-ghost",
        type: "button",
        text: "MasterUser",
        "aria-pressed": "false",
        onclick: () => setMode("masteruser"),
      }),
      el("button", {
        className: "noe-btn noe-btn-ghost",
        type: "button",
        text: "Admin",
        "aria-pressed": "true",
        onclick: () => setMode("admin"),
      }),
    ]);

    const runCli = el("button", {
      className: "noe-btn noe-btn-primary",
      type: "button",
      text: "Run operations command",
      onclick: async () => {
        err.hidden = true;
        const cmd = cliIn.value.trim();
        if (!cmd) return;
        if (/blockchain|ledger|block/i.test(cmd)) {
          err.hidden = false;
          showError(err, "blockchain operations excluded from Admin CLI");
          return;
        }
        try {
          const data = await LucidApi.backend("/admin/operations-cli", {
            method: "POST",
            body: {
              AdminID: session.userId,
              TokenID: session.tokenId,
              command: cmd,
              mode: LucidAuth.getMode(),
            },
          });
          cliOut.textContent = JSON.stringify(data, null, 2);
        } catch (ex) {
          err.hidden = false;
          showError(err, ex.message || "operations CLI failed");
        }
      },
    });

    async function loadReports() {
      try {
        const data = await LucidApi.backend("/admin/reports", {
          method: "POST",
          body: { AdminID: session.userId, TokenID: session.tokenId },
        });
        const items = data.reports || data.items || [];
        reports.textContent = items.length
          ? items.map((r) => `• ${r.summary || r.message || JSON.stringify(r)}`).join("\n")
          : "No pending system reports.";
      } catch (_) {
        reports.textContent = "Reports channel idle / unavailable.";
      }
    }

    LucidShell.setContent(
      el("section", { className: "noe-layout noe-layout-sidebar" }, [
        el("aside", { className: "noe-sidebar" }, [
          modeLabel,
          clock,
          el("span", {
            className: "noe-chip warn",
            text: "AdminID approval required for modifications",
          }),
          el("div", { className: "noe-field" }, [
            el("label", { for: "nodeHash", text: "Node_mode hash key" }),
            hashKey,
          ]),
          reports,
        ]),
        el("div", { className: "noe-layout" }, [
          el("h2", { text: "Admin home" }),
          el("p", {
            className: "noe-muted",
            text: "User features plus Admin mode controls. Ops CLI limited to operations container.",
          }),
          err,
          modeRow,
          el("div", { className: "noe-cta-row" }, [
            el("a", {
              className: "noe-btn noe-btn-ghost",
              href: LucidConfig.page("dashboard"),
              text: "User dashboard",
            }),
            el("a", {
              className: "noe-btn noe-btn-ghost",
              href: LucidConfig.page("findPeer"),
              text: "Sessions",
            }),
            el("a", {
              className: "noe-btn noe-btn-ghost",
              href: LucidConfig.page("lucidMarket"),
              text: "Market / payments",
            }),
          ]),
          el("section", { className: "noe-panel noe-form" }, [
            el("h3", { text: "Operations CLI" }),
            el("div", { className: "noe-field" }, [
              el("label", { for: "cli", text: "Command" }),
              cliIn,
            ]),
            runCli,
            cliOut,
          ]),
          el("section", { className: "noe-panel" }, [
            el("h3", { text: "In-container maintenance" }),
            el("p", {
              className: "noe-muted",
              text: "Admin_mode: full maintenance access. Changes that require dual control notify other AdminID.",
            }),
          ]),
        ]),
      ])
    );
    loadReports();
  }

  document.addEventListener("DOMContentLoaded", render);
})();
