/**
 * register.js — User / NodeUser registration; Admin/Master gated by hash keys from secrets flow.
 */
(function () {
  "use strict";

  function render() {
    const { el, mountShell, showError } = LucidShell;
    mountShell({ active: "register" });
    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const ok = el("p", { className: "noe-ok", text: "" });
    ok.hidden = true;

    const accountType = el("select", { id: "accountType" }, [
      el("option", { value: "user", text: "User" }),
      el("option", { value: "node", text: "NodeUser" }),
      el("option", { value: "master", text: "MasterUser (hash key)" }),
      el("option", { value: "admin", text: "Admin (hash key)" }),
    ]);
    const email = el("input", { id: "email", type: "email", required: "required" });
    const password = el("input", { id: "password", type: "password", required: "required" });
    const confirm = el("input", { id: "confirm", type: "password", required: "required" });
    const hashKey = el("input", { id: "hashKey", type: "password" });
    const hashWrap = el("div", { className: "noe-field", hidden: "hidden" }, [
      el("label", { for: "hashKey", text: "Hash key (AdminID.secrets / MasterID.secrets)" }),
      hashKey,
    ]);

    accountType.addEventListener("change", () => {
      const gated = accountType.value === "admin" || accountType.value === "master";
      hashWrap.hidden = !gated;
      hashKey.required = gated;
    });

    const form = el("form", { className: "noe-form noe-panel" }, [
      el("h2", { text: "Register" }),
      el("p", {
        className: "noe-muted",
        text: "Creates a 16-digit ID and TokenID via MasterServer. Select a public tier next, or supply a gated hash key for Admin / MasterUser.",
      }),
      err,
      ok,
      el("div", { className: "noe-field" }, [
        el("label", { for: "accountType", text: "Registration type" }),
        accountType,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "email", text: "Email" }),
        email,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "password", text: "Password" }),
        password,
      ]),
      el("div", { className: "noe-field" }, [
        el("label", { for: "confirm", text: "Confirm password" }),
        confirm,
      ]),
      hashWrap,
      el("div", { className: "noe-cta-row" }, [
        el("button", { className: "noe-btn noe-btn-primary", type: "submit", text: "Create account" }),
        el("a", {
          className: "noe-btn noe-btn-ghost",
          href: LucidConfig.page("tierSelect"),
          text: "Tier select",
        }),
        el("a", {
          className: "noe-btn noe-btn-ghost",
          href: LucidConfig.page("nodeRegistration"),
          text: "Node registration",
        }),
      ]),
    ]);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      err.hidden = true;
      ok.hidden = true;
      if (password.value !== confirm.value) {
        err.hidden = false;
        showError(err, "passwords do not match");
        return;
      }
      const type = accountType.value;
      const body = {
        Email: email.value.trim(),
        Password: password.value,
        account_type: type,
      };
      if (type === "admin" || type === "master") {
        body.HashKey = hashKey.value.trim();
      }
      const apiName = type === "node" ? "nodeRegistration" : "register";
      try {
        const data = await LucidApi.named(apiName, { method: "POST", body });
        if (data.TokenID || data.IDToken) {
          LucidAuth.setSession(
            {
              userId: data.UserID || data.NodeID || data.userId,
              tokenId: data.TokenID || data.IDToken,
              role:
                type === "admin"
                  ? "admin"
                  : type === "master"
                    ? "masteruser"
                    : type === "node"
                      ? "node"
                      : "user",
              tierSelected: data.Tier_selected,
            },
            false
          );
        }
        ok.hidden = false;
        ok.textContent = "Registration accepted. Continue to tier selection.";
        window.setTimeout(() => {
          window.location.href = LucidConfig.page("tierSelect");
        }, 600);
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "registration failed");
      }
    });

    LucidShell.setContent(form);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
