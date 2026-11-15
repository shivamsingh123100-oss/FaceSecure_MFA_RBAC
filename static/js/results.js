document.addEventListener("DOMContentLoaded", () => {
    const search = document.querySelector("[data-results-search]");
    const table = document.querySelector("[data-results-table]");
    const noMatch = document.querySelector("[data-results-empty]");

    if (search && table) {
        const rows = Array.from(table.querySelectorAll("tbody tr"));
        search.addEventListener("input", () => {
            const query = search.value.trim().toLocaleLowerCase();
            let visible = 0;
            rows.forEach(row => {
                const match = row.textContent.toLocaleLowerCase().includes(query);
                row.hidden = !match;
                if (match) visible += 1;
            });
            if (noMatch) noMatch.hidden = visible !== 0;
        });
    }

    document.querySelectorAll("[data-results-form]").forEach(form => {
        form.addEventListener("submit", event => {
            const submitter = event.submitter;
            if (!submitter) return;
            submitter.disabled = true;
            const label = submitter.querySelector("span");
            if (label) label.textContent = submitter.dataset.submitState || "Saving…";
            else submitter.textContent = submitter.dataset.submitState || "Saving…";
        });
    });

    const gradebook = document.querySelector("[data-gradebook-form]");
    if (!gradebook) return;

    const max = Number(gradebook.dataset.maxMarks);
    const feedback = gradebook.querySelector("[data-gradebook-feedback]");
    const inputs = Array.from(gradebook.querySelectorAll(".mark-input"));
    const getGrade = value => {
        const percentage = (value / max) * 100;
        if (percentage >= 90) return "A";
        if (percentage >= 80) return "B";
        if (percentage >= 70) return "C";
        if (percentage >= 60) return "D";
        return "F";
    };

    inputs.forEach(input => {
        input.addEventListener("input", () => {
            const preview = input.closest("tr")?.querySelector("[data-grade-preview]");
            if (preview) preview.textContent = input.value === "" ? "—" : getGrade(Number(input.value));
            if (input.value !== "" && (Number(input.value) < 0 || Number(input.value) > max)) {
                input.setCustomValidity(`Enter a mark between 0 and ${max}.`);
            } else {
                input.setCustomValidity("");
            }
        });
    });

    gradebook.addEventListener("submit", event => {
        const submitter = event.submitter;
        if (!submitter) return;

        if (submitter.hasAttribute("data-publish-results")) {
            const missing = inputs.find(input => input.value.trim() === "");
            if (missing) {
                event.preventDefault();
                if (feedback) feedback.textContent = "Add a mark for every student before publishing. Your entered marks are still here.";
                missing.focus();
                return;
            }
            if (!window.confirm("Publish these results to all students in this course?")) {
                event.preventDefault();
                return;
            }
        }

        submitter.disabled = true;
        submitter.textContent = submitter.dataset.submitState || (submitter.value === "publish" ? "Publishing…" : "Saving draft…");
    });
});
