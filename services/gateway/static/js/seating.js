/* eslint-disable */
// seating.js — Mapa de asientos interactivo
// Maneja: carga de asientos, selección, HOLD, confirmación de compra, countdown.
// Variables globales esperadas del template: EVENT_ID, EVENT_PRICE, EVENT_ROWS, EVENT_COLS, MAX_PER_USER, CURRENT_USER_ID

let seatData = {};       // { "A1": {status, zone, held_by, hold_until}, ... }
let selectedSeats = [];   // ["A1", "A2"]
let heldSeats = [];       // Asientos en HOLD por este usuario
let holdTimer = null;     // Interval del countdown
let isExpired = false;    // Estado de expiración

// ── Inicialización ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await loadSeats();
});

async function loadSeats() {
    const loading = document.getElementById('seat-loading');
    const mapEl = document.getElementById('seat-map');

    loading.style.display = 'flex';
    mapEl.style.display = 'none';

    const result = await apiFetch(`/api/seats/${EVENT_ID}`);

    if (!result.ok) {
        loading.innerHTML = '<span style="color:#e01b24;">Error al cargar el mapa de asientos.</span>';
        return;
    }

    seatData = result.data.seats || {};
    renderSeatMap(result.data);

    loading.style.display = 'none';
    mapEl.style.display = 'flex';

    // Verificar si hay asientos ya en HOLD por este usuario
    checkExistingHolds();
    updateLimitStatus(); // Verificar si ya llegamos al límite con compras previas
    isExpired = false;
    document.getElementById('seat-map').classList.remove('map-expired');
}

function renderSeatMap(data) {
    const mapEl = document.getElementById('seat-map');
    mapEl.innerHTML = '';

    const rows = data.rows || EVENT_ROWS;
    const cols = data.cols || EVENT_COLS;

    // Números de columna
    const colNumbers = document.createElement('div');
    colNumbers.className = 'seat-col-numbers';
    for (let c = 1; c <= cols; c++) {
        const numEl = document.createElement('span');
        numEl.className = 'seat-col-num';
        numEl.textContent = c;
        colNumbers.appendChild(numEl);
    }
    mapEl.appendChild(colNumbers);

    // Filas de asientos
    for (let r = 0; r < rows; r++) {
        const rowLetter = String.fromCharCode(65 + r);
        const rowEl = document.createElement('div');
        rowEl.className = 'seat-row';

        // Etiqueta de fila
        const label = document.createElement('span');
        label.className = 'seat-row-label';
        label.textContent = rowLetter;
        rowEl.appendChild(label);

        for (let c = 1; c <= cols; c++) {
            const seatId = `${rowLetter}${c}`;
            const seat = seatData[seatId] || { status: 'FREE', zone: 'GENERAL' };

            const btn = document.createElement('button');
            btn.className = `seat seat-${seat.status.toLowerCase()}`;
            btn.dataset.seatId = seatId;
            btn.textContent = c;
            if (seat.status === 'SOLD') {
                if (seat.held_by == CURRENT_USER_ID) { // Relaxed check
                    btn.className = 'seat seat-my-sold';
                    btn.disabled = true;
                    btn.title = 'Tu asiento (Comprado)';
                } else {
                    btn.className = 'seat seat-sold';
                    btn.disabled = true;
                }
            } else if (seat.status === 'HELD') {
                if (seat.held_by == CURRENT_USER_ID) { // Relaxed check
                    btn.className = 'seat seat-my-hold';
                    btn.disabled = true;
                    btn.title = 'Tu reserva temporal';
                } else {
                    btn.className = 'seat seat-held'; // Visualmente ocupado
                    btn.disabled = true;
                }
            } else {
                btn.className = 'seat seat-free';
                btn.addEventListener('click', () => toggleSeat(seatId));
            }

            // Si es un asiento con HOLD expirado, mostrarlo como libre
            if (seat.status === 'HELD' && seat.hold_until) {
                const holdEnd = new Date(seat.hold_until);
                if (holdEnd < new Date()) {
                    btn.className = 'seat seat-free';
                    btn.addEventListener('click', () => toggleSeat(seatId));
                    seat.status = 'FREE';
                    seatData[seatId] = seat;
                }
            }

            rowEl.appendChild(btn);
        }

        mapEl.appendChild(rowEl);
    }
}

