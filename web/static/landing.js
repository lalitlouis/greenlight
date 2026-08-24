/* Landing entrance: staggered reveal + drifting glows. Degrades to static. */

"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const reduced =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || typeof window.gsap === "undefined") return;

  gsap.fromTo(
    "[data-land]",
    { y: 30, opacity: 0 },
    { y: 0, opacity: 1, duration: 0.9, ease: "power3.out", stagger: 0.13, delay: 0.15 }
  );
  gsap.to(".glow-a", { x: 70, y: 50, duration: 11, ease: "sine.inOut", yoyo: true, repeat: -1 });
  gsap.to(".glow-b", { x: -60, y: -40, duration: 13, ease: "sine.inOut", yoyo: true, repeat: -1 });
  gsap.to(".glow-c", { x: 40, y: -60, duration: 15, ease: "sine.inOut", yoyo: true, repeat: -1 });
});
