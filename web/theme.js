// The theme the player picked (D897), set before the page's first paint: a classic script in the head, which the
// parser runs before it reaches the body (the CSP allows the site's own scripts; app.mjs, a module, runs after the
// first paint). The site remembers the theme in this browser's storage. The app serves its own theme.js in place of
// this file, which sets the theme its config remembers: its page's address, and so its storage, is new each launch.
try {
  if (localStorage.getItem("azurkit.theme") === "light") document.documentElement.dataset.theme = "light";
} catch {}   // storage refused (a private window, say): dark