// ── Selección de asientos ─────────────────────────────────────
function toggleSeat(seatId) {
    if (isExpired) {
        showToast('El tiempo de reserva ha expirado. Recarga la página.', 'warning');
        return;
    }
    const idx = selectedSeats.indexOf(seatId);

    if (idx >= 0) {
        // Deseleccionar
        selectedSeats.splice(idx, 1);
        updateSeatUI(seatId, 'free');
    } else {
        // Calcular asientos ya usados (comprados + reservados)
        let myPreUsed = 0;
        Object.values(seatData).forEach(s => {
            if (s.held_by == CURRENT_USER_ID) { // Relaxed check
                if (s.status === 'SOLD' || s.status === 'HELD') {
                    // Solo contar HELD si no expiró
                    if (s.status === 'HELD' && s.hold_until && new Date(s.hold_until) < new Date()) return;
                    myPreUsed++;
                }
            }
        });

        const totalProjected = myPreUsed + selectedSeats.length + 1;

        if (totalProjected > MAX_PER_USER) {
            const diff = MAX_PER_USER - myPreUsed;
            showToast(`Límite alcanzado. Solo puedes tener ${MAX_PER_USER} asientos (ya tienes ${myPreUsed}).`, 'warning');

            // Forzar verificación de overlay si llegamos al límite
            updateLimitStatus();
            return;
        }
        selectedSeats.push(seatId);
        updateSeatUI(seatId, 'selected');
    }

    updateLimitStatus();
    updateSelectionPanel();
}

function updateSeatUI(seatId, state) {
    const btn = document.querySelector(`[data-seat-id="${seatId}"]`);
    if (!btn) return;
    btn.className = `seat seat-${state}`;
}

