/**
 * node-registration.js — NodeUser registration → TokenID (/node-registration).
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell, showError } = LucidShell;
    mountShell({ active: "register" });
    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const email = el("input", { id: "email", type: "email", required: "required" });
    const password = el("input", { id: "password", type: "password", required: "required" });
    const userId = el("input", { id: "userId", required: "required" });
    const macHint = el("p", {
      className: "noe-muted",
      text: "Registered MAC is pulled on the Node console at time of operation — not entered here.",
    });

    const form = el("form", { className: "noe-form noe-panel" }, [
      el("h2", { text: "NodeUser registration" }),
      el("p", {
        className: "noe-muted",
        text: "Registers NodeID with LucidTopsNodeDB via MasterServer. Enables operations container authority after login.",
      }),
      err,
      el("div", { className: "noe-field" }, [
        el("label", { for: "userId", text: "Linked UserID (optional existing)" }),
        userId,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "email", text: "Email" }),
        email,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "password", text: "Password" }),
        password,
      ]),
      macHint,
      el("button", {
        className: "noe-btn noe-btn-primary",
        type: "submit",
        text: "Register NodeUser",
      }),
    ]);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      err.hidden = true;
      try {
        const data = await LucidApi.named("nodeRegistration", {
          method: "POST",
          body: {
            UserID: userId.value.trim(),
            Email: email.value.trim(),
            Password: password.value,
          },
        });
        LucidAuth.setSession(
          {
            userId: data.NodeID || data.UserID || userId.value.trim(),
            tokenId: data.TokenID || data.IDToken,
            role: "node",
            tierSelected: data.Tier_selected,
          },
          false
        );
        window.location.href = LucidConfig.page("dashboard");
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "node registration failed");
      }
    });

    LucidShell.setContent(form);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
