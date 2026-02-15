/**
 * X Feed Reader — Minimal client-side JS (HTMX does the heavy lifting).
 */

// Toast helper: show a temporary notification
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const colors = {
    success: 'bg-green-600/90 border-green-500/50',
    error: 'bg-red-600/90 border-red-500/50',
    info: 'bg-brand-600/90 border-brand-500/50',
  };

  const toast = document.createElement('div');
  toast.className = `px-5 py-3 rounded-lg border text-white text-sm font-medium shadow-xl backdrop-blur-sm transition-all duration-300 ${colors[type] || colors.info}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Listen for HTMX custom events to trigger toasts
document.addEventListener('htmx:afterRequest', (event) => {
  const trigger = event.detail.xhr?.getResponseHeader('HX-Trigger');
  if (trigger) {
    try {
      const data = JSON.parse(trigger);
      if (data.showToast) {
        showToast(data.showToast.message, data.showToast.type);
      }
    } catch {
      // Not JSON trigger, ignore
    }
  }
});

// Handle HTMX 401 → redirect to login
document.addEventListener('htmx:responseError', (event) => {
  if (event.detail.xhr?.status === 401) {
    window.location.href = '/login';
  }
});
