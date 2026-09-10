/**
 * home_page.js — LucidTops public onion landing (Noé Dark).
 * Links: login.js, register.js. Brand-first hero composition.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell } = LucidShell;
    const brand = LucidConfig.brandName();
    mountShell({ active: "home" });
    const hero = el("section", { className: "noe-hero" }, [
      el("h1", {}, [
        el("span", { className: "brand", text: brand }),
        document.createTextNode("Remote desktop over Tor."),
      ]),
      el("p", {
        text:
          "Self-hosted peer sessions through the LucidTops MasterServer. Create or join a SessionID, control screen share settings, and keep every hop on the onion path.",
      }),
      el("div", { className: "noe-cta-row" }, [
        el("a", {
          className: "noe-btn noe-btn-primary",
          href: LucidConfig.page("login"),
          text: "Login",
        }),
        el("a", {
          className: "noe-btn noe-btn-ghost",
          href: LucidConfig.page("register"),
          text: "Register",
        }),
      ]),
    ]);
    LucidShell.setContent(hero);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
