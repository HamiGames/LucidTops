/**
 * tier-select.js — Tier_selected from fixes.txt §13; posts /tier-select.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell, showError } = LucidShell;
    mountShell({ active: "register" });
    LucidAuth.requireAuth();
    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const list = el("div", { className: "noe-grid noe-grid-2" });

    LucidConfig.tiers().forEach((tier) => {
      if (tier.gated) return;
      const sessions =
        tier.sessionsPerMonth === 0 ? "unlimited sessions / month" : `${tier.sessionsPerMonth} sessions / month`;
      const card = el("article", { className: "noe-panel" }, [
        el("h3", { text: tier.label }),
        el("p", {
          className: "noe-muted",
          text: `$${tier.costAud} AUD / month · ${sessions} · ${tier.devices} device(s)`,
        }),
        el("button", {
          className: "noe-btn noe-btn-primary",
          type: "button",
          text: "Select",
          onclick: async () => {
            err.hidden = true;
            const session = LucidAuth.getSession();
            try {
              await LucidApi.named("tierSelect", {
                method: "POST",
                body: {
                  UserID: session.userId,
                  TokenID: session.tokenId,
                  Tier_selected: tier.id,
                  tier_key: tier.key,
                },
              });
              LucidAuth.setSession({ ...session, tierSelected: tier.id }, true);
              window.location.href = LucidConfig.page("lucidMarket");
            } catch (ex) {
              err.hidden = false;
              showError(err, ex.message || "tier selection failed");
            }
          },
        }),
      ]);
      list.appendChild(card);
    });

    LucidShell.setContent(
      el("section", { className: "noe-form" }, [
        el("h2", { text: "Select tier" }),
        el("p", {
          className: "noe-muted",
          text: "Public tiers only. Admin_tier and Master_user_tier require hash keys at registration.",
        }),
        err,
        list,
      ])
    );
  }

  document.addEventListener("DOMContentLoaded", render);
})();
