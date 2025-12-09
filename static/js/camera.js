(function () {
  let stream = null;
  let facingMode = "environment";
  let currentTargetInputId = null;

  const modal = document.getElementById("cameraModal");
  const video = document.getElementById("cameraVideo");
  const canvas = document.getElementById("cameraCanvas");
  const captureBtn = document.getElementById("cameraCaptureBtn");
  const cancelBtn = document.getElementById("cameraCancelBtn");
  const flipBtn = document.getElementById("cameraFlipBtn");

  async function openCameraForInput(inputId) {
    currentTargetInputId = inputId;
    modal.style.display = "flex";

    stopStream();

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facingMode } },
        audio: false
      });

      video.srcObject = stream;
      await video.play();
    } catch (err) {
      alert("Camera access failed.");
      closeModal();
    }
  }

  function stopStream() {
    if (stream) stream.getTracks().forEach(t => t.stop());
  }

  function closeModal() {
    stopStream();
    modal.style.display = "none";
    currentTargetInputId = null;
  }

  async function capturePhoto() {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    const blob = await new Promise(resolve =>
      canvas.toBlob(resolve, "image/jpeg", 0.9)
    );

    const file = new File([blob], `capture_${Date.now()}.jpg`, {
      type: "image/jpeg"
    });

    const input = document.getElementById(currentTargetInputId);
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;

    closeModal();
  }

  function bindCameraButtons() {
    document.querySelectorAll(".open-camera").forEach(btn => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";

      btn.addEventListener("click", () => {
        const inputId = btn.dataset.target;
        openCameraForInput(inputId);
      });
    });
  }

  flipBtn.addEventListener("click", () => {
    facingMode = facingMode === "user" ? "environment" : "user";
    if (currentTargetInputId) openCameraForInput(currentTargetInputId);
  });

  captureBtn.addEventListener("click", capturePhoto);
  cancelBtn.addEventListener("click", closeModal);

  document.addEventListener("DOMContentLoaded", bindCameraButtons);
})();
