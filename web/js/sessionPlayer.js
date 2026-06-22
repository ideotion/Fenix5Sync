/* Session-mode player: chains a built session (SessionBuilder output) through the
   shared form-model engine — one guided set at a time, with a rest screen and a
   countdown between sets/exercises, a progress indicator ("3 / 8"), and a
   completion summary. Offline, keyboard-operable, themed from CSS tokens.

   SessionPlayer.create(hostEl, session, { title, onExit }) -> { destroy } */
const SessionPlayer = (() => {
  const REST_BETWEEN_SETS = 20;       // seconds
  const REST_BETWEEN_EXERCISES = 30;  // seconds

  function el(tag, cls, txt) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  function create(host, session, opts = {}) {
    const items = (session.items || []).filter((i) => i.ex);
    const onExit = opts.onExit || (() => {});
    let itemIdx = 0, setIdx = 0, player = null, timer = null, destroyed = false;

    host.innerHTML = "";
    const root = el("div", "sp");
    const head = el("div", "sp-head");
    const title = el("div", "sp-title", opts.title || "Session");
    const progress = el("div", "sp-progress");
    const exitBtn = el("button", "btn sm", "Exit");
    exitBtn.onclick = () => { destroy(); onExit(); };
    head.append(title, progress, exitBtn);
    const stage = el("div", "sp-stage");
    root.append(head, stage);
    host.appendChild(root);

    function setProgress() {
      progress.textContent = items.length ? `${Math.min(itemIdx + 1, items.length)} / ${items.length}` : "";
    }

    function clearTimer() { if (timer) { clearInterval(timer); timer = null; } }
    function clearPlayer() { if (player) { player.destroy(); player = null; } }

    function playItem() {
      clearTimer(); clearPlayer();
      if (itemIdx >= items.length) return finishSession();
      setProgress();
      const item = items[itemIdx];
      stage.innerHTML = "";
      const label = el("div", "sp-ex-label");
      label.append(el("span", "sp-ex-role", item.role === "warmup" ? "Warm-up" : item.role === "cooldown" ? "Cool-down" : `Exercise ${itemIdx + 1}`));
      const setText = item.sets > 1 ? ` · set ${setIdx + 1} of ${item.sets}` : "";
      label.append(el("span", "sp-ex-name", item.name + setText));
      if (item.ex.loadCue) label.append(el("div", "sp-ex-load", item.ex.loadCue));
      const fmHost = el("div");
      // A manual advance so the session never stalls (reduced-motion users, or
      // skipping the RPE prompt). Completing the set + rating RPE also advances.
      const controls = el("div", "sp-controls");
      const skip = el("button", "btn", itemIdx + 1 >= items.length && setIdx + 1 >= (item.sets || 1) ? "Finish ›" : "Skip / next ›");
      skip.onclick = () => advance();
      controls.append(skip);
      stage.append(label, fmHost, controls);
      player = FormModel.create(fmHost, item.ex, { onFinish: () => advance() });
      if (player.start) player.start();  // auto-start the guided set
    }

    function advance() {
      const item = items[itemIdx];
      if (setIdx + 1 < (item.sets || 1)) {
        setIdx += 1;
        return rest(REST_BETWEEN_SETS, `Set ${setIdx + 1} of ${item.sets}: ${item.name}`, playItem);
      }
      itemIdx += 1; setIdx = 0;
      if (itemIdx >= items.length) return finishSession();
      const next = items[itemIdx];
      rest(REST_BETWEEN_EXERCISES, `Next: ${next.name}`, playItem);
    }

    function rest(seconds, nextLabel, then) {
      clearTimer(); clearPlayer();
      let left = seconds;
      stage.innerHTML = "";
      const card = el("div", "sp-rest");
      const big = el("div", "sp-rest-time", String(left));
      const lbl = el("div", "sp-rest-next", nextLabel);
      const skip = el("button", "btn primary", "Start now");
      skip.onclick = () => { clearTimer(); then(); };
      card.append(el("div", "sp-rest-h", "Rest"), big, lbl, skip);
      stage.appendChild(card);
      skip.focus();
      timer = setInterval(() => {
        left -= 1; big.textContent = String(Math.max(0, left));
        if (left <= 0) { clearTimer(); then(); }
      }, 1000);
    }

    function finishSession() {
      clearTimer(); clearPlayer();
      setProgress();
      stage.innerHTML = "";
      const done = el("div", "sp-done");
      done.append(el("div", "sp-done-h", "Session complete"));
      done.append(el("div", "sp-done-sub", `${items.length} exercises · about ${session.minutes || Math.round((session.seconds || 0) / 60)} min. Nice work.`));
      const list = el("ul", "sp-done-list");
      items.forEach((i) => list.append(el("li", null, `${i.name}${i.sets > 1 ? ` × ${i.sets}` : ""}`)));
      done.append(list);
      const again = el("button", "btn", "Back");
      again.onclick = () => { destroy(); onExit(); };
      done.append(again);
      stage.appendChild(done);
      again.focus();
    }

    function onKey(e) {
      if (destroyed) return;
      if (e.key === "Escape") { destroy(); onExit(); }
    }
    document.addEventListener("keydown", onKey);

    function destroy() {
      destroyed = true; clearTimer(); clearPlayer();
      document.removeEventListener("keydown", onKey);
      host.innerHTML = "";
    }

    if (!items.length) {
      stage.appendChild(el("div", "empty", "No exercises selected."));
    } else {
      playItem();
    }
    return { destroy };
  }

  return { create };
})();
