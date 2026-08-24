/* GREENLIGHT motion design. GSAP 3 + ScrollTrigger (vendored, /static/vendor).
   Every effect degrades to the final resting state when GSAP is absent or the
   user prefers reduced motion — animation is garnish, never a dependency. */

"use strict";

const FX = (() => {
  const reduced =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const on = !reduced && typeof window.gsap !== "undefined";
  if (on && window.ScrollTrigger) gsap.registerPlugin(ScrollTrigger);

  /* Elements marked data-reveal float up as they enter the viewport. */
  function reveals(scope) {
    const nodes = (scope || document).querySelectorAll("[data-reveal]");
    if (!on) return;
    nodes.forEach((node, i) => {
      gsap.fromTo(
        node,
        { y: 26, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.7,
          ease: "power3.out",
          delay: (i % 4) * 0.07,
          scrollTrigger: { trigger: node, start: "top 88%", once: true },
        }
      );
    });
  }

  /* data-count="2487" counts up when scrolled into view. */
  function counters(scope) {
    (scope || document).querySelectorAll("[data-count]").forEach((node) => {
      const to = parseFloat(node.dataset.count);
      const suffix = node.dataset.suffix || "";
      if (!on) {
        node.textContent = to.toLocaleString("en-US") + suffix;
        return;
      }
      const obj = { v: 0 };
      gsap.to(obj, {
        v: to,
        duration: 1.6,
        ease: "power2.out",
        scrollTrigger: { trigger: node, start: "top 90%", once: true },
        onUpdate: () => {
          node.textContent = Math.round(obj.v).toLocaleString("en-US") + suffix;
        },
      });
    });
  }

  /* The report's score ring sweeps from 0 to the score. */
  function scoreRing(node, score) {
    const num = node.querySelector("b");
    if (!on || typeof score !== "number") {
      node.style.setProperty("--scorepct", String(score));
      return;
    }
    const obj = { v: 0 };
    gsap.to(obj, {
      v: score,
      duration: 1.4,
      ease: "power2.inOut",
      delay: 0.2,
      onUpdate: () => {
        node.style.setProperty("--scorepct", obj.v.toFixed(1));
        if (num) num.textContent = String(Math.round(obj.v));
      },
    });
  }

  /* Similarity / tally bars grow to their target width on reveal. */
  function growBars(scope) {
    (scope || document).querySelectorAll("[data-grow]").forEach((node) => {
      const w = node.dataset.grow + "%";
      if (!on) {
        node.style.width = w;
        return;
      }
      gsap.fromTo(
        node,
        { width: "0%" },
        {
          width: w,
          duration: 1.0,
          ease: "power3.out",
          scrollTrigger: { trigger: node, start: "top 92%", once: true },
        }
      );
    });
  }

  /* Stagger a list of cards in (used after dynamic renders). */
  function staggerIn(nodes) {
    if (!on || !nodes.length) return;
    gsap.fromTo(
      nodes,
      { y: 18, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.5, ease: "power2.out", stagger: 0.06 }
    );
  }

  /* Hero: floating report mock + flowing pipeline dashes. */
  function hero() {
    if (!on) return;
    const mock = document.querySelector(".hero-mock");
    if (mock) {
      gsap.fromTo(
        mock,
        { y: 40, opacity: 0, rotate: 2.5 },
        { y: 0, opacity: 1, rotate: 0, duration: 1.0, ease: "power3.out", delay: 0.25 }
      );
      gsap.to(mock, {
        y: -10,
        duration: 3.2,
        ease: "sine.inOut",
        yoyo: true,
        repeat: -1,
        delay: 1.3,
      });
    }
    document.querySelectorAll(".flow-line").forEach((line) => {
      gsap.to(line, { strokeDashoffset: -60, duration: 2.4, ease: "none", repeat: -1 });
    });
    document.querySelectorAll(".pipe-node").forEach((node, i) => {
      gsap.fromTo(
        node,
        { scale: 0.6, opacity: 0, transformOrigin: "center" },
        { scale: 1, opacity: 1, duration: 0.55, ease: "back.out(1.7)", delay: 0.35 + i * 0.12 }
      );
    });
    const headline = document.querySelector(".hero h1");
    if (headline) {
      gsap.fromTo(
        [headline, document.querySelector(".hero .sub"), document.querySelector(".hero-ctas")],
        { y: 24, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.8, ease: "power3.out", stagger: 0.12 }
      );
    }
  }

  return { on, reveals, counters, scoreRing, growBars, staggerIn, hero };
})();

window.FX = FX;
