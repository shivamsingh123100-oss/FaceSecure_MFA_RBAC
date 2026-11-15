# University results portal

The portal is part of FaceSecure, so every student, teacher, and administrator must complete the existing password and face verification before entering results pages.

## Roles and workflow

- A registrant selects **Student** or **Teacher**. Both account types remain pending until a FaceSecure administrator verifies them.
- An administrator opens **University Results**, creates courses, assigns verified teachers, and enrolls verified students.
- A teacher opens an assigned course, saves draft marks, and publishes results when ready.
- A student sees only published results belonging to their own FaceSecure account.
- Administrators can verify accounts and administer course assignments; they cannot edit teacher marks through the gradebook.

Default grades use percentage bands: A (90+), B (80+), C (70+), D (60+), and F (below 60). Each course sets its own maximum mark.

## Entry point

Use `/results` on the FaceSecure host. An unauthenticated visitor is sent to the FaceSecure login flow; successful MFA routes the account to its role-specific results page.
