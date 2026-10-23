document.addEventListener("DOMContentLoaded", () => {

    /*
     * USER SEARCH
     */

    const userSearch =
        document.getElementById("userSearch");

    const usersTable =
        document.getElementById("usersTable");


    if (userSearch && usersTable) {

        userSearch.addEventListener("input", () => {

            const query =
                userSearch.value
                    .trim()
                    .toLowerCase();

            const rows =
                usersTable.querySelectorAll(
                    "tbody tr"
                );


            rows.forEach(row => {

                const text =
                    row.textContent.toLowerCase();

                row.style.display =
                    text.includes(query)
                        ? ""
                        : "none";

            });

        });

    }


    /*
     * ACTIVITY SEARCH
     */

    const activitySearch =
        document.getElementById("activitySearch");

    const activityTable =
        document.getElementById("activityTable");


    if (activitySearch && activityTable) {

        activitySearch.addEventListener("input", () => {

            const query =
                activitySearch.value
                    .trim()
                    .toLowerCase();

            const rows =
                activityTable.querySelectorAll(
                    "tbody tr"
                );


            rows.forEach(row => {

                const text =
                    row.textContent.toLowerCase();

                row.style.display =
                    text.includes(query)
                        ? ""
                        : "none";

            });

        });

    }


    /*
     * PREVENT DOUBLE SUBMISSION
     */

    document
        .querySelectorAll(
            ".verification-actions form"
        )
        .forEach(form => {

            form.addEventListener(
                "submit",
                () => {

                    const button =
                        form.querySelector(
                            "button[type='submit']"
                        );

                    if (button) {

                        button.disabled = true;

                        button.textContent =
                            "Processing...";

                    }

                }
            );

        });

});