import base64
import os
import io
import uuid
from pathlib import Path

import face_recognition
import numpy as np
from PIL import Image

from config import Config


# ============================================================
# FACE SERVICE EXCEPTIONS
# ============================================================

class FaceServiceError(Exception):
    """Base exception for face-processing errors."""


class InvalidImageError(FaceServiceError):
    """Raised when the supplied image cannot be processed."""


class NoFaceDetectedError(FaceServiceError):
    """Raised when no face is found."""


class MultipleFacesDetectedError(FaceServiceError):
    """Raised when more than one face is found."""


class FaceEncodingError(FaceServiceError):
    """Raised when a face encoding cannot be generated."""


# ============================================================
# IMAGE DECODING
# ============================================================

def decode_base64_image(image_data):
    """
    Convert a browser-generated base64 image into
    a PIL image.
    """

    if not image_data:
        raise InvalidImageError(
            "No image data was supplied."
        )

    try:

        if "," in image_data:
            image_data = image_data.split(
                ",",
                1
            )[1]

        image_bytes = base64.b64decode(
            image_data,
            validate=True
        )

        image = Image.open(
            io.BytesIO(image_bytes)
        )

        image = image.convert("RGB")

        return image

    except Exception as exc:

        raise InvalidImageError(
            "The supplied image could not be processed."
        ) from exc


# ============================================================
# IMAGE → NUMPY
# ============================================================

def pil_to_numpy(image):
    """
    Convert a PIL image to a NumPy RGB array.
    """

    if image is None:
        raise InvalidImageError(
            "Image is empty."
        )

    return np.asarray(
        image,
        dtype=np.uint8
    )


# ============================================================
# FACE DETECTION
# ============================================================

def detect_faces(image_array):
    """
    Detect faces in an image.

    Exactly one face is required for registration
    and authentication.
    """

    if image_array is None:
        raise InvalidImageError(
            "Image data is empty."
        )

    locations = face_recognition.face_locations(
        image_array,
        number_of_times_to_upsample=1,
        model="hog"
    )

    if len(locations) == 0:

        raise NoFaceDetectedError(
            "No face was detected. Please position your face clearly."
        )

    if len(locations) > 1:

        raise MultipleFacesDetectedError(
            "Multiple faces were detected. Please make sure only one person is visible."
        )

    return locations


# ============================================================
# FACE ENCODING
# ============================================================

def generate_face_encoding(image_array):
    """
    Generate the face encoding for exactly one face.
    """

    locations = detect_faces(
        image_array
    )

    encodings = face_recognition.face_encodings(
        image_array,
        known_face_locations=locations,
        num_jitters=1,
        model="small"
    )

    if not encodings:

        raise FaceEncodingError(
            "Unable to generate a face encoding."
        )

    return encodings[0]


# ============================================================
# SAVE FACE IMAGE
# ============================================================

def save_face_image(image, username):
    """
    Save the captured registration image.

    Returns the relative path stored in the database.
    """

    if image is None:
        raise InvalidImageError(
            "Cannot save an empty image."
        )

    face_directory = Path(
        Config.FACE_DIRECTORY
    )

    face_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    safe_username = "".join(
        character
        for character in username
        if character.isalnum()
        or character in ("_", "-")
    )

    unique_id = uuid.uuid4().hex

    filename = (
        f"{safe_username}_{unique_id}.jpg"
    )

    file_path = (
        face_directory / filename
    )

    image.save(
        file_path,
        format="JPEG",
        quality=95
    )

    return str(
        Path("data") / "faces" / filename
    )


# ============================================================
# COMPLETE REGISTRATION PROCESS
# ============================================================

def process_registration_face(
    image_data,
    username
):
    """
    Process a captured registration image.

    Steps:
        base64 image
        ↓
        PIL image
        ↓
        NumPy array
        ↓
        face detection
        ↓
        exactly one face
        ↓
        face encoding
        ↓
        image storage
    """

    image = decode_base64_image(
        image_data
    )

    image_array = pil_to_numpy(
        image
    )

    encoding = generate_face_encoding(
        image_array
    )

    face_path = save_face_image(
        image,
        username
    )

    return {
        "encoding": encoding,
        "face_path": face_path
    }


