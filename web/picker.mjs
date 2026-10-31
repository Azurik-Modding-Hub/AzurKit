// The shared gallery picker (D262; Step 4.7a): a search box over a list of entries in groups, each a button (role
// option) with its picture where one ships (the Characters tab's species, Step 4.3f) or its text alone (armor, staffs,
// critters, pickups), the chosen one marked. The Data tab's pickers use it, and the Characters tab's list moves onto it
// with the Data tab's wiring (its grade colours and marks through decorate). Text only (textContent), no eval: the
// page's CSP.
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// picker({ label, placeholder, pick, decorate }): pick(name) runs on a click, decorate(button, entry) adds a tab's own
// marks. Its element goes where the tab wants it; set(entries, chosen) lists entries ({ name, label?, group?, title?,
// picture? }) in their groups' first-seen order, filter(text) narrows them by name or label (case-blind), choose(name)
// moves the mark.
export function picker({ label, placeholder = "Search", pick, decorate = () => {} }) {
  const search = el("input", { type: "search", placeholder, spellcheck: false, autocomplete: "off" });
  search.setAttribute("aria-label", placeholder);
  const count = el("span", { className: "note" });
  const list = el("div", { className: "picker-list" });
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", label);
  const element = el("div", { className: "picker" }, el("p", { className: "picker-search" }, search, " ", count), list);
  const p = { entries: [], chosen: null, filter: "" };

  const row = (entry) => {
    const button = el("button", { type: "button", className: "picker-entry", title: entry.title ?? entry.name });
    if (entry.picture) button.append(el("img", { src: entry.picture, alt: "", loading: "lazy", decoding: "async" }));
    button.append(el("span", { textContent: entry.label ?? entry.name }));
    button.dataset.name = entry.name;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(entry.name === p.chosen));
    decorate(button, entry);
    return button;
  };
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
    count.textContent = shown.length === p.entries.length ? `${p.entries.length}`
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
