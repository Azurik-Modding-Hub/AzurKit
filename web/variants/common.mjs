// What the Variants view's tabs share (Step 4.6g; Modkit's Variants page's helpers): an element made with its props and
// children (text through textContent only), an attack column's title as the Attacks tab labels it, a text cut with an
// ellipsis and a box's text as a finite number.

export const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// An attacks_anims column as the Attacks tab labels it: basic1 Basic 1, hose_attack_3 Hose 3, sweep ledge Sweep ledge.
export const columnTitle = (column) => {
  const words = column.replace(/_/g, " ").replace(/(?<=[a-z])(?=\d)/g, " ").split(/\s+/).filter(Boolean);
  const kept = words.filter((w, i) => !(w === "attack" && i > 0 && i < words.length - 1 && /^\d+$/.test(words[i + 1])));
  const text = kept.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
};

export const cut = (text, chars) => text.length <= chars ? text : `${text.slice(0, chars - 1)}…`;

// A box's text as a finite number, else null (the engine refuses what isn't one by name, D23: nothing is clamped).
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i;
export const finite = (text) => NUMBER.test(text.trim()) && Number.isFinite(Number(text)) ? Number(text) : null;

// A number as a box shows it (Python's :g, near enough: no trailing zeros, at most 6 significant digits).
export const shown = (value) => typeof value === "number" ? String(Number(value.toPrecision(6))) : String(value);

// A recipe's value copied (its rows edited apart from the recipe until written).
export const copy = (value) => value === undefined ? value : JSON.parse(JSON.stringify(value));
