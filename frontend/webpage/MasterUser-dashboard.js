/**
 * MasterUser-dashboard.js — MasterUserID home: modes, maintenance (Admin approval), Node_mode hash.
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
    const session = LucidAuth.requireAuth({ roles: ["masteruser", "master"] });
    if (!session) return;
    mountShell({ active: "masterUserDashboard" });

    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const ok = el("p", { className: "noe-ok", text: "" });
    ok.hidden = true;
    const modeLabel = el("span", { className: "noe-chip", text: `mode: ${LucidAuth.getMode()}` });
    const clock = el("span", { className: "noe-chip", text: "" });
    const reports = el("div", { className: "noe-panel", text: "System reports route to AdminID." });
    const hashKey = el("input", { id: "nodeHash", type: "password", placeholder: "Node_mode hash key" });
    const maintNote = el("textarea", {
      id: "maint",
      placeholder: "Describe maintenance change for AdminID approval",
    });

    function tick() {
      const parts = nowParts();
      clock.textContent = `${parts.date} · ${parts.time}`;
    }
    tick();
    window.setInterval(tick, 1000);

    function setMode(mode) {
      err.hidden = true;
      if (mode === "node") {
        if (!hashKey.value.trim()) {
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
        onclick: () => setMode("user"),
      }),
      el("button", {
        className: "noe-btn noe-btn-ghost",
        type: "button",
        text: "Node",
        onclick: () => setMode("node"),
      }),
      el("button", {
        className: "noe-btn noe-btn-ghost",
        type: "button",
        text: "MasterUser",
        onclick: () => setMode("masteruser"),
      }),
    ]);

    const requestApproval = el("button", {
      className: "noe-btn noe-btn-primary",
      type: "button",
      text: "Request AdminID approval",
      onclick: async () => {
        err.hidden = true;
        ok.hidden = true;
        try {
          await LucidApi.backend("/masteruser/approval-request", {
            method: "POST",
            body: {
              MasterUserID: session.userId,
              TokenID: session.tokenId,
              mode: LucidAuth.getMode(),
              change_request: maintNote.value.trim(),
            },
          });
          ok.hidden = false;
          ok.textContent = "Approval alert sent to AdminID.";
        } catch (ex) {
          err.hidden = false;
          showError(err, ex.message || "approval request failed");
        }
      },
    });

    LucidShell.setContent(
      el("section", { className: "noe-layout noe-layout-sidebar" }, [
        el("aside", { className: "noe-sidebar" }, [
          modeLabel,
          clock,
          el("span", {
            className: "noe-chip warn",
            text: "MasterUserID modifications need AdminID approval",
          }),
          el("div", { className: "noe-field" }, [
            el("label", { for: "nodeHash", text: "Node_mode hash key" }),
            hashKey,
          ]),
          reports,
        ]),
        el("div", { className: "noe-layout" }, [
          el("h2", { text: "MasterUser dashboard" }),
          el("p", {
            className: "noe-muted",
            text: "User features plus MasterUser mode. Node_mode acts as NodeID = MasterUserID.",
          }),
          err,
          ok,
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
              href: LucidConfig.page("lucidLedger"),
              text: "Ledger",
            }),
          ]),
          el("section", { className: "noe-panel noe-form" }, [
            el("h3", { text: "In-container maintenance" }),
            el("p", {
              className: "noe-muted",
              text: "High-level system access. Submit change notes; AdminID must approve before apply.",
            }),
            el("div", { className: "noe-field" }, [
              el("label", { for: "maint", text: "Change request" }),
              maintNote,
            ]),
            requestApproval,
          ]),
        ]),
      ])
    );
  }

  document.addEventListener("DOMContentLoaded", render);
})();
