document.addEventListener("DOMContentLoaded", () => {

    /*
    ============================================================
    FACEsure CAMERA CONFIGURATION
    ============================================================
    */

    const cameraConfigurations = [

        {
            start: "startRegistrationCamera",
            capture: "captureRegistrationFace",
            video: "registrationVideo",
            canvas: "registrationCanvas",
            output: "registrationFaceImage",
            status: "registrationCaptureStatus"
        },

        {
            start: "startLoginCamera",
            capture: "captureLoginFace",
            video: "loginVideo",
            canvas: "loginCanvas",
            output: "loginFaceImage",
            status: "loginCaptureStatus"
        },

        {
            start: "startAdminRegistrationCamera",
            capture: "captureAdminRegistrationFace",
            video: "adminRegistrationVideo",
            canvas: "adminRegistrationCanvas",
            output: "adminRegistrationFaceImage",
            status: "adminRegistrationCaptureStatus"
        },

        {
            start: "startAdminLoginCamera",
            capture: "captureAdminLoginFace",
            video: "adminLoginVideo",
            canvas: "adminLoginCanvas",
            output: "adminLoginFaceImage",
            status: "adminLoginCaptureStatus"
        }

    ];


    /*
    ============================================================
    SETUP EACH CAMERA
    ============================================================
    */

    cameraConfigurations.forEach(configuration => {

        setupCamera(configuration);

    });


    /*
    ============================================================
    CAMERA SETUP
    ============================================================
    */

    function setupCamera(configuration) {

        const startButton =
            document.getElementById(configuration.start);

        const captureButton =
            document.getElementById(configuration.capture);

        const video =
            document.getElementById(configuration.video);

        const canvas =
            document.getElementById(configuration.canvas);

        const output =
            document.getElementById(configuration.output);

        const status =
            document.getElementById(configuration.status);


        /*
        --------------------------------------------------------
        IF THIS CAMERA DOES NOT EXIST ON CURRENT PAGE
        --------------------------------------------------------
        */

        if (
            !startButton ||
            !captureButton ||
            !video ||
            !canvas ||
            !output ||
            !status
        ) {

            return;

        }


        /*
        --------------------------------------------------------
        CAMERA STREAM
        --------------------------------------------------------
        */

        let stream = null;

        let isStarting = false;

        let isCapturing = false;


        /*
        ========================================================
        INITIAL BUTTON STATE
        ========================================================
        */

        captureButton.disabled = true;

        startButton.disabled = false;


        /*
        ========================================================
        HELPER: UPDATE STATUS
        ========================================================
        */

        function updateStatus(message) {

            status.textContent = message;

        }


        /*
        ========================================================
        HELPER: STOP CAMERA
        ========================================================
        */

        function stopCamera() {

            if (stream) {

                stream.getTracks().forEach(track => {

                    try {

                        track.stop();

                    } catch (error) {

                        console.warn(
                            "Unable to stop camera track:",
                            error
                        );

                    }

                });

                stream = null;

            }


            try {

                video.pause();

            } catch (error) {

                console.warn(
                    "Unable to pause video:",
                    error
                );

            }


            video.srcObject = null;

        }


        /*
        ========================================================
        HELPER: RESET CAMERA
        ========================================================
        */

        function resetCamera() {

            stopCamera();

            captureButton.disabled = true;

            startButton.disabled = false;

            startButton.textContent =
                "Start Camera";

        }


        /*
        ========================================================
        START CAMERA
        ========================================================
        */

        startButton.addEventListener(
            "click",
            async () => {

                /*
                Prevent double-clicking Start Camera
                */

                if (isStarting) {

                    return;

                }


                isStarting = true;

                startButton.disabled = true;

                updateStatus(
                    "Starting camera..."
                );


                /*
                ------------------------------------------------
                CHECK BROWSER SUPPORT
                ------------------------------------------------
                */

                if (
                    !navigator.mediaDevices ||
                    !navigator.mediaDevices.getUserMedia
                ) {

                    updateStatus(
                        "Camera access is not supported by this browser."
                    );

                    startButton.disabled = false;

                    isStarting = false;

                    return;

                }


                /*
                ------------------------------------------------
                STOP OLD CAMERA
                ------------------------------------------------
                */

                stopCamera();


                try {

                    /*
                    ============================================
                    REQUEST CAMERA
                    ============================================
                    */

                    stream =
                        await navigator.mediaDevices.getUserMedia({

                            video: {

                                facingMode: {
                                    ideal: "user"
                                },

                                width: {
                                    ideal: 1280
                                },

                                height: {
                                    ideal: 720
                                },

                                frameRate: {
                                    ideal: 30,
                                    max: 30
                                }

                            },

                            audio: false

                        });


                    /*
                    ============================================
                    ATTACH STREAM
                    ============================================
                    */

                    video.srcObject = stream;


                    /*
                    ============================================
                    WAIT FOR VIDEO METADATA
                    ============================================
                    */

                    await new Promise(
                        (resolve, reject) => {

                            let finished = false;

                            const timeout =
                                setTimeout(() => {

                                    if (!finished) {

                                        finished = true;

                                        reject(
                                            new Error(
                                                "Camera video initialization timed out."
                                            )
                                        );

                                    }

                                }, 10000);


                            video.onloadedmetadata =
                                () => {

                                    if (finished) {

                                        return;

                                    }

                                    finished = true;

                                    clearTimeout(timeout);

                                    resolve();

                                };

                        }
                    );


                    /*
                    ============================================
                    START VIDEO
                    ============================================
                    */

                    await video.play();


                    /*
                    ============================================
                    WAIT UNTIL VIDEO HAS REAL DIMENSIONS
                    ============================================
                    */

                    let attempts = 0;

                    while (
                        (
                            !video.videoWidth ||
                            !video.videoHeight
                        ) &&
                        attempts < 20
                    ) {

                        await new Promise(
                            resolve =>
                                setTimeout(
                                    resolve,
                                    100
                                )
                        );

                        attempts++;

                    }


                    /*
                    ============================================
                    VERIFY CAMERA IS ACTUALLY READY
                    ============================================
                    */

                    if (
                        !video.videoWidth ||
                        !video.videoHeight
                    ) {

                        throw new Error(
                            "Camera started but video frame is unavailable."
                        );

                    }


                    /*
                    ============================================
                    CAMERA SUCCESS
                    ============================================
                    */

                    updateStatus(
                        "Camera started. Position your face clearly inside the frame."
                    );


                    startButton.textContent =
                        "Camera Active";


                    startButton.disabled = true;


                    captureButton.disabled =
                        false;


                }

                catch (error) {

                    console.error(
                        "Camera error:",
                        error
                    );


                    /*
                    --------------------------------------------
                    CLEAN UP FAILED CAMERA
                    --------------------------------------------
                    */

                    stopCamera();


                    captureButton.disabled =
                        true;


                    startButton.disabled =
                        false;


                    startButton.textContent =
                        "Start Camera";


                    /*
                    --------------------------------------------
                    DIFFERENT CAMERA ERRORS
                    --------------------------------------------
                    */

                    let message =
                        "Unable to access the camera.";


                    if (
                        error.name ===
                        "NotAllowedError"
                    ) {

                        message =
                            "Camera permission was denied. Allow camera access and try again.";

                    }

                    else if (
                        error.name ===
                        "PermissionDeniedError"
                    ) {

                        message =
                            "Camera permission was denied. Allow camera access and try again.";

                    }

                    else if (
                        error.name ===
                        "NotFoundError"
                    ) {

                        message =
                            "No camera was found on this device.";

                    }

                    else if (
                        error.name ===
                        "NotReadableError"
                    ) {

                        message =
                            "The camera is being used by another application.";

                    }

                    else if (
                        error.name ===
                        "OverconstrainedError"
                    ) {

                        message =
                            "The requested camera settings are not supported.";

                    }

                    else if (
                        error.name ===
                        "SecurityError"
                    ) {

                        message =
                            "Camera access is blocked by browser security settings.";

                    }

                    else if (
                        error.name ===
                        "AbortError"
                    ) {

                        message =
                            "Camera startup was interrupted. Please try again.";

                    }

                    else if (
                        error.message
                    ) {

                        message =
                            error.message;

                    }


                    updateStatus(message);


                }

                finally {

                    isStarting = false;

                }

            }
        );


        /*
        ========================================================
        CAPTURE FACE
        ========================================================
        */

        captureButton.addEventListener(
            "click",
            async () => {

                /*
                ------------------------------------------------
                PREVENT DOUBLE CAPTURE
                ------------------------------------------------
                */

                if (isCapturing) {

                    return;

                }


                isCapturing = true;

                captureButton.disabled = true;


                /*
                ------------------------------------------------
                CHECK CAMERA
                ------------------------------------------------
                */

                if (!stream) {

                    updateStatus(
                        "Camera is not started. Please start the camera first."
                    );

                    captureButton.disabled = false;

                    isCapturing = false;

                    return;

                }


                /*
                ------------------------------------------------
                CHECK VIDEO READY
                ------------------------------------------------
                */

                if (
                    !video.videoWidth ||
                    !video.videoHeight
                ) {

                    updateStatus(
                        "Camera is not ready yet. Please wait a moment and try again."
                    );

                    captureButton.disabled = false;

                    isCapturing = false;

                    return;

                }


                try {

                    /*
                    ============================================
                    GET REAL VIDEO SIZE
                    ============================================
                    */

                    const width =
                        video.videoWidth;

                    const height =
                        video.videoHeight;


                    /*
                    ============================================
                    VALIDATE VIDEO SIZE
                    ============================================
                    */

                    if (
                        width < 320 ||
                        height < 240
                    ) {

                        throw new Error(
                            "Camera resolution is too low."
                        );

                    }


                    /*
                    ============================================
                    SET CANVAS SIZE
                    ============================================
                    */

                    canvas.width =
                        width;

                    canvas.height =
                        height;


                    /*
                    ============================================
                    GET CANVAS CONTEXT
                    ============================================
                    */

                    const context =
                        canvas.getContext(
                            "2d",
                            {
                                willReadFrequently: true
                            }
                        );


                    if (!context) {

                        throw new Error(
                            "Unable to create image capture canvas."
                        );

                    }


                    /*
                    ============================================
                    CLEAR OLD IMAGE
                    ============================================
                    */

                    context.clearRect(
                        0,
                        0,
                        width,
                        height
                    );


                    /*
                    ============================================
                    CAPTURE ONLY VIDEO FRAME
                    ============================================

                    IMPORTANT:

                    This captures the actual camera video.

                    HTML overlays/background elements are NOT
                    captured.
                    ============================================
                    */

                    context.drawImage(
                        video,
                        0,
                        0,
                        width,
                        height
                    );


                    /*
                    ============================================
                    CONVERT IMAGE TO JPEG
                    ============================================
                    */

                    const imageData =
                        canvas.toDataURL(
                            "image/jpeg",
                            0.95
                        );


                    /*
                    ============================================
                    VALIDATE CAPTURED IMAGE
                    ============================================
                    */

                    if (
                        !imageData ||
                        imageData === "data:," ||
                        imageData.length < 1000
                    ) {

                        throw new Error(
                            "Captured image is empty or invalid."
                        );

                    }


                    /*
                    ============================================
                    SAVE IMAGE TO HIDDEN INPUT
                    ============================================
                    */

                    output.value =
                        imageData;


                    /*
                    ============================================
                    VERIFY OUTPUT
                    ============================================
                    */

                    if (
                        !output.value ||
                        output.value.length < 1000
                    ) {

                        throw new Error(
                            "Captured face image could not be stored."
                        );

                    }


                    /*
                    ============================================
                    SUCCESS
                    ============================================
                    */

                    updateStatus(
                        "Face captured successfully. You can now authenticate."
                    );


                    captureButton.textContent =
                        "Face Captured";


                    /*
                    ============================================
                    STOP CAMERA AFTER CAPTURE
                    ============================================
                    */

                    stopCamera();


                    /*
                    ============================================
                    ALLOW RESTART
                    ============================================
                    */

                    startButton.disabled =
                        false;

                    startButton.textContent =
                        "Restart Camera";


                }

                catch (error) {

                    console.error(
                        "Face capture error:",
                        error
                    );


                    /*
                    --------------------------------------------
                    REMOVE INVALID IMAGE
                    --------------------------------------------
                    */

                    output.value = "";


                    /*
                    --------------------------------------------
                    RESET CAPTURE BUTTON
                    --------------------------------------------
                    */

                    captureButton.disabled =
                        false;


                    captureButton.textContent =
                        "Capture Face";


                    /*
                    --------------------------------------------
                    DISPLAY ERROR
                    --------------------------------------------
                    */

                    updateStatus(
                        "Face capture failed: " +
                        error.message
                    );

                }

                finally {

                    isCapturing = false;

                }

            }
        );


        /*
        ========================================================
        WHEN PAGE IS CLOSED
        ========================================================
        */

        window.addEventListener(
            "beforeunload",
            () => {

                stopCamera();

            }
        );


        /*
        ========================================================
        WHEN PAGE BECOMES HIDDEN
        ========================================================
        */

        document.addEventListener(
            "visibilitychange",
            () => {

                if (
                    document.hidden &&
                    stream
                ) {

                    stopCamera();

                    captureButton.disabled =
                        true;

                    startButton.disabled =
                        false;

                    startButton.textContent =
                        "Start Camera";

                }

            }
        );

    }

});