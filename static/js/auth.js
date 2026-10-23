document.addEventListener("DOMContentLoaded", () => {

    /*
     * PASSWORD VISIBILITY
     */

    document
        .querySelectorAll(".password-toggle")
        .forEach(button => {

            button.addEventListener("click", () => {

                const targetId =
                    button.getAttribute("data-target");

                const input =
                    document.getElementById(targetId);

                if (!input) {
                    return;
                }

                if (input.type === "password") {

                    input.type = "text";
                    button.textContent = "Hide";

                } else {

                    input.type = "password";
                    button.textContent = "Show";

                }

            });

        });


    /*
     * PASSWORD STRENGTH
     */

    const password =
        document.getElementById("password");

    const strengthBar =
        document.getElementById("passwordStrengthBar");

    if (password && strengthBar) {

        password.addEventListener("input", () => {

            const value = password.value;

            let score = 0;

            if (value.length >= 8) {
                score++;
            }

            if (/[A-Z]/.test(value)) {
                score++;
            }

            if (/[a-z]/.test(value)) {
                score++;
            }

            if (/[0-9]/.test(value)) {
                score++;
            }

            if (/[^A-Za-z0-9]/.test(value)) {
                score++;
            }

            strengthBar.style.width =
                `${score * 20}%`;

        });

    }


    /*
     * USER REGISTRATION VALIDATION
     */

    const userRegistration =
        document.getElementById("userRegistrationForm");

    if (userRegistration) {

        userRegistration.addEventListener(
            "submit",
            event => {

                const password =
                    document.getElementById("password");

                const confirmPassword =
                    document.getElementById(
                        "confirm_password"
                    );

                if (
                    password &&
                    confirmPassword &&
                    password.value !== confirmPassword.value
                ) {

                    event.preventDefault();

                    alert(
                        "Password and confirm password do not match."
                    );

                    confirmPassword.focus();

                    return;
                }

                const faceImage =
                    document.getElementById(
                        "registrationFaceImage"
                    );

                if (
                    faceImage &&
                    !faceImage.value
                ) {

                    event.preventDefault();

                    alert(
                        "Please capture your face before registration."
                    );

                }

            }
        );

    }


    /*
     * ADMIN REGISTRATION VALIDATION
     */

    const adminRegistration =
        document.getElementById("adminRegistrationForm");

    if (adminRegistration) {

        adminRegistration.addEventListener(
            "submit",
            event => {

                const password =
                    document.getElementById("password");

                const confirmPassword =
                    document.getElementById(
                        "confirm_password"
                    );

                if (
                    password &&
                    confirmPassword &&
                    password.value !== confirmPassword.value
                ) {

                    event.preventDefault();

                    alert(
                        "Password and confirm password do not match."
                    );

                    confirmPassword.focus();

                    return;
                }

                const faceImage =
                    document.getElementById(
                        "adminRegistrationFaceImage"
                    );

                if (
                    faceImage &&
                    !faceImage.value
                ) {

                    event.preventDefault();

                    alert(
                        "Please capture the administrator face."
                    );

                }

            }
        );

    }

});