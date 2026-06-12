const viewTitle = document.getElementById("viewTitle");
const healthState = document.getElementById("healthState");
const streamState = document.getElementById("streamState");
const metricTotal = document.getElementById("metricTotal");
const metricToday = document.getElementById("metricToday");
const rowsBody = document.getElementById("rows");
const statusFilter = document.getElementById("statusFilter");
const refreshBtn = document.getElementById("refreshBtn");
const autoRefresh = document.getElementById("autoRefresh");
const liveThumb = document.getElementById("liveThumb");
const thumbFallback = document.getElementById("thumbFallback");
const liveMeta = document.getElementById("liveMeta");
const recentPlates = document.getElementById("recentPlates");
const mapMeta = document.getElementById("mapMeta");
const lightbox = document.getElementById("lightbox");
const lightboxImage = document.getElementById("lightboxImage");
const lightboxClose = document.getElementById("lightboxClose");

const viewNames = {
	"overview-view": "Overview",
	"violations-view": "Violations",
	"map-view": "Map View",
};

const appState = {
	violations: [],
	sortKey: "last_seen",
	sortDir: "desc",
	filterStatus: "ALL",
	map: null,
	mapPoints: null,
	mapPath: null,
	lastMapSignature: "",
};

async function fetchJson(url) {
	const response = await fetch(url, { headers: { Accept: "application/json" } });
	if (!response.ok) {
		throw new Error(`HTTP ${response.status}`);
	}
	return response.json();
}

function escapeHtml(value) {
	return String(value ?? "")
		.replaceAll("&", "&amp;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;")
		.replaceAll('"', "&quot;")
		.replaceAll("'", "&#039;");
}

function normalizeStatus(status) {
	const normalized = String(status ?? "LEGAL").trim().toUpperCase();
	return normalized === "ILLEGAL" ? "ILLEGAL" : "LEGAL";
}

function formatNumber(value, digits = 6) {
	if (value === null || value === undefined || value === "") {
		return "-";
	}
	const cast = Number(value);
	if (!Number.isFinite(cast)) {
		return "-";
	}
	return cast.toFixed(digits);
}

function basenameFromPath(pathValue) {
	const raw = String(pathValue || "").trim();
	if (!raw) {
		return "";
	}
	const parts = raw.split(/[\\/]/);
	return parts[parts.length - 1] || "";
}

function screenshotUrlForRow(row) {
	const fileName = basenameFromPath(row.screenshot_path);
	if (!fileName) {
		return null;
	}
	return `/api/screenshots/${encodeURIComponent(fileName)}`;
}

function switchView(viewId) {
	for (const view of document.querySelectorAll(".view")) {
		view.classList.toggle("active", view.id === viewId);
	}
	for (const item of document.querySelectorAll(".nav-item")) {
		item.classList.toggle("active", item.dataset.view === viewId);
	}
	viewTitle.textContent = viewNames[viewId] || "Overview";

	if (viewId === "map-view") {
		ensureMap();
		setTimeout(() => {
			if (appState.map) {
				appState.map.invalidateSize();
			}
		}, 80);
	}
}

function parseSortValue(row, key) {
	if (key === "duration_sec" || key === "latitude" || key === "longitude" || key === "id") {
		const n = Number(row[key]);
		return Number.isFinite(n) ? n : Number.NEGATIVE_INFINITY;
	}
	if (key === "first_seen" || key === "last_seen") {
		const t = Date.parse(row[key] || "");
		return Number.isFinite(t) ? t : Number.NEGATIVE_INFINITY;
	}
	if (key === "parking_status") {
		return normalizeStatus(row.parking_status);
	}
	const fallback = row[key] ?? row.zone_id ?? "";
	return String(fallback).toUpperCase();
}

function getVisibleRows() {
	let rows = [...appState.violations];
	if (appState.filterStatus !== "ALL") {
		rows = rows.filter((row) => normalizeStatus(row.parking_status) === appState.filterStatus);
	}

	rows.sort((a, b) => {
		const left = parseSortValue(a, appState.sortKey);
		const right = parseSortValue(b, appState.sortKey);
		if (left < right) {
			return appState.sortDir === "asc" ? -1 : 1;
		}
		if (left > right) {
			return appState.sortDir === "asc" ? 1 : -1;
		}
		return 0;
	});

	return rows;
}

