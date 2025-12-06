// static/js/dashboard-search.js

document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("customerSearch");
    const box = document.getElementById("searchSuggestions");

    function hideBox() {
        box.style.display = "none";
        box.innerHTML = "";
    }

    // Handle search typing
    input.addEventListener("keyup", function () {

        const q = this.value.trim();

        if (q.length < 1) {
            hideBox();
            return;
        }

        // Fetch matching customers
        fetch(`/search/customers/?q=` + encodeURIComponent(q))
            .then(r => r.json())
            .then(data => {
                const results = data.results;

                if (results.length === 0) {
                    hideBox();
                    return;
                }

                let html = "";

                results.forEach(c => {
                    html += `
                        <div class="suggest-item"
                             data-id="${c.id}"
                             style="padding:12px 14px; cursor:pointer; border-bottom:1px solid #eee;">
                            <strong>${c.name}</strong>
                            <div style="font-size:12px; color:#6b7280;">${c.mobile_number}</div>
                        </div>
                    `;
                });

                box.innerHTML = html;
                box.style.display = "block";

                // Click redirect handler
                document.querySelectorAll(".suggest-item").forEach(item => {
                    item.addEventListener("click", function () {
                        const id = this.dataset.id;   // customer id
                        window.location.href = `/customer/${id}/loans/`;   // <-- requested behavior
                    });
                });
            });
    });

    // Hide box when clicking outside
    document.addEventListener("click", (e) => {
        if (!box.contains(e.target) && e.target !== input) {
            hideBox();
        }
    });

});
