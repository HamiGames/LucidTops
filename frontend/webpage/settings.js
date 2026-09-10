/**
 * settings.js — session control settings GUI → /user-session-control payload.
 */
(function () {
  "use strict";

  const DEFAULTS = {
    mouse: true,
    keyboard: true,
    audio: true,
    video: true,
    screen: true,
    transfer: false,
    transfer_paths: "",
  };

  function loadLocal() {
    try {
      const raw = sessionStorage.getItem("lucid.sessionSettings");
      return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
    } catch (_) {
      return { ...DEFAULTS };
    }
  }

  function render() {
    const { el, mountShell, showError } = LucidShell;
    const session = LucidAuth.requireAuth();
    if (!session) return;
    mountShell({ active: "settings" });

    const current = loadLocal();
    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const ok = el("p", { className: "noe-ok", text: "" });
    ok.hidden = true;

    function toggle(id, label, checked) {
      const input = el("input", {
        id,
        type: "checkbox",
      });
      input.checked = !!checked;
      return {
        input,
        node: el("label", { className: "noe-muted" }, [input, document.createTextNode(` ${label}`)]),
      };
    }

    const mouse = toggle("mouse", "Mouse control", current.mouse);
    const keyboard = toggle("keyboard", "Keyboard control", current.keyboard);
    const audio = toggle("audio", "Audio", current.audio);
    const video = toggle("video", "Video", current.video);
    const screen = toggle("screen", "Screen share", current.screen);
    const transfer = toggle("transfer", "File transfer", current.transfer);
    const paths = el("textarea", {
      id: "transfer_paths",
      text: current.transfer_paths || "",
    });
    paths.value = current.transfer_paths || "";

    const form = el("form", { className: "noe-form noe-panel" }, [
      el("h2", { text: "Session control settings" }),
      el("p", {
        className: "noe-muted",
        text: "Stored as session_settings for Host_UserID and applied in RemoteView / Rdp.",
      }),
      err,
      ok,
      mouse.node,
      keyboard.node,
      audio.node,
      video.node,
      screen.node,
      transfer.node,
      el("div", { className: "noe-field" }, [
        el("label", { for: "transfer_paths", text: "Transfer access locations (one per line)" }),
        paths,
      ]),
      el("button", {
        className: "noe-btn noe-btn-primary",
        type: "submit",
        text: "Save settings",
      }),
    ]);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      err.hidden = true;
      ok.hidden = true;
      const payload = {
        mouse: mouse.input.checked,
        keyboard: keyboard.input.checked,
        audio: audio.input.checked,
        video: video.input.checked,
        screen: screen.input.checked,
        transfer: transfer.input.checked,
        transfer_paths: paths.value
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
      };
      sessionStorage.setItem("lucid.sessionSettings", JSON.stringify(payload));
      try {
        await LucidApi.named("sessionControl", {
          method: "POST",
          body: {
            UserID: session.userId,
            TokenID: session.tokenId,
            SessionID: sessionStorage.getItem("lucid.activeSessionId") || "",
            Session_settings: payload,
          },
        });
        ok.hidden = false;
        ok.textContent = "Settings saved for session.";
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "settings save failed");
      }
    });

    LucidShell.setContent(form);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
