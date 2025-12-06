let stream = null;
let currentInputField = null;

const modal = document.getElementById("cameraModal");
const video = document.getElementById("cameraPreview");
const canvas = document.getElementById("cameraCanvas");
const captureBtn = document.getElementById("captureBtn");
const useBtn = document.getElementById("useBtn");
const closeBtn = document.getElementById("closeCameraBtn");

// OPEN CAMERA
document.querySelectorAll(".open-camera").forEach(btn => {
    btn.addEventListener("click", async () => {
        currentInputField = document.querySelector(`input[name="${btn.dataset.target}"]`);

        modal.style.display = "flex";

        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" },
            audio: false
        });

        video.srcObject = stream;

        useBtn.style.display = "none";
        captureBtn.style.display = "inline-block";
    });
});

// CAPTURE IMAGE
captureBtn.addEventListener("click", () => {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    useBtn.style.display = "inline-block";
});

// USE PHOTO
useBtn.addEventListener("click", async () => {
    canvas.toBlob(blob => {
        const file = new File([blob], "capture.jpg", { type: "image/jpeg" });

        const dt = new DataTransfer();
        dt.items.add(file);

        currentInputField.files = dt.files;

        alert("Photo added successfully!");

        closeCamera();
    });
});

// CLOSE CAMERA
closeBtn.addEventListener("click", closeCamera);

function closeCamera() {
    modal.style.display = "none";

    if (stream) {
        stream.getTracks().forEach(t => t.stop());
    }
}
