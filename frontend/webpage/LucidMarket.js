/**
 * LucidMarket.js — tiers / token transfer / billing via /billing-information.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell, showError } = LucidShell;
    const session = LucidAuth.requireAuth();
    if (!session) return;
    mountShell({ active: "lucidMarket" });

    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const ok = el("p", { className: "noe-ok", text: "" });
    ok.hidden = true;
    const billingBox = el("pre", { className: "noe-cli", text: "Loading billing…" });
    const peerId = el("input", { id: "peerId", placeholder: "Peer UserID / NodeID" });
    const amount = el("input", { id: "amount", type: "number", min: "0", step: "0.01" });

    async function refreshBilling() {
      try {
        const data = await LucidApi.named("billing", {
          method: "POST",
          body: { UserID: session.userId, TokenID: session.tokenId },
        });
        billingBox.textContent = JSON.stringify(data, null, 2);
      } catch (ex) {
        billingBox.textContent = ex.message || "billing unavailable";
      }
    }

    const tierGrid = el("div", { className: "noe-grid noe-grid-2" });
    LucidConfig.tiers()
      .filter((t) => !t.gated)
      .forEach((tier) => {
        tierGrid.appendChild(
          el("article", { className: "noe-panel" }, [
            el("h3", { text: tier.label }),
            el("p", {
              className: "noe-muted",
              text: `$${tier.costAud} AUD · ${
                tier.sessionsPerMonth === 0 ? "unlimited" : tier.sessionsPerMonth
              } sessions`,
            }),
            el("button", {
              className: "noe-btn noe-btn-primary",
              type: "button",
              text: "Purchase / renew",
              onclick: async () => {
                err.hidden = true;
                ok.hidden = true;
                try {
                  await LucidApi.named("billing", {
                    method: "POST",
                    body: {
                      UserID: session.userId,
                      TokenID: session.tokenId,
                      action: "purchase_tier",
                      Tier_selected: tier.id,
                      tier_key: tier.key,
                      Payment_Amount: tier.costAud,
                    },
                  });
                  ok.hidden = false;
                  ok.textContent = `Tier ${tier.label} purchase submitted.`;
                  refreshBilling();
                } catch (ex) {
                  err.hidden = false;
                  showError(err, ex.message || "purchase failed");
                }
              },
            }),
          ])
        );
      });

    const transfer = el("form", { className: "noe-form noe-panel" }, [
      el("h3", { text: "Token transfer" }),
      el("p", {
        className: "noe-muted",
        text: "Peer token transfers (NodeUser / peers). Settled through MasterServer billing path.",
      }),
      el("div", { className: "noe-field" }, [
        el("label", { for: "peerId", text: "Counterparty ID" }),
        peerId,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "amount", text: "Amount" }),
        amount,
      ]),
      el("button", {
        className: "noe-btn noe-btn-ghost",
        type: "submit",
        text: "Transfer tokens",
      }),
    ]);

    transfer.addEventListener("submit", async (event) => {
      event.preventDefault();
      err.hidden = true;
      ok.hidden = true;
      try {
        await LucidApi.named("billing", {
          method: "POST",
          body: {
            UserID: session.userId,
            TokenID: session.tokenId,
            action: "token_transfer",
            counterparty_id: peerId.value.trim(),
            Payment_Amount: Number(amount.value),
          },
        });
        ok.hidden = false;
        ok.textContent = "Transfer submitted.";
        refreshBilling();
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "transfer failed");
      }
    });

    LucidShell.setContent(
      el("section", { className: "noe-layout" }, [
        el("header", {}, [
          el("h2", { text: "LucidMarket" }),
          el("p", {
            className: "noe-muted",
            text: "Subscriptions and token exchange via Backend → PaySystems (restricted automation).",
          }),
          err,
          ok,
        ]),
        el("div", { className: "noe-panel" }, [
          el("h3", { text: "Billing snapshot" }),
          billingBox,
        ]),
        el("h3", { text: "Tiers" }),
        tierGrid,
        transfer,
        el("a", {
          className: "noe-btn noe-btn-ghost",
          href: LucidConfig.page("tierSelect"),
          text: "Open tier select",
        }),
      ])
    );
    refreshBilling();
  }

  document.addEventListener("DOMContentLoaded", render);
})();
