/**
 * logout.js — clear TokenID session and return to home.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell } = LucidShell;
    mountShell({ active: "logout" });
    const session = LucidAuth.getSession();
    const panel = el("section", { className: "noe-panel noe-form" }, [
      el("h2", { text: "Logout" }),
      el("p", {
        className: "noe-muted",
        text: session
          ? `End session for ${session.userId}? TokenID will be removed from this browser.`
          : "No active TokenID on this browser.",
      }),
      el("div", { className: "noe-cta-row" }, [
        el("button", {
          className: "noe-btn noe-btn-danger",
          type: "button",
          text: "Confirm logout",
          onclick: async () => {
            try {
              if (session && session.tokenId) {
                await LucidApi.named("logout", {
                  method: "POST",
                  body: { UserID: session.userId, TokenID: session.tokenId },
                });
              }
            } catch (_) {
              /* local clear still required */
            }
            LucidAuth.clearSession();
            window.location.href = LucidConfig.page("home");
          },
        }),
        el("a", {
          className: "noe-btn noe-btn-ghost",
          href: LucidConfig.page("dashboard"),
          text: "Cancel",
        }),
      ]),
    ]);
    LucidShell.setContent(panel);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