function renderRows() {
	const rows = getVisibleRows();
	rowsBody.innerHTML = "";

	if (!rows.length) {
		rowsBody.innerHTML = '<tr><td colspan="10">No records found for the selected filter.</td></tr>';
		return;
	}

	for (const row of rows) {
		const tr = document.createElement("tr");
		const status = normalizeStatus(row.parking_status);
		const statusClass = status === "ILLEGAL" ? "badge-illegal" : "badge-legal";
		const imgUrl = screenshotUrlForRow(row);

		tr.innerHTML = `
			<td>${escapeHtml(row.id ?? "-")}</td>
			<td>${escapeHtml(row.license_plate ?? "-")}</td>
			<td><span class="badge ${statusClass}">${status}</span></td>
			<td>${escapeHtml(row.zone_name ?? row.zone_id ?? "-")}</td>
			<td>${escapeHtml(row.first_seen ?? "-")}</td>
			<td>${escapeHtml(row.last_seen ?? "-")}</td>
			<td>${formatNumber(row.duration_sec, 2)}</td>
			<td>${formatNumber(row.latitude, 6)}</td>
			<td>${formatNumber(row.longitude, 6)}</td>
			<td>${imgUrl ? `<button type="button" class="thumb-btn" data-image="${escapeHtml(imgUrl)}">View</button>` : "-"}</td>
		`;

		rowsBody.appendChild(tr);
	}
}

function todayCount(rows) {
	const today = new Date().toISOString().slice(0, 10);
	let count = 0;
	for (const row of rows) {
		const stamp = String(row.last_seen || row.first_seen || "");
		if (stamp.startsWith(today)) {
			count += 1;
		}
	}
	return count;
}

function ensureMap() {
	if (appState.map || typeof L === "undefined") {
		return;
	}

	appState.map = L.map("map", {
		zoomControl: true,
		attributionControl: true,
	}).setView([20.5937, 78.9629], 5);

	L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
		maxZoom: 19,
		attribution: "&copy; OpenStreetMap contributors",
	}).addTo(appState.map);

	appState.mapPoints = L.layerGroup().addTo(appState.map);
	appState.mapPath = L.layerGroup().addTo(appState.map);
}

function refreshMap() {
	ensureMap();
	if (!appState.map || !appState.mapPoints || !appState.mapPath) {
		return;
	}

	appState.mapPoints.clearLayers();
	appState.mapPath.clearLayers();

	const points = [];
	for (const row of appState.violations) {
		const lat = Number(row.latitude);
		const lon = Number(row.longitude);
		if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
			continue;
		}

		const status = normalizeStatus(row.parking_status);
		const color = status === "ILLEGAL" ? "#ff7a66" : "#6ce09a";

		L.circleMarker([lat, lon], {
			radius: 6,
			color,
			weight: 2,
			fillColor: color,
			fillOpacity: 0.35,
		}).bindPopup(
			`<strong>${escapeHtml(row.license_plate ?? "UNKNOWN")}</strong><br>${status}<br>${escapeHtml(row.last_seen ?? "")}`
		).addTo(appState.mapPoints);

		points.push({
			lat,
			lon,
			time: Date.parse(row.last_seen || row.first_seen || "") || 0,
		});
	}

	if (!points.length) {
		mapMeta.textContent = "No coordinates plotted yet.";
		appState.lastMapSignature = "";
		return;
	}

	points.sort((a, b) => a.time - b.time);
	const lineCoords = points.map((p) => [p.lat, p.lon]);
	L.polyline(lineCoords, {
		color: "#59d3ff",
		weight: 2,
		opacity: 0.75,
		dashArray: "6 6",
	}).addTo(appState.mapPath);

	mapMeta.textContent = `${points.length} coordinate point${points.length === 1 ? "" : "s"} plotted`;

	const newest = points[points.length - 1];
	const mapSignature = `${points.length}:${newest.lat.toFixed(6)}:${newest.lon.toFixed(6)}:${newest.time}`;

	if (appState.lastMapSignature !== mapSignature) {
		const bounds = L.latLngBounds(lineCoords);
		if (bounds.isValid()) {
			appState.map.fitBounds(bounds.pad(0.2));
		}
		appState.lastMapSignature = mapSignature;
	}
}