# ============================================================
# LOAD REGISTERED FACE
# ============================================================

def load_registered_face(
    face_path
):
    """
    Load the stored registration face.
    """

    if not face_path:
        raise InvalidImageError(
            "No registered face is associated with this account."
        )

    path = Path(
        face_path
    )

    if not path.is_absolute():

        path = (
            Config.BASE_DIR / path
        )

    if not path.exists():

        raise InvalidImageError(
            "Registered face data could not be found."
        )

    try:

        image = face_recognition.load_image_file(
            str(path)
        )

        return image

    except Exception as exc:

        raise InvalidImageError(
            "Registered face image could not be loaded."
        ) from exc


# ============================================================
# REGISTERED FACE ENCODING
# ============================================================

def get_registered_face_encoding(
    face_path
):
    """
    Generate the encoding from the stored
    registration face.
    """

    image = load_registered_face(
        face_path
    )

    return generate_face_encoding(
        image
    )


# ============================================================
# VERIFY LIVE FACE
# ============================================================
def verify_face(
    image_data,
    registered_face_path,
    tolerance=None
):
    """
    Compare the captured face against the registered face.

    Returns:
        {
            "success": True/False,
            "matched": True/False,
            "distance": float or None,
            "message": str
        }
    """

    try:

        # ====================================================
        # TOLERANCE
        # ====================================================

        if tolerance is None:
            tolerance = Config.FACE_TOLERANCE

        print("\n" + "=" * 70)
        print("FACE VERIFICATION STARTED")
        print("=" * 70)
        print("Tolerance:", tolerance)
        print("Registered face path:", registered_face_path)
        print("Image received:", bool(image_data))

        # ====================================================
        # VALIDATE CAPTURED IMAGE
        # ====================================================

        if not image_data:

            print("ERROR: No captured image received.")

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": "No captured face image was received."
            }

        print("Captured image length:", len(image_data))

        # ====================================================
        # VALIDATE REGISTERED FACE
        # ====================================================

        if not registered_face_path:

            print("ERROR: Registered face path is empty.")

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": "No registered face is associated with this account."
            }

        if not os.path.exists(registered_face_path):

            print(
                "ERROR: Registered face does not exist:",
                registered_face_path
            )

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": "Registered face image was not found."
            }

        print("Registered face file exists: YES")

        # ====================================================
        # DECODE CAPTURED IMAGE
        # ====================================================

        print("Decoding captured image...")

        live_image = decode_base64_image(
            image_data
        )

        if live_image is None:

            print("ERROR: Could not decode captured image.")

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": "Captured image could not be decoded."
            }

        print("Captured image decoded successfully.")

        # ====================================================
        # CONVERT TO NUMPY
        # ====================================================

        live_array = pil_to_numpy(
            live_image
        )

        if live_array is None:

            print("ERROR: Image conversion failed.")

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": "Captured image could not be processed."
            }

        print(
            "Live image shape:",
            getattr(live_array, "shape", None)
        )

        # ====================================================
        # GENERATE LIVE FACE ENCODING
        # ====================================================

        print("Generating live face encoding...")

        live_encoding = generate_face_encoding(
            live_array
        )

        if live_encoding is None:

            print("ERROR: No face encoding generated.")

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": (
                    "No face detected in the captured image. "
                    "Please position your face clearly inside "
                    "the camera frame."
                )
            }

        print("Live face encoding generated successfully.")

        # ====================================================
        # LOAD REGISTERED FACE ENCODING
        # ====================================================

        print("Loading registered face encoding...")

        registered_encoding = get_registered_face_encoding(
            registered_face_path
        )

        if registered_encoding is None:

            print(
                "ERROR: Registered face encoding could not be loaded."
            )

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": "Unable to read the registered face."
            }

        print(
            "Registered face encoding loaded successfully."
        )

        # ====================================================
        # CALCULATE FACE DISTANCE
        # ====================================================

        print("Calculating face distance...")

        distances = face_recognition.face_distance(
            [registered_encoding],
            live_encoding
        )

        if distances is None or len(distances) == 0:

            print("ERROR: Face distance calculation failed.")

            return {
                "success": False,
                "matched": False,
                "distance": None,
                "message": "Unable to calculate face distance."
            }

        face_distance = float(
            distances[0]
        )

        print("Face distance:", face_distance)
        print("Allowed tolerance:", float(tolerance))

        # ====================================================
        # FACE MATCH
        # ====================================================

        matched = (
            face_distance <= float(tolerance)
        )

        print("Face matched:", matched)

        # ====================================================
        # MATCH SUCCESS
        # ====================================================

        if matched:

            print("=" * 70)
            print("FACE VERIFICATION SUCCESSFUL")
            print("=" * 70)

            return {
                "success": True,
                "matched": True,
                "distance": face_distance,
                "message": "Face verification successful."
            }

        # ====================================================
        # MATCH FAILED
        # ====================================================

        print("=" * 70)
        print("FACE VERIFICATION FAILED")
        print("Distance:", face_distance)
        print("Tolerance:", float(tolerance))
        print("=" * 70)

        return {
            "success": True,
            "matched": False,
            "distance": face_distance,
            "message": (
                "Face does not match the registered face."
            )
        }

    # ========================================================
    # NO FACE
    # ========================================================

    except NoFaceDetectedError as e:

        print("\nFACE VERIFICATION ERROR: NO FACE DETECTED")
        print("Details:", str(e))

        return {
            "success": False,
            "matched": False,
            "distance": None,
            "message": (
                "No face detected. Please position your face "
                "clearly inside the camera frame."
            )
        }

    # ========================================================
    # MULTIPLE FACES
    # ========================================================

    except MultipleFacesDetectedError as e:

        print("\nFACE VERIFICATION ERROR: MULTIPLE FACES")
        print("Details:", str(e))

        return {
            "success": False,
            "matched": False,
            "distance": None,
            "message": (
                "Multiple faces detected. Please make sure "
                "only your face is visible."
            )
        }

    # ========================================================
    # INVALID IMAGE
    # ========================================================

    except InvalidImageError as e:

        print("\nFACE VERIFICATION ERROR: INVALID IMAGE")
        print("Details:", str(e))

        return {
            "success": False,
            "matched": False,
            "distance": None,
            "message": str(e)
        }

    # ========================================================
    # FACE ENCODING ERROR
    # ========================================================

    except FaceEncodingError as e:

        print("\nFACE VERIFICATION ERROR: FACE ENCODING")
        print("Details:", str(e))

        return {
            "success": False,
            "matched": False,
            "distance": None,
            "message": str(e)
        }

    # ========================================================
    # UNEXPECTED ERROR
    # ========================================================

    except Exception as e:

        import traceback

        print("\n")
        print("=" * 70)
        print("FACE VERIFICATION ACTUAL ERROR")
        print("=" * 70)
        print("ERROR TYPE :", type(e).__name__)
        print("ERROR      :", str(e))
        print("-" * 70)

        traceback.print_exc()

        print("=" * 70)
        print("\n")

        return {
            "success": False,
            "matched": False,
            "distance": None,
            "message": (
                f"{type(e).__name__}: {str(e)}"
            )
        }
# ============================================================
# SIMPLE FACE MATCH HELPER
# ============================================================

def faces_match(
    known_encoding,
    candidate_encoding,
    tolerance=None
):
    """
    Compare two already-generated face encodings.
    """

    if tolerance is None:

        tolerance = Config.FACE_TOLERANCE

    results = face_recognition.compare_faces(
        [known_encoding],
        candidate_encoding,
        tolerance=tolerance
    )

    return bool(
        results and results[0]
    )


# ============================================================
# FACE DISTANCE HELPER
# ============================================================

def calculate_face_distance(
    known_encoding,
    candidate_encoding
):
    """
    Calculate Euclidean face distance.
    """

    distances = face_recognition.face_distance(
        [known_encoding],
        candidate_encoding
    )

    if len(distances) == 0:
        return None

    return float(
        distances[0]
    )