document.addEventListener("DOMContentLoaded", () => {

    const loader = document.getElementById("page-loader");

    if (loader) {
        setTimeout(() => {
            loader.classList.add("loaded");
        }, 250);
    }


    const menuButton =
        document.getElementById("mobileMenuButton");

    const navigation =
        document.querySelector(".main-nav");

    if (menuButton && navigation) {

        menuButton.addEventListener("click", () => {

            navigation.classList.toggle("mobile-open");

            const opened =
                navigation.classList.contains("mobile-open");

            menuButton.setAttribute(
                "aria-expanded",
                opened ? "true" : "false"
            );

        });

    }


    document
        .querySelectorAll(".flash-close")
        .forEach(button => {

            button.addEventListener("click", () => {

                const message =
                    button.closest(".flash-message");

                if (message) {
                    message.remove();
                }

            });

        });


    document
        .querySelectorAll("[data-auto-dismiss='true']")
        .forEach(message => {

            setTimeout(() => {

                message.style.opacity = "0";

                setTimeout(() => {
                    message.remove();
                }, 300);

            }, 5000);

        });


    document
        .querySelectorAll("[data-confirm]")
        .forEach(button => {

            button.addEventListener("click", event => {

                const message =
                    button.getAttribute("data-confirm");

                if (!window.confirm(message)) {
                    event.preventDefault();
                }

            });

        });

});