function renderRecentPlates(plates) {
	recentPlates.innerHTML = "";
	if (!Array.isArray(plates) || !plates.length) {
		recentPlates.innerHTML = "<li>No live parked detections right now.</li>";
		return;
	}

	for (const entry of plates.slice(0, 2)) {
		const status = normalizeStatus(entry.parking_status);
		const lat = formatNumber(entry.latitude, 6);
		const lon = formatNumber(entry.longitude, 6);
		const item = document.createElement("li");
		item.innerHTML = `
			<span>${escapeHtml(entry.plate_text || "DETECTING...")}</span>
			<span>${status} | ${lat}, ${lon}</span>
		`;
		recentPlates.appendChild(item);
	}
}

function openLightbox(imageUrl) {
	if (!imageUrl) {
		return;
	}
	lightboxImage.src = imageUrl;
	lightbox.classList.remove("hidden");
}

function closeLightbox() {
	lightbox.classList.add("hidden");
	lightboxImage.src = "";
}

async function refreshHealth() {
	try {
		const health = await fetchJson("/api/health");
		healthState.textContent = health.ok ? "Online" : "Offline";
	} catch (error) {
		healthState.textContent = "Unavailable";
	}
}

async function refreshViolations() {
	const payload = await fetchJson("/api/violations?limit=600");
	appState.violations = Array.isArray(payload.items) ? payload.items : [];
	metricTotal.textContent = String(payload.count ?? appState.violations.length);
	metricToday.textContent = String(todayCount(appState.violations));
	renderRows();
	refreshMap();
}

async function refreshOpsState() {
	try {
		const ops = await fetchJson("/api/ops/state");
		const frame = ops.frame || {};
		if (frame.image_b64) {
			liveThumb.src = `data:image/jpeg;base64,${frame.image_b64}`;
			liveThumb.hidden = false;
			thumbFallback.hidden = true;
			liveMeta.textContent = `Sequence ${frame.sequence_id ?? "-"} | ${frame.updated_at_utc ?? ""}`;
			streamState.textContent = "Connected";
		} else {
			liveThumb.hidden = true;
			thumbFallback.hidden = false;
			streamState.textContent = "Waiting";
		}

		renderRecentPlates(ops.plates || []);
	} catch (error) {
		streamState.textContent = "Unavailable";
		liveMeta.textContent = `Stream error: ${error.message}`;
		liveThumb.hidden = true;
		thumbFallback.hidden = false;
		renderRecentPlates([]);
	}
}

async function refreshAll() {
	await refreshHealth();
	try {
		await refreshViolations();
	} catch (error) {
		metricTotal.textContent = "0";
		metricToday.textContent = "0";
		rowsBody.innerHTML = `<tr><td colspan="10">Failed to load records: ${escapeHtml(error.message)}</td></tr>`;
		mapMeta.textContent = "Could not load coordinates.";
	}
	await refreshOpsState();
}

for (const nav of document.querySelectorAll(".nav-item")) {
	nav.addEventListener("click", () => switchView(nav.dataset.view));
}

for (const th of document.querySelectorAll("th[data-sort]")) {
	th.addEventListener("click", () => {
		const key = th.dataset.sort;
		if (!key) {
			return;
		}
		if (appState.sortKey === key) {
			appState.sortDir = appState.sortDir === "asc" ? "desc" : "asc";
		} else {
			appState.sortKey = key;
			appState.sortDir = "asc";
		}
		renderRows();
	});
}

statusFilter.addEventListener("change", () => {
	appState.filterStatus = statusFilter.value;
	renderRows();
});

rowsBody.addEventListener("click", (event) => {
	const target = event.target;
	if (!(target instanceof HTMLElement)) {
		return;
	}
	const button = target.closest(".thumb-btn");
	if (!button) {
		return;
	}
	openLightbox(button.dataset.image);
});

refreshBtn.addEventListener("click", refreshAll);
lightboxClose.addEventListener("click", closeLightbox);
lightbox.addEventListener("click", (event) => {
	if (event.target === lightbox) {
		closeLightbox();
	}
});
document.addEventListener("keydown", (event) => {
	if (event.key === "Escape") {
		closeLightbox();
	}
});

setInterval(() => {
	if (autoRefresh.checked) {
		refreshHealth();
		refreshViolations().catch(() => {
			return;
		});
	}
}, 3000);

setInterval(() => {
	if (autoRefresh.checked) {
		refreshOpsState();
	}
}, 1200);

refreshAll();
