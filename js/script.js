/* ========================================
   ALEX REYNOSO ART
   Global Website Scripts
   ======================================== */

document.addEventListener("DOMContentLoaded", function () {
    const button = document.createElement("button");

    button.type = "button";
    button.className = "back-to-top";
    button.setAttribute("aria-label", "Back to top");
    button.setAttribute("title", "Back to top");
    button.innerHTML = "&#8593;";

    document.body.appendChild(button);

    function updateBackToTop() {
        button.classList.toggle("is-visible", window.scrollY > 500);
    }

    button.addEventListener("click", function () {
        const reduceMotion = window.matchMedia(
            "(prefers-reduced-motion: reduce)"
        ).matches;

        window.scrollTo({
            top: 0,
            behavior: reduceMotion ? "auto" : "smooth"
        });
    });

    window.addEventListener(
        "scroll",
        updateBackToTop,
        { passive: true }
    );

    updateBackToTop();
});
