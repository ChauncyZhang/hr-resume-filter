export function createAppHistory({ history, eventTarget }) {
  const entries = [];
  let sequence = 0;
  let listening = false;

  function handlePopState() {
    const entry = entries.pop();
    entry?.restore();
  }

  return {
    start() {
      if (listening) return;
      eventTarget.addEventListener("popstate", handlePopState);
      listening = true;
    },
    stop() {
      if (!listening) return;
      eventTarget.removeEventListener("popstate", handlePopState);
      listening = false;
    },
    push(restore) {
      if (typeof restore !== "function") return;
      sequence += 1;
      entries.push({ id: sequence, restore });
      const currentState = history.state && typeof history.state === "object" ? history.state : {};
      history.pushState({ ...currentState, recruitingAppEntry: sequence }, "");
    },
    requestBack(fallback) {
      if (entries.length) {
        history.back();
        return true;
      }
      fallback?.();
      return false;
    },
  };
}
