// The shared gallery picker (D262; Step 4.7a): a search box over a list of entries in groups, each a button (role
// option) with its picture where one ships (the Characters tab's species, Step 4.3f; the Data tab's critters and pickups,
// their bodies') or its text alone (armor, staffs), the chosen one marked. The Data tab's pickers use it, and the
// Characters tab's species list (its grade colours and marks through decorate, in its own search box, list and count)
// and its community variants' rows (option). Text only (textContent), no eval: the page's CSP.
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// An entry's button ({ name, label?, title?, picture? }: its picture and label, else its label alone), marked when it is
// the chosen one; decorate(button, entry) adds a tab's own marks.
export function option(entry, chosen, decorate = () => {}) {
  const button = el("button", { type: "button", className: "picker-entry", title: entry.title ?? entry.name });
  const label = entry.label ?? entry.name;
  if (entry.picture) {
    button.append(el("img", { src: entry.picture, alt: "", loading: "lazy", decoding: "async" }),
                  el("span", { textContent: label }));
  } else {
    button.textContent = label;
  }
  button.dataset.name = entry.name;
  button.setAttribute("role", "option");
  button.setAttribute("aria-selected", String(entry.name === chosen));
  decorate(button, entry);
  return button;
}

// picker({ label, placeholder, pick, decorate, search, list, count }): pick(name) runs on a click, decorate(button,
// entry) adds a tab's own marks. It makes its search box, list and count in its element, which goes where the tab
// wants it, or takes a tab's own (count null: the tab writes its own; element null). set(entries, chosen) lists
// entries ({ name, label?, group?, title?, picture? }) in their groups' first-seen order, filter(text) narrows them by
// name or label (case-blind), choose(name) moves the mark.
export function picker({ label, placeholder = "Search", pick, decorate = () => {}, search = null, list = null,
                         count }) {
  const own = !list;
  if (!search) {
    search = el("input", { type: "search", placeholder, spellcheck: false, autocomplete: "off" });
    search.setAttribute("aria-label", placeholder);
  }
  if (count === undefined) count = el("span", { className: "note" });
  list ??= el("div", { className: "picker-list" });
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", label);
  const element = own ? el("div", { className: "picker" },
                           el("p", { className: "picker-search" }, search, " ", count ?? ""), list) : null;
  const p = { entries: [], chosen: null, filter: "" };

  const row = (entry) => option(entry, p.chosen, decorate);
  const render = () => {
    const wanted = p.filter.toLowerCase();
    const shown = p.entries.filter((e) => !wanted || e.name.toLowerCase().includes(wanted)
                                         || (e.label ?? "").toLowerCase().includes(wanted));
    const groups = new Map();
    for (const entry of shown) {
      const key = entry.group ?? "";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(entry);
    }
    list.replaceChildren(...[...groups].flatMap(([group, entries]) => [
      ...group ? [el("h3", { className: "picker-group", textContent: group })] : [], ...entries.map(row)]));
    if (count) count.textContent = shown.length === p.entries.length ? `${p.entries.length}`
      : `${shown.length} of ${p.entries.length}`;
  };
  list.addEventListener("click", (event) => {
    const button = event.target.closest?.(".picker-entry");
    if (button && list.contains(button)) pick(button.dataset.name);
  });
  search.addEventListener("input", () => {
    p.filter = search.value.trim();
    render();
  });
  return {
    element,
    set(entries, chosen = p.chosen) {
      p.entries = entries;
      p.chosen = chosen;
      render();
    },
    filter(text) {
      search.value = text;
      p.filter = text.trim();
      render();
    },
    choose(name) {
      p.chosen = name;
      for (const button of list.querySelectorAll(".picker-entry")) {
        button.setAttribute("aria-selected", String(button.dataset.name === name));
      }
    },
  };
}
