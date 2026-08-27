/* Runs before first paint (blocking, in <head>): applies the saved theme so a
   dark-mode user never sees a parchment flash. Injected by _versioned_html on
   every page — inline would violate our CSP (script-src 'self'). */
try {
  var t = localStorage.getItem("sr-theme");
  if (t) document.documentElement.dataset.theme = t;
} catch (e) {
  /* storage unavailable: default light */
}
