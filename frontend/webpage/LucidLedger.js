/**
 * LucidLedger.js — ledger list by creation date; HistoryKey shows SessionID only.
 */
(function () {
  "use strict";

  function normalizeBlocks(data) {
    if (!data) return [];
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.blocks)) return data.blocks;
    if (Array.isArray(data.ledger)) return data.ledger;
    if (Array.isArray(data.items)) return data.items;
    return [];
  }

  function render() {
    const { el, mountShell, showError } = LucidShell;
    const session = LucidAuth.requireAuth();
    if (!session) return;
    mountShell({ active: "lucidLedger" });

    const err = el("p", { className: "noe-error", text: "" });
    err.hidden = true;
    const tbody = el("tbody");
    const table = el("table", { className: "noe-table" }, [
      el("thead", {}, [
        el("tr", {}, [
          el("th", { text: "BlockID" }),
          el("th", { text: "Creator" }),
          el("th", { text: "Created" }),
          el("th", { text: "HistoryKey (SessionID)" }),
          el("th", { text: "Rewards" }),
        ]),
      ]),
      tbody,
    ]);

    async function load() {
      err.hidden = true;
      tbody.innerHTML = "";
      try {
        const data = await LucidApi.named("userLedger", {
          method: "POST",
          body: { UserID: session.userId, TokenID: session.tokenId },
        });
        const blocks = normalizeBlocks(data).slice().sort((a, b) => {
          const da = String(a.creation_timestamp || a.created_at || "");
          const db = String(b.creation_timestamp || b.created_at || "");
          return db.localeCompare(da);
        });
        if (!blocks.length) {
          tbody.appendChild(
            el("tr", {}, [el("td", { colSpan: "5", className: "noe-muted", text: "No ledger entries." })])
          );
          return;
        }
        blocks.forEach((block) => {
          const history =
            block.HistoryKey ||
            block.history_key ||
            block.SessionID ||
            (block.session_ids && block.session_ids.join(", ")) ||
            "—";
          tbody.appendChild(
            el("tr", {}, [
              el("td", { text: String(block.BlockID || block.block_id || "").slice(0, 18) }),
              el("td", { text: String(block.creator_id || block.creator || "—") }),
              el("td", { text: String(block.creation_timestamp || block.created_at || "—") }),
              el("td", { text: String(history) }),
              el("td", { text: String(block.Rewards ?? block.rewards ?? "—") }),
            ])
          );
        });
      } catch (ex) {
        err.hidden = false;
        showError(err, ex.message || "ledger read failed");
      }
    }

    LucidShell.setContent(
      el("section", { className: "noe-layout" }, [
        el("header", {}, [
          el("h2", { text: "LucidLedger" }),
          el("p", {
            className: "noe-muted",
            text: "Block content is limited to HistoryKey SessionID references.",
          }),
          err,
        ]),
        el("div", { className: "noe-panel" }, [table]),
      ])
    );
    load();
  }

  document.addEventListener("DOMContentLoaded", render);
})();
