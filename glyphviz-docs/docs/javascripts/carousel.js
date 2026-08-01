/* Lightweight, dependency-free auto-advancing carousel for the home page's
   "example gallery" strip. No framework — this is the only carousel on the
   site, so a Material-theme dependency would be a heavier fix than the
   ~70 lines below. Re-initializes on every instant-navigation page load
   (document$), matching hero-scene.js's pattern, and tears down its own
   previous timers first so repeat visits to the home page don't stack them. */
(function () {
  "use strict";

  var timers = [];

  function stopAll() {
    timers.forEach(function (t) { window.clearInterval(t); });
    timers = [];
  }

  function initCarousel(root) {
    var track = root.querySelector(".gv-carousel__track");
    var slides = Array.prototype.slice.call(track.children);
    if (slides.length < 2) return;

    var dotsWrap = root.querySelector(".gv-carousel__dots");
    dotsWrap.innerHTML = "";
    var prevBtn = root.querySelector(".gv-carousel__arrow--prev");
    var nextBtn = root.querySelector(".gv-carousel__arrow--next");
    var index = 0;
    var timer = null;
    var reduceMotion = window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    var dots = slides.map(function (_, i) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "gv-carousel__dot";
      b.setAttribute("aria-label", "Show example " + (i + 1) + " of " + slides.length);
      b.addEventListener("click", function () { goTo(i); restart(); });
      dotsWrap.appendChild(b);
      return b;
    });

    function render() {
      track.style.transform = "translateX(-" + (index * 100) + "%)";
      dots.forEach(function (d, i) {
        d.classList.toggle("is-active", i === index);
      });
    }

    function goTo(i) {
      index = (i + slides.length) % slides.length;
      render();
    }

    function next() { goTo(index + 1); }
    function prev() { goTo(index - 1); }

    function start() {
      if (reduceMotion || timer) return;
      timer = window.setInterval(next, 4500);
      timers.push(timer);
    }
    function stop() {
      if (timer) {
        window.clearInterval(timer);
        timers = timers.filter(function (t) { return t !== timer; });
        timer = null;
      }
    }
    function restart() { stop(); start(); }

    nextBtn.addEventListener("click", function () { next(); restart(); });
    prevBtn.addEventListener("click", function () { prev(); restart(); });
    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", start);

    render();
    start();
  }

  function init() {
    stopAll();
    document.querySelectorAll("[data-gv-carousel]").forEach(initCarousel);
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(init);
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
