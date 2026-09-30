/* ========================================
   ALEX REYNOSO ART
   Global Website Scripts
   ======================================== */

document.addEventListener("DOMContentLoaded", function () {

    /* ========================================
       BACK TO TOP
       ======================================== */

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


    /* ========================================
       AUTOMATIC ARTWORK NAVIGATION
       art.html controls the artwork order.
       ======================================== */

    const artworkNavigation = document.querySelector(
        ".artwork-navigation"
    );

    const artworkNavigationTop = document.querySelector(
        ".artwork-navigation-top"
    );

    /*
     * Run the artwork system if either navigation
     * exists on the current page.
     */
    if (artworkNavigation || artworkNavigationTop) {

        fetch("art.html")
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Could not load art.html");
                }

                return response.text();
            })
            .then(function (html) {

                const parser = new DOMParser();

                const artDocument = parser.parseFromString(
                    html,
                    "text/html"
                );

                /*
                 * Only linked featured artwork cards count.
                 * Mia's Kids Corner and unlinked placeholders
                 * are automatically ignored.
                 */
                const artworkCards = Array.from(
                    artDocument.querySelectorAll(
                        ".art-gallery .artwork-featured > a[href]"
                    )
                );

                const artworks = artworkCards.map(function (link) {

                    const titleElement = link.querySelector("h2");

                    return {
                        href: link.getAttribute("href"),
                        title: titleElement
                            ? titleElement.textContent.trim()
                            : "Artwork"
                    };
                });


                /*
                 * Compare filenames only.
                 */
                const currentPage =
                    window.location.pathname.split("/").pop() ||
                    "index.html";

                const currentIndex = artworks.findIndex(
                    function (artwork) {
                        return artwork.href.split("/").pop() === currentPage;
                    }
                );

                if (currentIndex === -1) {
                    return;
                }


                const previousArtwork =
                    currentIndex > 0
                        ? artworks[currentIndex - 1]
                        : null;

                const nextArtwork =
                    currentIndex < artworks.length - 1
                        ? artworks[currentIndex + 1]
                        : null;


                /* ========================================
                   TOP ARTWORK NAVIGATION
                   Arrows only + Back to Art
                   ======================================== */

                if (artworkNavigationTop) {

                    const topPrevious = document.createElement("div");
                    topPrevious.className =
                        "artwork-navigation-top-previous";

                    if (previousArtwork) {

                        const previousLink =
                            document.createElement("a");

                        previousLink.href =
                            previousArtwork.href;

                        previousLink.innerHTML =
                            '<span aria-hidden="true">←</span>';

                        previousLink.setAttribute(
                            "aria-label",
                            "Previous artwork: " +
                            previousArtwork.title
                        );

                        topPrevious.appendChild(previousLink);
                    }


                    const topCenter = document.createElement("div");
                    topCenter.className =
                        "artwork-navigation-top-center";

                    const topBackLink =
                        document.createElement("a");

                    topBackLink.href = "art.html";
                    topBackLink.textContent = "BACK TO ART";

                    topCenter.appendChild(topBackLink);


                    const topNext = document.createElement("div");
                    topNext.className =
                        "artwork-navigation-top-next";

                    if (nextArtwork) {

                        const nextLink =
                            document.createElement("a");

                        nextLink.href =
                            nextArtwork.href;

                        nextLink.innerHTML =
                            '<span aria-hidden="true">→</span>';

                        nextLink.setAttribute(
                            "aria-label",
                            "Next artwork: " +
                            nextArtwork.title
                        );

                        topNext.appendChild(nextLink);
                    }


                    artworkNavigationTop.replaceChildren(
                        topPrevious,
                        topCenter,
                        topNext
                    );

                    artworkNavigationTop.classList.add(
                        "is-ready"
                    );
                }


                /* ========================================
                   BOTTOM ARTWORK NAVIGATION
                   Artwork names + Back to Art
                   ======================================== */

                if (artworkNavigation) {

                    /* PREVIOUS */

                    const previousSlot =
                        document.createElement("div");

                    previousSlot.className =
                        "artwork-navigation-slot " +
                        "artwork-navigation-previous";

                    if (previousArtwork) {

                        const previousLink =
                            document.createElement("a");

                        previousLink.href =
                            previousArtwork.href;

                        previousLink.innerHTML =
                            '<span aria-hidden="true">←</span> ' +
                            escapeArtworkTitle(
                                previousArtwork.title
                            );

                        previousLink.setAttribute(
                            "aria-label",
                            "Previous artwork: " +
                            previousArtwork.title
                        );

                        previousSlot.appendChild(
                            previousLink
                        );
                    }


                    /* BACK TO ART */

                    const centerSlot =
                        document.createElement("div");

                    centerSlot.className =
                        "artwork-navigation-slot " +
                        "artwork-navigation-center";

                    const backLink =
                        document.createElement("a");

                    backLink.href = "art.html";
                    backLink.textContent = "BACK TO ART";

                    centerSlot.appendChild(backLink);


                    /* NEXT */

                    const nextSlot =
                        document.createElement("div");

                    nextSlot.className =
                        "artwork-navigation-slot " +
                        "artwork-navigation-next";

                    if (nextArtwork) {

                        const nextLink =
                            document.createElement("a");

                        nextLink.href =
                            nextArtwork.href;

                        nextLink.innerHTML =
                            escapeArtworkTitle(
                                nextArtwork.title
                            ) +
                            ' <span aria-hidden="true">→</span>';

                        nextLink.setAttribute(
                            "aria-label",
                            "Next artwork: " +
                            nextArtwork.title
                        );

                        nextSlot.appendChild(nextLink);
                    }


                    artworkNavigation.replaceChildren(
                        previousSlot,
                        centerSlot,
                        nextSlot
                    );

                    artworkNavigation.classList.add(
                        "is-ready"
                    );
                }

            })
            .catch(function (error) {

                console.warn(
                    "Artwork navigation unavailable:",
                    error
                );
            });
    }


    /* ========================================
       SMALL SAFETY HELPER
       Prevent artwork titles from becoming HTML.
       ======================================== */

    function escapeArtworkTitle(text) {
        const element = document.createElement("span");
        element.textContent = text;
        return element.innerHTML;
    }

});
