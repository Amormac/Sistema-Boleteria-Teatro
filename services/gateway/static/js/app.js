/**
 * app.js — Utilidades generales del frontend
 */

// Auto-cerrar flash messages después de 5 segundos
document.addEventListener('DOMContentLoaded', () => {
    const flashes = document.querySelectorAll('.flash');
    flashes.forEach(flash => {
        setTimeout(() => {
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-10px)';
            setTimeout(() => flash.remove(), 300);
        }, 5000);
    });
});

/**
 * Fetch helper con JSON
 */
async function apiFetch(url, options = {}) {
    const defaults = {
        headers: { 'Content-Type': 'application/json' },
    };
    const config = { ...defaults, ...options };
    if (options.headers) {
        config.headers = { ...defaults.headers, ...options.headers };
    }
    try {
        const resp = await fetch(url, config);
        const data = await resp.json();
        return { ok: resp.ok, status: resp.status, data };
    } catch (err) {
        return { ok: false, status: 0, data: { error: err.message } };
    }
}

/**
 * Muestra notificación tipo toast
 */
function showToast(message, type = 'info') {
    const container = document.querySelector('.flash-container') ||
        (() => {
            const div = document.createElement('div');
            div.className = 'flash-container';
            document.querySelector('.navbar').after(div);
            return div;
        })();

    const flash = document.createElement('div');
    flash.className = `flash flash-${type}`;
    flash.innerHTML = `<span>${message}</span><button class="flash-close" onclick="this.parentElement.remove()">×</button>`;
    container.prepend(flash);

    setTimeout(() => {
        flash.style.opacity = '0';
        flash.style.transform = 'translateY(-10px)';
        setTimeout(() => flash.remove(), 300);
    }, 5000);
}
