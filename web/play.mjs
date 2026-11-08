// Play and Attach… (the app's alone, D882; Modkit's app Play button and its tracker's admin attach, D256, D257,
// D274): Play launches your xemu with the build you saved last in its tray and private endpoints Live reads first, then
// tracks that build's seed with Live on; Attach… (macOS, the tracker's Live bar) reads an xemu you started yourself
// through a read-only admin helper, after one password prompt. The engine decides (azurkit.app.play); this page asks
// what it needs in one small dialog: attach to the xemu already running, which xemu (several found), or where it is
// (none found: its path, or Choose… with the window's dialog). The asks (body -> reply; a refusal is {refused}):
//   play    {iso, xemu?}  -> {launched} | {tracking} | {running, attach, text} | {choose, picked} | {none}
//   attach  {pid?}        -> {attached} | {choose}
const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// call(type, body): the engine's ask; say(text, error); saved(): {out, plan} of the build saved last (plan null when
// it isn't randomized), or null; track(plan): the Randomizer tab's Tracker on plan; live(fromTray): Live on (with the
// seed in xemu's tray first); choose(): the window's open dialog for xemu (null: none); attach: whether this
// computer has the admin attach (macOS).
export function player({ call, say, saved, track, live, choose = null, attach = false }) {
  let then = null;   // the dialog's answer goes here

  // The one question: text, then a pick of found (each {label, value}), or a path box (with Choose… where the app has
  // dialogs), and its yes button.
  const ask = (text, { pick = null, picked = 0, path = false, yes }, answer) => {
    $("xemu-ask-text").textContent = text;
    $("xemu-ask-pick").hidden = !pick;
    $("xemu-ask-pick").replaceChildren(...(pick ?? []).map(({ label, value }) =>
      el("option", { value: String(value), textContent: label })));
    if (pick) $("xemu-ask-pick").selectedIndex = picked;
    $("xemu-ask-path").hidden = !path;
    $("xemu-ask-path").value = "";
    $("xemu-ask-choose").hidden = !path || !choose;
    $("xemu-ask-yes").textContent = yes;
    then = answer;
    $("xemu-ask").showModal();
  };

  const play = async (xemu = null) => {
    const build = saved();
    if (!build) return say("Save the build first, then press Play", true);
    $("play").disabled = true;
    say(xemu ? "Starting xemu…" : "Looking for xemu…");
    const reply = await call("play", { iso: build.out, ...(xemu ? { xemu } : {}) });
    $("play").disabled = false;
    if ("refused" in reply) return say(reply.refused, true);
    if (reply.running) {
      if (!reply.attach) return say(reply.text, true);
      say("");
      return ask(reply.text, { yes: "Attach" }, () => attachTo());
    }
    if (reply.choose) {
      say("");
      return ask("Which xemu?", { pick: reply.choose.map(({ label, path }) => ({ label, value: path })),
                                  picked: reply.picked, yes: "Play" }, play);
    }
    if (reply.none) {
      say("");
      return ask(reply.none, { path: true, yes: "Play" }, play);
    }
    const name = build.out.split(/[\\/]/).pop();
    if (reply.tracking) {   // its xemu still runs, or the helper reads it: no second one
      say(`xemu already runs ${build.plan ? "a build" : name}: Live reads it`);
      return live(true);
    }
    say(`Started ${reply.launched} with ${name}${build.plan ? `: tracking seed ${build.plan.seed}, Live on`
      : " (not randomized: no seed to track)"}`);
    if (build.plan) track(build.plan);
  };

  const attachTo = async (pid = null) => {
    say("Attaching to xemu: macOS asks for your password once…");
    const reply = await call("attach", pid === null ? {} : { pid });
    if ("refused" in reply) return say(reply.refused, true);
    if (reply.choose) {
      say("");
      return ask("Which xemu?", { pick: reply.choose.map(({ label, pid: value }) => ({ label, value })), yes: "Attach" },
                 (value) => attachTo(Number(value)));
    }
    say(`Attached to ${reply.attached}: Live reads it`);
    return live(true);
  };

  $("play").hidden = false;
  $("play").addEventListener("click", () => play());
  $("track-attach").hidden = !attach;
  $("track-attach").addEventListener("click", () => attachTo());
  $("xemu-ask-yes").addEventListener("click", () => {
    const value = !$("xemu-ask-pick").hidden ? $("xemu-ask-pick").value
      : !$("xemu-ask-path").hidden ? $("xemu-ask-path").value.trim() : null;
    if (value === "") return $("xemu-ask-path").focus();
    $("xemu-ask").close();
    then?.(value);
  });
  $("xemu-ask-no").addEventListener("click", () => $("xemu-ask").close());
  $("xemu-ask-choose").addEventListener("click", async () => {
    const path = await choose?.();
    if (path) $("xemu-ask-path").value = path;
  });
  return { play, attach: attachTo, ask };
}
