const opsStatus = document.getElementById("opsStatus");
const opsLatency = document.getElementById("opsLatency");
const liveFrameMeta = document.getElementById("liveFrameMeta");
const opsLiveFrame = document.getElementById("opsLiveFrame");
const opsLiveFallback = document.getElementById("opsLiveFallback");
const gpsMeta = document.getElementById("gpsMeta");

const plateATitle = document.getElementById("plateATitle");
const plateAImg = document.getElementById("plateAImg");
const plateAFallback = document.getElementById("plateAFallback");
const plateAStatus = document.getElementById("plateAStatus");
const plateAGeo = document.getElementById("plateAGeo");

const plateBTitle = document.getElementById("plateBTitle");
const plateBImg = document.getElementById("plateBImg");
const plateBFallback = document.getElementById("plateBFallback");
const plateBStatus = document.getElementById("plateBStatus");
const plateBGeo = document.getElementById("plateBGeo");

const POLL_MS = 400;

const state = {
    map: null,
    patrolMarker: null,
    headingCone: null,
    pathLine: null,
    pathPoints: [],
    hasCentered: false,
    polling: false,
};

function normalizeStatus(status) {
    const normalized = String(status || "LEGAL").trim().toUpperCase();
    return normalized === "ILLEGAL" ? "ILLEGAL" : "LEGAL";
}

function formatCoord(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(6) : "-";
}

function ensureMap() {
    if (state.map || typeof L === "undefined") {
        return;
    }

    state.map = L.map("opsMap", {
        zoomControl: true,
        attributionControl: true,
    }).setView([20.5937, 78.9629], 5);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
    }).addTo(state.map);

    state.pathLine = L.polyline([], {
        color: "#59d3ff",
        weight: 3,
        opacity: 0.72,
    }).addTo(state.map);
}

function destinationPoint(lat, lon, bearingDeg, distanceMeters) {
    const earthRadius = 6378137;
    const brng = (bearingDeg * Math.PI) / 180;
    const lat1 = (lat * Math.PI) / 180;
    const lon1 = (lon * Math.PI) / 180;
    const ratio = distanceMeters / earthRadius;

    const lat2 = Math.asin(
        Math.sin(lat1) * Math.cos(ratio) +
        Math.cos(lat1) * Math.sin(ratio) * Math.cos(brng)
    );

    const lon2 = lon1 + Math.atan2(
        Math.sin(brng) * Math.sin(ratio) * Math.cos(lat1),
        Math.cos(ratio) - Math.sin(lat1) * Math.sin(lat2)
    );

    return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

function buildHeadingCone(lat, lon, headingDeg) {
    const left = destinationPoint(lat, lon, headingDeg - 24, 30);
    const center = destinationPoint(lat, lon, headingDeg, 42);
    const right = destinationPoint(lat, lon, headingDeg + 24, 30);
    return [
        [lat, lon],
        left,
        center,
        right,
    ];
}

function updateFrame(frame) {
    if (frame && frame.image_b64) {
        opsLiveFrame.src = `data:image/jpeg;base64,${frame.image_b64}`;
        opsLiveFrame.hidden = false;
        opsLiveFallback.hidden = true;
        liveFrameMeta.textContent = `Seq ${frame.sequence_id ?? "-"} | ${frame.updated_at_utc ?? ""}`;
        return;
    }

    opsLiveFrame.hidden = true;
    opsLiveFallback.hidden = false;
    liveFrameMeta.textContent = "No frame available";
}

function updateMap(gps) {
    ensureMap();
    if (!state.map) {
        return;
    }

    if (gps?.latitude == null || gps?.longitude == null) {
        gpsMeta.textContent = "No GPS fix yet";
        return;
    }

    const lat = Number(gps.latitude);
    const lon = Number(gps.longitude);
    const heading = Number(gps.heading_deg);

    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        gpsMeta.textContent = "No GPS fix yet";
        return;
    }

    const latLng = [lat, lon];

    if (!state.patrolMarker) {
        state.patrolMarker = L.circleMarker(latLng, {
            radius: 7,
            color: "#8ce1ff",
            weight: 3,
            fillColor: "#59d3ff",
            fillOpacity: 0.5,
        }).addTo(state.map);
    } else {
        state.patrolMarker.setLatLng(latLng);
    }

    if (
        !state.pathPoints.length ||
        state.pathPoints[state.pathPoints.length - 1][0] !== lat ||
        state.pathPoints[state.pathPoints.length - 1][1] !== lon
    ) {
        state.pathPoints.push([lat, lon]);
        if (state.pathPoints.length > 240) {
            state.pathPoints.shift();
        }
        state.pathLine.setLatLngs(state.pathPoints);
    }

    if (Number.isFinite(heading)) {
        const cone = buildHeadingCone(lat, lon, heading);
        if (!state.headingCone) {
            state.headingCone = L.polygon(cone, {
                color: "#59d3ff",
                weight: 1,
                fillColor: "#59d3ff",
                fillOpacity: 0.24,
            }).addTo(state.map);
        } else {
            state.headingCone.setLatLngs(cone);
        }
    }

    if (!state.hasCentered) {
        state.map.setView(latLng, 17);
        state.hasCentered = true;
    }

    gpsMeta.textContent = `${formatCoord(lat)}, ${formatCoord(lon)} | Heading ${Number.isFinite(heading) ? heading.toFixed(1) : "-"}°`;
}

