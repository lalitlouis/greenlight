/* Runs before first paint (blocking, in <head>): applies the saved theme so a
   dark-mode user never sees a parchment flash. Injected by _versioned_html on
   every page — inline would violate our CSP (script-src 'self'). */
try {
  var t = localStorage.getItem("sr-theme");
  /* dark is the default; only "light" is a stored override (legacy "dark" = default) */
  if (t === "light") document.documentElement.dataset.theme = "light";
} catch (e) {
  /* storage unavailable: default dark */
}
