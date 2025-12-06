

// document.addEventListener("DOMContentLoaded", () => {

//     const steps = document.querySelectorAll(".step-panel");
//     const tabs = document.querySelectorAll(".step-tab");

//     let currentStep = 1; // default step

//     // SHOW A STEP
//     function showStep(step) {
//         currentStep = step;

//         // Hide all step panels
//         steps.forEach(panel => {
//             panel.classList.remove("active");
//             if (Number(panel.dataset.stepPanel) === step) {
//                 panel.classList.add("active");
//             }
//         });

//         // Update step tabs
//         tabs.forEach(tab => {
//             tab.classList.remove("active");
//             if (Number(tab.dataset.step) === step) {
//                 tab.classList.add("active");
//             }
//         });
//     }

//     // VALIDATION FOR EACH STEP
//     function validateStep(step) {
//         let valid = true;

//         const panel = document.querySelector(`.step-panel[data-step-panel="${step}"]`);
//         const requiredInputs = panel.querySelectorAll("input[required], textarea[required], select[required]");

//         requiredInputs.forEach(input => {
//             if (input.value.trim() === "") {
//                 input.classList.add("error");
//                 valid = false;
//             } else {
//                 input.classList.remove("error");
//             }
//         });

//         return valid;
//     }

//     // NEXT BUTTON CLICK
//     document.querySelectorAll(".next-btn").forEach(btn => {
//         btn.addEventListener("click", () => {
//             const step = Number(btn.dataset.nextStep);

//             // Validate before going next
//             if (!validateStep(step)) {
//                 alert("Please fill all required fields.");
//                 return;
//             }

//             showStep(step + 1);
//         });
//     });

//     // BACK BUTTON CLICK
//     document.querySelectorAll(".back-btn").forEach(btn => {
//         btn.addEventListener("click", () => {
//             const prevStep = Number(btn.dataset.prevStep);
//             showStep(prevStep - 1);
//         });
//     });

//     // OPTIONAL: Clicking on step tabs
//     tabs.forEach(tab => {
//         tab.addEventListener("click", () => {
//             const goTo = Number(tab.dataset.step);
//             showStep(goTo);
//         });
//     });

//     // INIT FIRST STEP
//     showStep(1);
// });