function setBadge(target, status) {
    const normalized = normalizeStatus(status);
    const cls = normalized === "ILLEGAL" ? "badge-illegal" : "badge-legal";
    target.innerHTML = `<span class="badge ${cls}">${normalized}</span>`;
}

function renderPlateSlot(slot, plate) {
    const isA = slot === "A";
    const title = isA ? plateATitle : plateBTitle;
    const image = isA ? plateAImg : plateBImg;
    const fallback = isA ? plateAFallback : plateBFallback;
    const status = isA ? plateAStatus : plateBStatus;
    const geo = isA ? plateAGeo : plateBGeo;

    if (!plate) {
        title.textContent = "Awaiting parked detection";
        image.hidden = true;
        fallback.hidden = false;
        status.textContent = "-";
        geo.textContent = "-";
        return;
    }

    const plateText = String(plate.plate_text || "DETECTING...").trim().toUpperCase() || "DETECTING...";
    title.textContent = `Plate ${plateText}`;
    setBadge(status, plate.parking_status);
    geo.textContent = `${formatCoord(plate.latitude)}, ${formatCoord(plate.longitude)}`;

    if (plate.crop_b64) {
        image.src = `data:image/jpeg;base64,${plate.crop_b64}`;
        image.hidden = false;
        fallback.hidden = true;
    } else {
        image.hidden = true;
        fallback.hidden = false;
    }
}

async function fetchOpsState() {
    const response = await fetch("/api/ops/state", {
        headers: { Accept: "application/json" },
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
}

async function pollOnce() {
    if (state.polling) {
        return;
    }

    state.polling = true;
    const started = performance.now();

    try {
        const ops = await fetchOpsState();
        const elapsed = Math.round(performance.now() - started);

        opsStatus.textContent = "Connected";
        opsLatency.textContent = `Polling: ${POLL_MS}ms | RTT ${elapsed}ms`;

        updateFrame(ops.frame);
        updateMap(ops.gps || {});

        const plates = Array.isArray(ops.plates) ? ops.plates : [];
        renderPlateSlot("A", plates[0] || null);
        renderPlateSlot("B", plates[1] || null);
    } catch (error) {
        opsStatus.textContent = "Stream unavailable";
        opsLatency.textContent = `Polling: ${POLL_MS}ms`;
        liveFrameMeta.textContent = `Error: ${error.message}`;
    } finally {
        state.polling = false;
    }
}

ensureMap();
pollOnce();
setInterval(pollOnce, POLL_MS);
