/* Sign-in page: carry the ?next= destination through to the OAuth flow. */

"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const next = new URLSearchParams(window.location.search).get("next");
  const btn = document.getElementById("google-btn");
  if (btn && next && next.startsWith("/")) {
    btn.href = "/auth/login?next=" + encodeURIComponent(next);
  }
});
