// --- Chart ---
const ctx = document.getElementById("capitalChart").getContext("2d");
const capitalChart = new Chart(ctx, {
    type: "line",
    data: {
        labels: [],
        datasets: [{
            label: "Capital ($)",
            data: [],
            borderColor: "#8b5cf6",
            backgroundColor: "rgba(139,92,246,0.1)",
            fill: true,
            tension: 0.3,
            pointRadius: 2,
        }],
    },
    options: {
        responsive: true,
        scales: {
            x: { ticks: { color: "#64748b", maxTicksLimit: 10 }, grid: { color: "#1e293b" } },
            y: { ticks: { color: "#64748b", callback: v => "$" + v }, grid: { color: "#1e293b" } },
        },
        plugins: { legend: { display: false } },
    },
});

// --- Helpers ---
const $id = id => document.getElementById(id);
const pnlColor = v => v >= 0 ? "text-emerald-400" : "text-red-400";
const pnlSign  = v => v >= 0 ? "+" : "";
function esc(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function formatTime(iso) {
    if (!iso) return "-";
    return new Date(iso).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

const STAGE_LABELS = ["Abierta", "1/3 vendido", "2/3 vendido", "Cerrada"];

// --- Update UI ---
function updateUI(data) {
    const running = data.bot_status === "running";
    const badge = $id("bot-status-badge");
    badge.className = "flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium " +
        (running ? "bg-violet-900/50 text-violet-300" : "bg-red-900/50 text-red-300");
    $id("status-dot").className = "w-2 h-2 rounded-full " + (running ? "bg-violet-400 pulse-dot" : "bg-red-400");
    $id("status-text").textContent = running ? "Corriendo" : "Detenido";
    $id("btn-start").classList.toggle("hidden", running);
    $id("btn-stop").classList.toggle("hidden", !running);

    $id("m-capital").textContent    = "$" + data.capital_total.toFixed(2);
    $id("m-disponible").textContent = "$" + data.capital_disponible.toFixed(2);

    const pnlEl = $id("m-pnl");
    pnlEl.textContent = pnlSign(data.pnl) + "$" + data.pnl.toFixed(2);
    pnlEl.className   = "text-xl font-bold mt-1 " + pnlColor(data.pnl);

    const roiEl = $id("m-roi");
    roiEl.textContent = pnlSign(data.roi) + data.roi.toFixed(2) + "%";
    roiEl.className   = "text-xl font-bold mt-1 " + pnlColor(data.roi);

    $id("m-wl").textContent      = data.won + " / " + data.lost;
    $id("m-tracked").textContent = data.tracked_markets || 0;
    $id("m-trend").textContent   = data.trend_ready || 0;
    $id("m-scans").textContent   = data.scan_count;

    lastPriceUpdateISO = data.last_price_update || null;
    priceThreadAlive   = data.price_thread_alive ?? true;
    updatePriceBadge();

    updateInsights(data.insights);

    // Chart
    const hist = data.capital_history || [];
    capitalChart.data.labels           = hist.map(h => formatTime(h.time));
    capitalChart.data.datasets[0].data = hist.map(h => h.capital);
    capitalChart.update();

    // Open positions
    const openTb  = $id("table-open");
    const openPos = data.open_positions || [];
    if (openPos.length === 0) {
        openTb.innerHTML = "";
        $id("no-open").classList.remove("hidden");
    } else {
        $id("no-open").classList.add("hidden");
        openTb.innerHTML = openPos.map(p => {
            const stage = p.exit_stage || 0;
            const stageLabel = STAGE_LABELS[stage] || stage;
            const stageBadge = stage > 0
                ? `<span class="text-xs text-amber-400 ml-1">${stageLabel}</span>`
                : "";
            return `
            <tr class="border-b border-gray-800">
                <td class="q py-2 pr-3">${esc(p.question)}${stageBadge}</td>
                <td class="num py-2 pr-3 text-violet-300">${(p.entry_yes * 100).toFixed(1)}&cent;</td>
                <td class="num py-2 pr-3 font-semibold">${(p.current_yes * 100).toFixed(1)}&cent;</td>
                <td class="num py-2 pr-3 text-gray-400 text-xs">${stageLabel}</td>
                <td class="num py-2 pr-3">$${p.allocated.toFixed(2)}</td>
                <td class="num py-2 ${pnlColor(p.pnl)}">${pnlSign(p.pnl)}$${p.pnl.toFixed(2)}</td>
            </tr>`;
        }).join("");
    }

    // Opportunities
    const oppsTb = $id("table-opps");
    const opps   = data.last_opportunities || [];
    if (opps.length === 0) {
        oppsTb.innerHTML = "";
        $id("no-opps").classList.remove("hidden");
    } else {
        $id("no-opps").classList.add("hidden");
        oppsTb.innerHTML = opps.map(o => {
            const inRange  = o.yes_price >= 0.22 && o.yes_price <= 0.27;
            const hasTrend = o.has_trend;
            const rowClass = inRange
                ? "border-b border-violet-900/40 bg-violet-900/10"
                : "border-b border-gray-800";
            const trendIcon = hasTrend ? "⬆ trend" : (o.trend_obs >= 4 ? "≈ stable" : "⏳");
            const trendColor = hasTrend ? "text-emerald-400" : (o.trend_obs >= 4 ? "text-yellow-400" : "text-gray-500");
            return `
            <tr class="${rowClass}">
                <td class="q py-2 pr-3">${esc(o.question)}</td>
                <td class="num py-2 pr-3 ${inRange ? 'text-violet-300 font-semibold' : ''}">${(o.yes_price * 100).toFixed(1)}&cent;</td>
                <td class="num py-2 pr-3 text-gray-400">${o.trend_obs || 0}</td>
                <td class="num py-2 pr-3 text-xs ${trendColor}">${trendIcon}</td>
                <td class="num py-2">$${(o.volume || 0).toLocaleString()}</td>
            </tr>`;
        }).join("");
    }

    // Closed trades
    const closedTb = $id("table-closed");
    const closed   = data.closed_positions || [];
    if (closed.length === 0) {
        closedTb.innerHTML = "";
        $id("no-closed").classList.remove("hidden");
    } else {
        $id("no-closed").classList.add("hidden");
        closedTb.innerHTML = closed.map(c => {
            const statusColor =
                c.status === "WON"       ? "text-emerald-400" :
                c.status === "PARTIAL_1" ? "text-violet-400"  :
                c.status === "PARTIAL_2" ? "text-blue-400"    :
                c.status === "STOPPED"   ? "text-yellow-400"  :
                c.status === "LOST"      ? "text-red-400"     : "text-gray-400";
            return `
            <tr class="border-b border-gray-800">
                <td class="q py-2 pr-3">${esc(c.question)}</td>
                <td class="num py-2 pr-3 text-violet-300">${(c.entry_yes * 100).toFixed(1)}&cent;</td>
                <td class="num py-2 pr-3">$${c.allocated.toFixed(2)}</td>
                <td class="num py-2 pr-3 ${pnlColor(c.pnl)}">${pnlSign(c.pnl)}$${c.pnl.toFixed(2)}</td>
                <td class="num py-2 pr-3 font-semibold ${statusColor}">${c.status}</td>
                <td class="res py-2 pr-3">${esc(c.resolution || "-")}</td>
                <td class="num py-2">${formatTime(c.close_time)}</td>
            </tr>`;
        }).join("");
    }
}

// --- Polling ---
async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        if (res.ok) updateUI(await res.json());
    } catch(e) { console.error(e); }
}

