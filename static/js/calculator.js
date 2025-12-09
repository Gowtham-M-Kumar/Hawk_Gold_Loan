let selectedCarat = 22;

// When user clicks a carat button
document.querySelectorAll(".carat-btn").forEach(btn => {
    btn.addEventListener("click", function () {
        document.querySelectorAll(".carat-btn").forEach(b => b.classList.remove("active"));
        this.classList.add("active");

        selectedCarat = parseInt(this.dataset.carat);
        calculateValue();
    });
});

// When user types grams
document.getElementById("goldWeight").addEventListener("input", calculateValue);


function calculateValue() {
    const grams = document.getElementById("goldWeight").value;

    if (!grams || grams <= 0) {
        updateResult(0);
        return;
    }

    fetch(`/calculate_gold_value/?grams=${grams}&carat=${selectedCarat}`)
        .then(res => res.json())
        .then(data => {
            updateResult(data.amount);
        })
        .catch(err => {
            console.error("Calculation error:", err);
        });
}

function updateResult(amount) {
    const lakh = (amount / 100000).toFixed(2);
    const formatted = Math.floor(amount).toLocaleString("en-IN");

    document.getElementById("calcResult").innerHTML =
        `${lakh} L | You're eligible for ₹${formatted} based on the gold details you entered.`;
}
