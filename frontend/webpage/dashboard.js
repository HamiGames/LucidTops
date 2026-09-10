/**
 * dashboard.js — authenticated User home: sessions, settings, ledger, market, tier usage.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell } = LucidShell;
    const session = LucidAuth.requireAuth();
    if (!session) return;
    mountShell({ active: "dashboard" });
    const pages = LucidConfig.runtime().pages;
    const tier = LucidConfig.tiers().find((t) => t.id === Number(session.tierSelected));
    const tierLabel = tier ? tier.label : session.tierSelected != null ? `tier ${session.tierSelected}` : "tier unset";

    const panel = el("section", { className: "noe-layout" }, [
      el("header", {}, [
        el("h2", { text: "Dashboard" }),
        el("p", {
          className: "noe-muted",
          text: `${session.userId} · ${LucidAuth.detectRole(session)} · ${tierLabel}`,
        }),
      ]),
      el("div", { className: "noe-grid noe-grid-2" }, [
        el("a", { className: "noe-panel", href: pages.findPeer }, [
          el("h3", { text: "Sessions" }),
          el("p", { className: "noe-muted", text: "Create SessionID or find a peer for remote desktop." }),
        ]),
        el("a", { className: "noe-panel", href: pages.settings }, [
          el("h3", { text: "Session settings" }),
          el("p", { className: "noe-muted", text: "Mouse, keyboard, audio, video, screen, transfers." }),
        ]),
        el("a", { className: "noe-panel", href: pages.lucidLedger }, [
          el("h3", { text: "LucidLedger" }),
          el("p", { className: "noe-muted", text: "Read blockchain ledger entries for completed sessions." }),
        ]),
        el("a", { className: "noe-panel", href: pages.lucidMarket }, [
          el("h3", { text: "LucidMarket" }),
          el("p", { className: "noe-muted", text: "Tiers, tokens, and billing through PaySystems." }),
        ]),
      ]),
    ]);
    LucidShell.setContent(panel);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
