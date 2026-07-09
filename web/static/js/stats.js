// --- Tab 3: Statistics Tab Analytics ---

async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        if (!res.ok) throw new Error("Status code: " + res.status);
        const data = await res.json();
        
        // Total stats
        const totalAll = data.totals.total || 0;
        const successAll = data.totals.success_count || 0;
        const failureAll = data.totals.failure_count || 0;
        const crAll = totalAll > 0 ? Math.round((successAll / totalAll) * 100) : 0;

        document.getElementById('stats-total-all').innerText = totalAll;
        document.getElementById('stats-success-all').innerText = successAll;
        document.getElementById('stats-failure-all').innerText = failureAll;
        document.getElementById('stats-cr-all').innerText = crAll + '%';

        // Today stats
        const totalToday = data.today.total || 0;
        const successToday = data.today.success_count || 0;
        const failureToday = data.today.failure_count || 0;
        const crToday = totalToday > 0 ? Math.round((successToday / totalToday) * 100) : 0;

        document.getElementById('stats-total-today').innerText = totalToday;
        document.getElementById('stats-success-today').innerText = successToday;
        document.getElementById('stats-failure-today').innerText = failureToday;
        document.getElementById('stats-cr-today').innerText = crToday + '%';

        // Bank stats table
        const tableBody = document.getElementById('stats-banks-table-body');
        if (!tableBody) return;
        tableBody.innerHTML = '';
        
        if (!data.banks || data.banks.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" class="empty-state">Немає статистики верифікацій</td></tr>';
            return;
        }

        data.banks.forEach(b => {
            const total = b.total || 0;
            const success = b.success || 0;
            const failure = b.failure || 0;
            const cr = total > 0 ? Math.round((success / total) * 100) : 0;
            const avgMin = Math.floor((b.avg_duration || 0) / 60);
            const avgSec = (b.avg_duration || 0) % 60;
            const avgFormatted = avgMin > 0 ? `${avgMin}м ${avgSec}с` : `${avgSec}с`;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-weight: 600;">${b.bank}</td>
                <td>${total}</td>
                <td style="color: var(--accent-success);">${success}</td>
                <td style="color: var(--accent-danger);">${failure}</td>
                <td>${cr}%</td>
                <td>${avgFormatted}</td>
            `;
            tableBody.appendChild(tr);
        });
    } catch (err) {
        showToast("Не вдалося завантажити статистику", "error");
    }
}

async function clearStats() {
    const confirmed = await showConfirm("Ви впевнені, що хочете очистити всю статистику верифікацій? Цю дію неможливо скасувати.", "danger");
    if (!confirmed) return;

    try {
        const res = await fetch('/api/stats/clear', {
            method: 'POST'
        });
        if (res.ok) {
            showToast("Статистику успішно очищено!", "success");
            await loadStats();
        } else {
            const err = await res.json();
            showToast("Помилка очищення: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Помилка відправки запиту", "error");
    }
}
