/**
 * find-peer.js — create SessionID + find peer via MasterServer user-session routes.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell, showError } = LucidShell;
    const session = LucidAuth.requireAuth();
    if (!session) return;
    mountShell({ active: "findPeer" });

    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const result = el("p", { className: "noe-ok", text: "" });
    result.hidden = true;
    const sessionIdInput = el("input", {
      id: "sessionId",
      placeholder: "SessionID",
      autocomplete: "off",
    });

    const createBtn = el("button", {
      className: "noe-btn noe-btn-primary",
      type: "button",
      text: "Create SessionID",
    });
    const findBtn = el("button", {
      className: "noe-btn noe-btn-ghost",
      type: "button",
      text: "Find peer",
    });

    createBtn.addEventListener("click", async () => {
      err.hidden = true;
      result.hidden = true;
      try {
        const data = await LucidApi.named("sessionCreate", {
          method: "POST",
          body: {
            UserID: session.userId,
            TokenID: session.tokenId,
            Host_UserID: session.userId,
          },
        });
        const sid = data.SessionID || data.sessionId;
        if (sid) {
          sessionIdInput.value = String(sid);
          sessionStorage.setItem("lucid.activeSessionId", String(sid));
        }
        result.hidden = false;
        result.textContent = `SessionID ready: ${sid || "(see response)"}`;
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "session create failed (tier limit?)");
      }
    });

    findBtn.addEventListener("click", async () => {
      err.hidden = true;
      result.hidden = true;
      const sid = sessionIdInput.value.trim();
      if (!sid) {
        err.hidden = false;
        showError(err, "SessionID required");
        return;
      }
      try {
        const data = await LucidApi.named("sessionFind", {
          method: "POST",
          body: {
            UserID: session.userId,
            TokenID: session.tokenId,
            SessionID: sid,
            Viewer_UserID: session.userId,
          },
        });
        sessionStorage.setItem("lucid.activeSessionId", sid);
        if (data.SessionID) sessionStorage.setItem("lucid.activeSessionId", String(data.SessionID));
        window.location.href = LucidConfig.page("connectHandshake");
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "peer find failed");
      }
    });

    LucidShell.setContent(
      el("section", { className: "noe-form noe-panel" }, [
        el("h2", { text: "Find peer" }),
        el("p", {
          className: "noe-muted",
          text: "MasterServer creates SessionID. Join with SessionID to open handshake, then RemoteView.",
        }),
        err,
        result,
        el("div", { className: "noe-field" }, [
          el("label", { for: "sessionId", text: "SessionID" }),
          sessionIdInput,
        ]),
        el("div", { className: "noe-cta-row" }, [createBtn, findBtn]),
      ])
    );
  }

  document.addEventListener("DOMContentLoaded", render);
})();
