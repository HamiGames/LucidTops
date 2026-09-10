/**
 * login.js — UserID / NodeID portal → TokenID via MasterServer (/login, /node-login).
 * Tor-only: no ClearNet OAuth.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell, showError } = LucidShell;
    mountShell({ active: "login" });
    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;

    const accountType = el("select", { id: "accountType" }, [
      el("option", { value: "user", text: "UserID" }),
      el("option", { value: "node", text: "NodeUser" }),
    ]);
    const userId = el("input", {
      id: "userId",
      name: "userId",
      autocomplete: "username",
      required: "required",
    });
    const password = el("input", {
      id: "password",
      name: "password",
      type: "password",
      autocomplete: "current-password",
      required: "required",
    });
    const remember = el("input", {
      id: "remember",
      type: "checkbox",
    });

    const form = el("form", { className: "noe-form noe-panel" }, [
      el("h2", { text: "Login" }),
      el("p", {
        className: "noe-muted",
        text: "Authenticate with MasterServer. Successful login returns TokenID for sessions and ledger access.",
      }),
      err,
      el("div", { className: "noe-field" }, [
        el("label", { for: "accountType", text: "Account type" }),
        accountType,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "userId", text: "UserID / NodeID" }),
        userId,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "password", text: "Password" }),
        password,
      ]),
      el("label", { className: "noe-muted" }, [
        remember,
        document.createTextNode(" Remember TokenID on this browser"),
      ]),
      el("div", { className: "noe-cta-row" }, [
        el("button", { className: "noe-btn noe-btn-primary", type: "submit", text: "Sign in" }),
        el("a", {
          className: "noe-btn noe-btn-ghost",
          href: LucidConfig.page("register"),
          text: "Register",
        }),
      ]),
      el("p", { className: "noe-muted" }, [
        document.createTextNode("Forgot password? Contact AdminID via MasterServer support channel."),
      ]),
    ]);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      err.hidden = true;
      const isNode = accountType.value === "node";
      const apiName = isNode ? "nodeLogin" : "login";
      const body = isNode
        ? { NodeID: userId.value.trim(), Password: password.value }
        : { UserID: userId.value.trim(), Password: password.value };
      try {
        const data = await LucidApi.named(apiName, { method: "POST", body });
        const role =
          data.role ||
          data.Role ||
          (isNode ? "node" : null) ||
          (Number(data.Tier_selected) === 8
            ? "admin"
            : Number(data.Tier_selected) === 7
              ? "masteruser"
              : "user");
        const session = LucidAuth.setSession(
          {
            userId: data.UserID || data.NodeID || data.userId || userId.value.trim(),
            tokenId: data.TokenID || data.IDToken || data.tokenId,
            role,
            tierSelected: data.Tier_selected ?? data.tierSelected,
          },
          remember.checked
        );
        window.location.href = LucidAuth.homeForRole(LucidAuth.detectRole(session));
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "login unsuccessful");
      }
    });

    LucidShell.setContent(form);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
