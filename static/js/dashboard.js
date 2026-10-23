document.addEventListener("DOMContentLoaded", () => {

    /*
     * Dashboard cards appear smoothly
     */

    const cards =
        document.querySelectorAll(
            ".dashboard-card, .stat-card, .quick-action"
        );


    cards.forEach((card, index) => {

        card.style.opacity = "0";
        card.style.transform = "translateY(8px)";

        setTimeout(() => {

            card.style.transition =
                "opacity 0.3s ease, transform 0.3s ease";

            card.style.opacity = "1";
            card.style.transform = "translateY(0)";

        }, index * 50);

    });


    /*
     * Disable dashboard links while navigating
     */

    document
        .querySelectorAll(".quick-action")
        .forEach(link => {

            link.addEventListener("click", () => {

                link.style.opacity = "0.7";

            });

        });

});