function updateSelectionPanel() {
    const panel = document.getElementById('selection-panel');
    const listEl = document.getElementById('selected-seats-list');
    const totalEl = document.getElementById('selection-total');

    if (selectedSeats.length === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';

    listEl.innerHTML = selectedSeats
        .sort()
        .map(s => `<span class="seat-tag"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px"><path d="M19 9h-6L10 3H6L3 9h1a2 2 0 0 1 1.7 1h8.6A2 2 0 0 1 16 9h3v10H5v-4"></path><path d="M5 21v-4"></path><path d="M19 21v-4"></path></svg>${s}</span>`)
        .join('');

    const total = selectedSeats.length * EVENT_PRICE;
    totalEl.textContent = `$${total.toFixed(2)}`;
}

// ── HOLD (reserva temporal) ──────────────────────────────────
async function holdSeats() {
    if (selectedSeats.length === 0) return;

    const holdBtn = document.getElementById('btn-hold');
    holdBtn.disabled = true;
    holdBtn.textContent = 'Reservando...';

    try {
        const result = await apiFetch('/api/hold', {
            method: 'POST',
            body: JSON.stringify({ event_id: EVENT_ID, seats: selectedSeats })
        });

        if (!result.ok) {
            throw new Error(result.data.error || 'Error al reservar asientos.');
        }

        heldSeats = result.data.seats || selectedSeats;
        const holdUntil = result.data.hold_until;

        heldSeats.forEach(s => updateSeatUI(s, 'my-hold'));
        selectedSeats = [];

        document.getElementById('selection-panel').style.display = 'none';
        showConfirmPanel(heldSeats, holdUntil);
        showToast('¡Asientos reservados! Confirma tu compra antes de que expire.', 'success');

    } catch (error) {
        showToast(error.message, 'danger');
        holdBtn.disabled = false;
        holdBtn.textContent = '🔒 Reservar (10 min)';
        // Intentar recargar el mapa para sincronizar estado
        await loadSeats();
        selectedSeats = [];
        updateSelectionPanel();
    }
}

function showConfirmPanel(seats, holdUntil) {
    const panel = document.getElementById('confirm-panel');
    panel.style.display = 'block';

    document.getElementById('held-seats-list').innerHTML = seats
        .sort()
        .map(s => `<span class="seat-tag"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px"><path d="M19 9h-6L10 3H6L3 9h1a2 2 0 0 1 1.7 1h8.6A2 2 0 0 1 16 9h3v10H5v-4"></path><path d="M5 21v-4"></path><path d="M19 21v-4"></path></svg>${s}</span>`)
        .join('');

    const total = seats.length * EVENT_PRICE;
    document.getElementById('confirm-total').textContent = `$${total.toFixed(2)}`;

    // Iniciar countdown
    startCountdown(holdUntil);
}

function startCountdown(holdUntil) {
    if (holdTimer) clearInterval(holdTimer);

    // Asegurar que la fecha se interprete como UTC
    let utcString = holdUntil;
    if (!utcString.endsWith('Z') && !utcString.includes('+')) {
        utcString += 'Z';
    }
    const endTime = new Date(utcString).getTime();
    const countdownEl = document.getElementById('hold-countdown');

    holdTimer = setInterval(() => {
        const now = Date.now();
        const remaining = Math.max(0, endTime - now);

        if (remaining <= 0) {
            clearInterval(holdTimer);
            handleExpiration();
            return;
        }

        const mins = Math.floor(remaining / 60000);
        const secs = Math.floor((remaining % 60000) / 1000);
        countdownEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }, 1000);
}

function handleExpiration() {
    isExpired = true;
    const countdownEl = document.getElementById('hold-countdown');
    countdownEl.textContent = '¡Expirado!';

    // Bloquear UI
    document.getElementById('seat-map').classList.add('map-expired');
    document.getElementById('btn-confirm').disabled = true;
    document.getElementById('btn-cancel-hold').disabled = true;

    showToast('Tu reserva ha expirado. Los asientos fueron liberados.', 'danger');

    // Recargar automáticamente después de 3 segundos
    setTimeout(() => location.reload(), 3000);
}

// ── Confirmar compra ─────────────────────────────────────────
async function confirmPurchase() {
    const confirmBtn = document.getElementById('btn-confirm');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Procesando...';

    const result = await apiFetch('/api/purchase', {
        method: 'POST',
        body: JSON.stringify({ event_id: EVENT_ID, seats: heldSeats })
    });

    if (!result.ok) {
        showToast(result.data.error || 'Error al confirmar la compra.', 'danger');
        confirmBtn.disabled = false;
        confirmBtn.textContent = '✅ Confirmar Compra';
        return;
    }

    // Limpiar timer
    if (holdTimer) clearInterval(holdTimer);

    // Actualizar asientos a SOLD
    heldSeats.forEach(s => updateSeatUI(s, 'sold'));

    // Ocultar panel de confirmación
    document.getElementById('confirm-panel').style.display = 'none';

    // Mostrar modal de éxito con tickets
    showSuccessModal(result.data);
}

function showSuccessModal(data) {
    const modal = document.getElementById('success-modal');
    const ticketsList = document.getElementById('tickets-list');

    const tickets = data.tickets || [];
    ticketsList.innerHTML = tickets.map(t => `
        <div class="ticket-result-item">
            <span>Asiento <strong>${t.seat_id}</strong></span>
            <span class="ticket-result-code">${t.code}</span>
        </div>
    `).join('');

    modal.style.display = 'flex';
}

// ── Cancelar HOLD ────────────────────────────────────────────
async function releaseHold() {
    if (heldSeats.length === 0) return;

    // Guardar referencia antes de limpiar
    const seatsToRelease = [...heldSeats];

    const result = await apiFetch('/api/release', {
        method: 'POST',
        body: JSON.stringify({ event_id: EVENT_ID, seats: seatsToRelease })
    });

    if (holdTimer) clearInterval(holdTimer);

    // Resetear visualmente los asientos a verde (FREE) inmediatamente
    seatsToRelease.forEach(s => updateSeatUI(s, 'free'));

    heldSeats = [];
    selectedSeats = [];
    document.getElementById('confirm-panel').style.display = 'none';
    document.getElementById('selection-panel').style.display = 'none';

    // Resetear el botón de reservar para que funcione de nuevo
    const holdBtn = document.getElementById('btn-hold');
    if (holdBtn) {
        holdBtn.disabled = false;
        holdBtn.textContent = '🔒 Reservar (10 min)';
    }

    showToast('Reserva cancelada. Los asientos están disponibles nuevamente.', 'info');

    // Esperar un momento para que el servidor procese y luego recargar
    setTimeout(() => loadSeats(), 500);
}

// ── Verificar holds existentes ───────────────────────────────
function checkExistingHolds() {
    const myHolds = [];
    let earliestHoldUntil = null;

    for (const [seatId, seat] of Object.entries(seatData)) {
        if (seat.status === 'HELD' && seat.held_by == CURRENT_USER_ID && seat.hold_until) { // Relaxed check
            const holdEnd = new Date(seat.hold_until);
            if (holdEnd > new Date()) {
                myHolds.push(seatId);
                if (!earliestHoldUntil || holdEnd < new Date(earliestHoldUntil)) {
                    earliestHoldUntil = seat.hold_until;
                }
            }
        }
    }

    if (myHolds.length > 0) {
        heldSeats = myHolds;
        showConfirmPanel(heldSeats, earliestHoldUntil);
    }
}

// ── Estado de Límites (UX v13) ───────────────────────────────
function updateLimitStatus() {
    let myPreUsed = 0;
    // Contar comprados + holds activos
    Object.values(seatData).forEach(s => {
        if (s.held_by == CURRENT_USER_ID) {
            if (s.status === 'SOLD' || (s.status === 'HELD' && s.hold_until && new Date(s.hold_until) > new Date())) {
                myPreUsed++;
            }
        }
    });

    const total = myPreUsed + selectedSeats.length;
    const max = Number(MAX_PER_USER);
    const remaining = max - total;
    const percentage = Math.min((total / max) * 100, 100);

    const bar = document.getElementById('limit-status-bar');
    const mainText = document.getElementById('limit-main-text');
    const subText = document.getElementById('limit-sub-text');
    const count = document.getElementById('limit-count');
    const fill = document.getElementById('limit-progress-fill');

    if (!bar) return;

    bar.style.display = 'flex'; // Asegurar visible
    count.textContent = `${total}/${max}`;

    // Animate width
    requestAnimationFrame(() => {
        fill.style.width = `${percentage}%`;
    });

    // Reset classes
    bar.classList.remove('limit-warning', 'limit-reached');

    if (total >= max) {
        bar.classList.add('limit-reached');
        mainText.textContent = "¡Límite alcanzado!";
        subText.textContent = `Has completado tus ${max} boletos.`;
        fill.style.backgroundColor = 'var(--danger)';
    } else if (remaining <= 2 && max > 2) {
        bar.classList.add('limit-warning');
        mainText.textContent = "Casi completas tu cupo";
        subText.textContent = `Te quedan ${remaining} boleto(s).`;
        fill.style.backgroundColor = 'var(--warning)';
    } else {
        mainText.textContent = "Selección de boletos";
        subText.textContent = `Puedes seleccionar ${remaining} más.`;
        fill.style.backgroundColor = 'var(--info)';
    }
}

// function hideLimitOverlay() removed

function clearSelection() {
    // Restaurar UI de todos los seleccionados
    selectedSeats.forEach(seatId => {
        updateSeatUI(seatId, 'free');
    });

    // Vaciar array
    selectedSeats = [];

    // Actualizar paneles y overlay
    updateSelectionPanel();
    updateLimitStatus();
}
