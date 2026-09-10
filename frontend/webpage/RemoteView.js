/**
 * RemoteView.js — active SessionID remote view surface; controls from settings; RDP via Proxy.
 */
(function () {
  "use strict";

  function loadSettings() {
    try {
      return JSON.parse(sessionStorage.getItem("lucid.sessionSettings") || "{}");
    } catch (_) {
      return {};
    }
  }

  function render() {
    const { el, mountShell, showError } = LucidShell;
    const session = LucidAuth.requireAuth();
    if (!session) return;
    mountShell({ active: "findPeer" });

    const sid = sessionStorage.getItem("lucid.activeSessionId") || "";
    const settings = loadSettings();
    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const status = el("p", { className: "noe-muted", text: "Connecting via Proxy → Rdp…" });
    const stage = el("div", {
      className: "noe-remote-stage",
      id: "remote-stage",
      text: sid ? `Session ${sid}` : "No SessionID",
    });

    const endBtn = el("button", {
      className: "noe-btn noe-btn-danger",
      type: "button",
      text: "End session",
    });
    const discBtn = el("button", {
      className: "noe-btn noe-btn-ghost",
      type: "button",
      text: "Disconnect",
    });

    async function rdpAttach() {
      if (!sid) {
        err.hidden = false;
        showError(err, "SessionID required");
        return;
      }
      try {
        const data = await LucidApi.rdp("/session-attach", {
          method: "POST",
          body: {
            UserID: session.userId,
            TokenID: session.tokenId,
            SessionID: sid,
            Session_settings: settings,
          },
        });
        status.textContent = data.status || data.message || "Rdp attach accepted";
        stage.textContent = `Live · ${sid} · mouse=${!!settings.mouse} keyboard=${!!settings.keyboard}`;
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "Rdp attach failed");
        status.textContent = "Rdp unavailable — check Proxy frontend/rdp route";
      }
    }

    endBtn.addEventListener("click", async () => {
      try {
        await LucidApi.named("sessionEnd", {
          method: "POST",
          body: { UserID: session.userId, TokenID: session.tokenId, SessionID: sid },
        });
      } catch (_) {
        /* still clear local */
      }
      sessionStorage.removeItem("lucid.activeSessionId");
      window.location.href = LucidConfig.page("dashboard");
    });

    discBtn.addEventListener("click", async () => {
      try {
        await LucidApi.named("sessionDisconnect", {
          method: "POST",
          body: { UserID: session.userId, TokenID: session.tokenId, SessionID: sid },
        });
      } catch (_) {
        /* ignore */
      }
      window.location.href = LucidConfig.page("findPeer");
    });

    LucidShell.setContent(
      el("section", { className: "noe-layout" }, [
        el("header", {}, [
          el("h2", { text: "Remote view" }),
          status,
          err,
        ]),
        stage,
        el("div", { className: "noe-cta-row" }, [
          el("a", {
            className: "noe-btn noe-btn-ghost",
            href: LucidConfig.page("settings"),
            text: "Settings",
          }),
          discBtn,
          endBtn,
        ]),
      ])
    );

    rdpAttach();
  }

  document.addEventListener("DOMContentLoaded", render);
})();
