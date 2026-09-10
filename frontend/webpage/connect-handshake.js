/**
 * connect-handshake.js — T&Cs + digital signature before session connect (mandatory acceptance).
 */
(function () {
  "use strict";

  async function digestSignature(material) {
    const enc = new TextEncoder().encode(material);
    const buf = await crypto.subtle.digest("SHA-512", enc);
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  function render() {
    const { el, mountShell, showError } = LucidShell;
    const session = LucidAuth.requireAuth();
    if (!session) return;
    mountShell({ active: "findPeer" });

    const sid = sessionStorage.getItem("lucid.activeSessionId") || "";
    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const accept = el("input", { id: "accept", type: "checkbox" });
    const sigOut = el("textarea", { id: "signature", readOnly: "readonly" });

    const genBtn = el("button", {
      className: "noe-btn noe-btn-ghost",
      type: "button",
      text: "Generate digital signature",
    });
    const connectBtn = el("button", {
      className: "noe-btn noe-btn-primary",
      type: "button",
      text: "Complete handshake",
    });

    genBtn.addEventListener("click", async () => {
      err.hidden = true;
      if (!accept.checked) {
        err.hidden = false;
        showError(err, "accept terms before generating signature");
        return;
      }
      const stamp = new Date().toISOString();
      const material = `${session.userId}:${session.tokenId}:${sid}:${stamp}`;
      try {
        const signature = await digestSignature(material);
        sigOut.value = signature;
        sessionStorage.setItem("lucid.handshakeSignature", signature);
        sessionStorage.setItem("lucid.handshakeStamp", stamp);
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "signature failed");
      }
    });

    connectBtn.addEventListener("click", async () => {
      err.hidden = true;
      if (!accept.checked) {
        err.hidden = false;
        showError(err, "acceptance of connection is mandatory");
        return;
      }
      const signature = sigOut.value || sessionStorage.getItem("lucid.handshakeSignature");
      if (!signature) {
        err.hidden = false;
        showError(err, "generate digital signature first");
        return;
      }
      try {
        await LucidApi.named("sessionConnect", {
          method: "POST",
          body: {
            UserID: session.userId,
            TokenID: session.tokenId,
            SessionID: sid,
            accepted: true,
            digital_signature: signature,
            signed_at: sessionStorage.getItem("lucid.handshakeStamp"),
          },
        });
        window.location.href = LucidConfig.page("remoteView");
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "handshake failed");
      }
    });

    const modal = el("div", { className: "noe-modal-backdrop" }, [
      el("section", { className: "noe-panel noe-modal noe-form" }, [
        el("h2", { text: "Connect handshake" }),
        el("p", {
          className: "noe-muted",
          text: `SessionID ${sid || "(none)"} — digital signature authenticates session control settings.`,
        }),
        err,
        el("label", {}, [
          accept,
          document.createTextNode(
            " I accept LucidTops peer session terms, logging into SessionsDB, and remote control policies."
          ),
        ]),
        el("div", { className: "noe-field" }, [
          el("label", { for: "signature", text: "Digital signature (SHA-512)" }),
          sigOut,
        ]),
        el("div", { className: "noe-cta-row" }, [
          genBtn,
          connectBtn,
          el("a", {
            className: "noe-btn noe-btn-ghost",
            href: LucidConfig.page("findPeer"),
            text: "Back",
          }),
        ]),
      ]),
    ]);

    LucidShell.setContent(modal);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