function winRateBar(rate) {
    const pct   = (rate * 100).toFixed(0);
    const color = rate >= 0.7 ? "bg-emerald-500" : rate >= 0.5 ? "bg-yellow-500" : "bg-red-500";
    return `<div class="flex items-center gap-2">
        <div class="flex-1 bg-gray-700 rounded-full h-1.5">
            <div class="${color} h-1.5 rounded-full" style="width:${pct}%"></div>
        </div>
        <span class="text-xs text-gray-300 w-8 text-right">${pct}%</span>
    </div>`;
}

function updateInsights(ins) {
    const panel = $id("insights-panel");
    if (!ins) { panel.classList.add("hidden"); return; }
    panel.classList.remove("hidden");
    $id("insights-trades").textContent =
        `Win rate: ${(ins.overall_win_rate*100).toFixed(0)}% (${ins.total_trades} trades)`;
    $id("insights-city").innerHTML = ins.by_city.map(c =>
        `<div class="mb-1"><div class="flex justify-between text-xs text-gray-400 mb-0.5">
            <span>${c.city}</span><span class="text-gray-500">${c.trades} trades</span>
        </div>${winRateBar(c.win_rate)}</div>`
    ).join("") || '<p class="text-gray-600 text-xs">Mínimo 2 trades por ciudad</p>';
    $id("insights-hour").innerHTML = ins.by_hour.map(h =>
        `<div class="mb-1"><div class="flex justify-between text-xs text-gray-400 mb-0.5">
            <span>${String(h.hour).padStart(2,"0")}:00 UTC</span><span class="text-gray-500">${h.trades} trades</span>
        </div>${winRateBar(h.win_rate)}</div>`
    ).join("") || '<p class="text-gray-600 text-xs">Mínimo 2 trades por hora</p>';
}

async function startBot() { await fetch("/api/bot/start", {method:"POST"}); fetchStatus(); }
async function stopBot()  { await fetch("/api/bot/stop",  {method:"POST"}); fetchStatus(); }

// --- Price badge ---
let lastPriceUpdateISO = null;
let priceThreadAlive   = false;

function updatePriceBadge() {
    const dot   = $id("price-badge-dot");
    const txt   = $id("price-badge-txt");
    const badge = $id("price-badge");
    if (!lastPriceUpdateISO) {
        badge.className = "flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-gray-700 text-gray-400";
        dot.className   = "w-1.5 h-1.5 rounded-full bg-gray-500";
        txt.textContent = "Precios: sin datos";
        return;
    }
    const secAgo = Math.round((Date.now() - new Date(lastPriceUpdateISO).getTime()) / 1000);
    txt.textContent = "Precios: hace " + secAgo + "s";
    if (!priceThreadAlive) {
        badge.className = "flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-red-900/60 text-red-300";
        dot.className   = "w-1.5 h-1.5 rounded-full bg-red-400";
    } else if (secAgo < 60) {
        badge.className = "flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-violet-900/60 text-violet-300";
        dot.className   = "w-1.5 h-1.5 rounded-full bg-violet-400 pulse-dot";
    } else if (secAgo < 120) {
        badge.className = "flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-yellow-900/60 text-yellow-300";
        dot.className   = "w-1.5 h-1.5 rounded-full bg-yellow-400";
    } else {
        badge.className = "flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-red-900/60 text-red-300";
        dot.className   = "w-1.5 h-1.5 rounded-full bg-red-400";
    }
}

setInterval(updatePriceBadge, 1000);
fetchStatus();
setInterval(fetchStatus, 5000);
