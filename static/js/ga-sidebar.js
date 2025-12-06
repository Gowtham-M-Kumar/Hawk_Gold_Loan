document.addEventListener("DOMContentLoaded", () => {
    const sidebar = document.getElementById("gaSidebar");
    const toggle = document.getElementById("toggleSidebar");

    toggle.addEventListener("click", () => {
        sidebar.classList.toggle("open");
    });
});
