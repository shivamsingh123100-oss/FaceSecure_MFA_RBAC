document.addEventListener("DOMContentLoaded", () => {
    const printButton = document.querySelector("[data-print-results]");
    if (printButton) printButton.addEventListener("click", () => window.print());

    const downloadButton = document.querySelector("[data-download-results]");
    const table = document.querySelector("[data-student-results]");
    if (!downloadButton || !table) return;

    downloadButton.addEventListener("click", () => {
        const rows = Array.from(table.querySelectorAll("tr"));
        const csv = rows.map(row => Array.from(row.querySelectorAll("th, td"))
            .map(cell => `"${cell.innerText.replace(/\s+/g, " ").trim().replace(/"/g, '""')}"`)
            .join(","))
            .join("\r\n");
        const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "my-academic-results.csv";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    });
});
