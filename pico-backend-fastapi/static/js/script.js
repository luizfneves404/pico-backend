document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("resetForm");
  if (!form) return;

  const newPassword = document.getElementById("new_password");
  const confirmPassword = document.getElementById("confirm_password");

  // Real-time password matching validation
  confirmPassword.addEventListener("input", function () {
    if (newPassword.value !== confirmPassword.value) {
      confirmPassword.setCustomValidity("Passwords do not match");
    } else {
      confirmPassword.setCustomValidity("");
    }
  });

  // Form submission
  form.addEventListener("submit", function (e) {
    if (newPassword.value !== confirmPassword.value) {
      e.preventDefault();
      alert("Passwords do not match");
      return false;
    }
  });
});
