const form = document.getElementById("transfer-form");
const resultSection = document.getElementById("result");
const resultJson = document.getElementById("result-json");
const backendName = document.getElementById("backend-name");

async function refreshStatus() {
    try {
        const res = await fetch("http://localhost:8003/");
        const data = await res.json();
        backendName.textContent = data.backend || "mock";
    } catch (err) {
        backendName.textContent = "offline";
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
        sender_balance: Number(form.sender_balance.value),
        receiver_balance: Number(form.receiver_balance.value),
        amount: Number(form.amount.value),
    };

    try {
        const response = await fetch("http://localhost:8001/transfer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        resultJson.textContent = JSON.stringify(data, null, 2);
        resultSection.hidden = false;
        form.sender_balance.value = data.sender_balance;
        await refreshStatus();
    } catch (err) {
        resultJson.textContent = `Transfer failed: ${err}`;
        resultSection.hidden = false;
    }
});

refreshStatus();
