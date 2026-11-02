// A reshape's dress on the site (D1011): a worker of its own, which runs worker.mjs and goes when it ends. worker.mjs
// answers in order and a dress takes minutes, so on the page's worker it would hold every ask behind it: the tracker's
// clicks, Track, the Randomizer tab's, a Build. Terminated, its heap goes too (wasm memory never shrinks), and a worker
// can stop what it runs no other way: stopping(), read every WATCH ms, ends it at once with {stopped: true}.
//
// alone(body, {content, stopping, asking, answered, posted}): body is the preview ask's ({file, recipe}), content what
// this browser keeps installed (siteEngine's), the rest app.mjs's bar: its records show on this dress's own ask. The
// reply, or {refused} if the worker stopped.
const WATCH = 250;
const DRAWING = { stage: "start", label: "Drawing the model", percent: null };

export function alone(body, { content, stopping, asking, answered, posted }) {
  const entry = new URL("worker.mjs", location.href).href;
  const url = URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\n`], { type: "text/javascript" }));
  const worker = new Worker(url, { type: "module" }), id = asking("preview");
  return new Promise((resolve) => {
    const end = (reply) => {
      clearInterval(watch);
      worker.terminate();
      URL.revokeObjectURL(url);
      answered(id);
      resolve(reply);
    };
    const watch = setInterval(() => stopping() && end({ stopped: true }), WATCH);
    worker.onmessage = ({ data }) => {
      if (data.type === "ready") {
        if (content) worker.postMessage({ type: "content", ...content });
        worker.postMessage({ type: "preview", call: 0, ...body });
        posted(DRAWING, id);
      } else if (data.type === "progress") {
        const { type, ...step } = data;
        posted(step.percent === 100 ? DRAWING : { ...step, stage: "start" }, id);   // a whole step leaves the drawing
      } else if (data.type === "reply") {
        end(data.reply);
      } else if (data.type === "failed") {
        end({ refused: data.message });
      }
    };
    worker.onerror = (e) => {
      e.preventDefault();
      end({ refused: "The engine stopped before it answered (out of memory?): try again, or use the desktop app" });
    };
  });
}
