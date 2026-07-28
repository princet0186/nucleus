import { useCallback, useEffect, useMemo, useState } from "react";
import MapView from "./MapView";
import "./MapPanel.css";
import {
  createPoi,
  deletePoi,
  formatDistance,
  kindColor,
  listFacilities,
  listPois,
  mapStatus,
  resolvePosition,
  searchFacilities,
  wipePois,
} from "../lib/mapsApi";

/**
 * The map sidebar. Driven either by a chat answer (`payload`) or by its own
 * search controls on the standalone page.
 *
 * Two things it must never do:
 *   - imply a road route. The backend returns a straight-line bearing and no
 *     ETA; the line is dashed and the caveat is always visible.
 *   - flatten provenance. An operator pin is one person's word and is marked
 *     UNVERIFIED everywhere it appears.
 */

const KIND_GROUPS = [
  { value: "", label: "All" },
  { value: "medical", label: "Medical" },
  { value: "evac", label: "Evac" },
  { value: "support", label: "Support" },
  { value: "hospital", label: "Hospital only" },
  { value: "helipad", label: "Helipad only" },
];

// One-tap "what's near me" — the OpenStreetMap-survey edge. Each searches that
// category from the operator's position (or the region centre).
const QUICK_CATEGORIES = [
  { kind: "hospital", label: "🏥 Hospitals" },
  { kind: "clinic", label: "➕ Clinics" },
  { kind: "pharmacy", label: "💊 Pharmacies" },
  { kind: "helipad", label: "🚁 Helipads" },
  { kind: "fire_station", label: "🚒 Fire" },
  { kind: "police", label: "🚓 Police" },
  { kind: "fuel", label: "⛽ Fuel" },
  { kind: "water_point", label: "💧 Water" },
  { kind: "shelter", label: "🏠 Shelter" },
];

/** "28.61, 77.20" is coordinates; anything else is treated as an MGRS grid. */
const COORD_RE = /^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$/;

function originBody(text) {
  const coords = COORD_RE.exec(text);
  if (coords) return { lat: Number(coords[1]), lon: Number(coords[2]) };
  return { grid: text.trim() };
}

export default function MapPanel({ payload, variant = "sidebar", onClose }) {
  const [status, setStatus] = useState(null);
  const [region, setRegion] = useState(null);
  // Basemap look, remembered across sessions. "day" = light street map
  // (Google-maps-like), "night" = dark tactical.
  const [theme, setTheme] = useState(() => localStorage.getItem("nucleus.mapTheme") || "day");

  const [originText, setOriginText] = useState("");
  const [origin, setOrigin] = useState(null);
  const [facilities, setFacilities] = useState([]);
  const [overview, setOverview] = useState([]); // all region facilities, no position
  const [route, setRoute] = useState(null);
  const [warning, setWarning] = useState("");

  const [kinds, setKinds] = useState("");
  const [radiusKm, setRadiusKm] = useState(25);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [focusId, setFocusId] = useState(null);

  const [pinMode, setPinMode] = useState(false);
  const [draftPin, setDraftPin] = useState(null);
  const [markText, setMarkText] = useState("");
  const [poiKinds, setPoiKinds] = useState([]);
  const [myPois, setMyPois] = useState([]);
  const [poiForm, setPoiForm] = useState({ name: "", kind: "waypoint", note: "" });

  useEffect(() => {
    mapStatus()
      .then((data) => {
        setStatus(data);
        setRegion(data.default_region || data.regions[0]?.region || null);
      })
      .catch((err) => setError(err.message));
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      const next = prev === "day" ? "night" : "day";
      localStorage.setItem("nucleus.mapTheme", next);
      return next;
    });
  };

  const refreshPois = useCallback(() => {
    listPois()
      .then((data) => {
        setPoiKinds(data.kinds);
        setMyPois(data.pois);
        setPoiForm((form) => ({ ...form, kind: form.kind || data.kinds[0]?.kind }));
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(refreshPois, [refreshPois]);

  // Load every facility in the region ONLY for a basemap-less region, so the map
  // opens with content it would otherwise lack. With a basemap the tiles already
  // draw POIs, and overlaying thousands of DOM markers buries the canvas and
  // blocks click-to-mark — so we skip the overview entirely there.
  useEffect(() => {
    if (!region || !status) return undefined;
    const entry = status.regions.find((r) => r.region === region);
    if (entry?.has_tiles) {
      setOverview([]);
      return undefined;
    }
    let active = true;
    listFacilities(region)
      .then((data) => {
        if (active) setOverview(data.facilities || []);
      })
      .catch(() => {
        if (active) setOverview([]);
      });
    return () => {
      active = false;
    };
  }, [region, status, myPois]); // re-run after a pin is added/removed

  // Adopt whatever the chat resolved. The chat is authoritative here: it already
  // ran intent detection, origin parsing, search and routing on-device.
  useEffect(() => {
    if (!payload) return;
    setFacilities(payload.facilities || []);
    setRoute(payload.route || null);
    setWarning(payload.warning || "");
    if (payload.origin) {
      setOrigin(payload.origin);
      setOriginText(payload.origin.grid);
    }
    if (payload.region) setRegion(payload.region);
    if (payload.kinds?.length === 1) setKinds(payload.kinds[0]);
  }, [payload]);

  // Core search: takes an explicit position body ({grid} or {lat,lon}) and a
  // kind. The form, the category chips, and the map's "nearby here" all funnel
  // through this so behaviour stays identical however the search was triggered.
  const doSearch = async ({ body, kind }) => {
    if (busy) return;
    setBusy(true);
    setError("");
    setRoute(null);
    try {
      const data = await searchFacilities({
        ...body,
        kinds: kind ? [kind] : [],
        radius_km: Number(radiusKm),
        region,
      });
      setOrigin(data.origin);
      if (data.origin) setOriginText(data.origin.grid);
      setFacilities(data.facilities);
      setWarning(data.facilities.length ? "" : `No matching facility within ${radiusKm} km.`);
    } catch (err) {
      setError(err.message);
      setFacilities([]);
    } finally {
      setBusy(false);
    }
  };

  const runSearch = (event) => {
    event?.preventDefault();
    if (!originText.trim()) return;
    doSearch({ body: originBody(originText), kind: kinds });
  };

  // Where a category search originates: the operator's set position, else the
  // typed coordinate, else the centre of the region they're looking at.
  const searchOriginBody = () => {
    if (origin) return { lat: origin.lat, lon: origin.lon };
    if (originText.trim()) return originBody(originText);
    if (regionCenter) return { lat: regionCenter[1], lon: regionCenter[0] };
    return null;
  };

  // A category chip: search that kind from the best available origin.
  const searchCategory = (kind) => {
    setKinds(kind);
    const body = searchOriginBody();
    if (!body) {
      setError("Set your position (or search a coordinate) first.");
      return;
    }
    doSearch({ body, kind });
  };

  // "Nearby facilities here" from the map context menu: search from the clicked
  // point, honouring the currently selected category.
  const searchHere = (lat, lon) => doSearch({ body: { lat, lon }, kind: kinds });

  const addNoteAt = (lat, lon) => {
    setPinMode(false);
    setDraftPin({ lat, lon });
  };

  /**
   * Draw the straight line from the operator to a facility.
   *
   * Every number here (distance, bearing, compass) was computed by the backend
   * and travels on the facility record — nothing is recalculated in the browser.
   * Only the two-point geometry is assembled, and it is dashed and captioned as
   * straight-line so it is never read as a road.
   */
  const selectFacility = (facility) => {
    setFocusId(facility.id);
    if (!origin) return;
    setRoute({
      geometry: [
        [origin.lon, origin.lat],
        [facility.lon, facility.lat],
      ],
      distance_km: facility.distance_km,
      bearing_deg: facility.bearing_deg,
      compass: facility.compass,
      is_straight_line: true,
      duration_min: null,
      provider: "straight_line",
    });
  };

  const handleMapClick = useCallback(
    ({ lat, lon }) => {
      if (!pinMode) return;
      setDraftPin({ lat, lon });
      setPinMode(false);
    },
    [pinMode]
  );

  // Mark an exact coordinate by typing it — an MGRS grid or "lat, lon" — instead
  // of clicking the map. Opens the same save form at the resolved point.
  const markCoordinate = async (event) => {
    event?.preventDefault();
    if (!markText.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const pos = await resolvePosition(markText);
      setDraftPin({ lat: pos.lat, lon: pos.lon });
      setPinMode(false);
      setMarkText("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const savePin = async (event) => {
    event.preventDefault();
    if (!draftPin || !poiForm.name.trim()) return;
    setBusy(true);
    setError("");
    try {
      await createPoi({
        name: poiForm.name.trim(),
        kind: poiForm.kind,
        note: poiForm.note.trim(),
        lat: draftPin.lat,
        lon: draftPin.lon,
      });
      setDraftPin(null);
      setPoiForm({ name: "", kind: poiForm.kind, note: "" });
      refreshPois();
      // Re-run the current search so the new mark shows up ranked immediately.
      if (originText.trim()) doSearch({ body: originBody(originText), kind: kinds });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const removePin = async (id) => {
    try {
      await deletePoi(id);
      refreshPois();
      setFacilities((list) => list.filter((f) => f.id !== id));
    } catch (err) {
      setError(err.message);
    }
  };

  const handleWipePins = async () => {
    const ok = window.confirm(
      "Delete every operator pin on this device? Surveyed OSM facilities are unaffected."
    );
    if (!ok) return;
    try {
      const { wiped } = await wipePois();
      refreshPois();
      setFacilities((list) => list.filter((f) => f.source !== "operator"));
      setError(wiped ? "" : "No pins to delete.");
    } catch (err) {
      setError(err.message);
    }
  };

  const noRegion = status && status.regions.length === 0;
  const activeRegion = useMemo(
    () => status?.regions.find((r) => r.region === region),
    [status, region]
  );
  const hasPoiIndex = activeRegion?.poi_index?.present;
  // A region can carry a facility index and no basemap. That is a supported
  // deployment (megabytes instead of gigabytes), so distinguish "no map data at
  // all" from "no terrain to draw under correct pins".
  const hasTiles = Boolean(activeRegion?.has_tiles);
  const facilityCount = activeRegion?.poi_index?.facilities;

  // The operator's own pins, shaped like facilities so MapView can plot them.
  const operatorPins = useMemo(
    () => myPois.map((p) => ({ ...p, source: "operator", verified: false })),
    [myPois]
  );

  // What to draw as markers:
  //   - a search is active  -> its ranked results
  //   - basemap present     -> only the operator's own pins (tiles draw the rest)
  //   - no basemap          -> the full indexed overview, or nothing would show
  // This is the fix for a dense city: never overlay thousands of OSM markers on
  // top of a basemap that already shows them — it buried the canvas and made
  // click-to-mark impossible.
  let shownFacilities;
  if (facilities.length) shownFacilities = facilities;
  else if (hasTiles) shownFacilities = operatorPins;
  else shownFacilities = overview;
  const regionCenter = activeRegion?.center || null;

  return (
    <aside className={`map-panel ${variant === "page" ? "map-panel-page" : ""}`}>
      <header className="map-panel-head">
        <div>
          <span className="map-panel-title">Offline Map</span>
          <span className="map-panel-sub">
            {noRegion ? "no basemap installed" : activeRegion?.region || "…"}
          </span>
        </div>
        <div className="map-head-actions">
          {hasTiles && (
            <button
              className="map-icon-btn"
              onClick={toggleTheme}
              title={theme === "day" ? "Switch to night map" : "Switch to day map"}
            >
              {theme === "day" ? "🌙" : "☀️"}
            </button>
          )}
          {status?.regions.length > 1 && (
            <select
              className="map-select"
              value={region || ""}
              onChange={(e) => setRegion(e.target.value)}
            >
              {status.regions.map((r) => (
                <option key={r.region} value={r.region}>
                  {r.region}
                </option>
              ))}
            </select>
          )}
          {onClose && (
            <button className="map-icon-btn" onClick={onClose} title="Close map">
              ✕
            </button>
          )}
        </div>
      </header>

      {noRegion && (
        <div className="map-banner warn">
          No map data installed. Build a region to search facilities:
          <code>./tools/build_region.sh monaco monaco</code>
        </div>
      )}
      {status && !noRegion && !hasTiles && (
        <div className="map-banner info">
          <strong>{facilityCount ?? 0} facilities</strong> indexed, no basemap installed. Pins and
          bearings below are exact — there is simply no terrain drawn under them.
          <code>./tools/build_region.sh {region} &lt;geofabrik-area&gt;</code>
        </div>
      )}
      {status && !noRegion && !hasPoiIndex && (
        <div className="map-banner warn">
          Region <strong>{region}</strong> has no facility index — only your own pins are
          searchable. Rebuild with <code>tools/build_poi_index.py</code>.
        </div>
      )}

      <div className="map-canvas-wrap">
        <MapView
          region={hasTiles ? region : null}
          origin={origin}
          facilities={shownFacilities}
          route={route}
          focusId={focusId}
          center={regionCenter}
          theme={theme}
          pinMode={pinMode}
          onMapClick={handleMapClick}
          onAddNoteAt={addNoteAt}
          onSearchAt={searchHere}
        />
        {pinMode ? (
          <div className="map-pin-hint">Click the map to place the pin</div>
        ) : (
          <div className="map-pin-hint subtle">Drag to move · scroll to zoom · click to add a note</div>
        )}
        {!facilities.length && overview.length > 0 && (
          <div className="map-overview-hint">
            {overview.length} facilities · enter your position to rank by distance
          </div>
        )}
      </div>

      <form className="map-search" onSubmit={runSearch}>
        <input
          className="map-input"
          placeholder="Your position — 42S WD 1234 5678 or 28.6139, 77.2090"
          value={originText}
          onChange={(e) => setOriginText(e.target.value)}
        />
        <div className="map-search-row">
          <select className="map-select grow" value={kinds} onChange={(e) => setKinds(e.target.value)}>
            {KIND_GROUPS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
          <input
            className="map-input narrow"
            type="number"
            min="1"
            max="200"
            value={radiusKm}
            onChange={(e) => setRadiusKm(e.target.value)}
            title="Search radius (km)"
          />
          <span className="map-unit">km</span>
          <button className="map-btn primary" type="submit" disabled={busy || !originText.trim()}>
            {busy ? "…" : "Find"}
          </button>
        </div>
      </form>

      {/* One-tap nearby categories — surveyed OSM facilities near the operator. */}
      <div className="map-quick-cats">
        {QUICK_CATEGORIES.map((c) => (
          <button
            key={c.kind}
            className={`map-chip ${kinds === c.kind ? "active" : ""}`}
            onClick={() => searchCategory(c.kind)}
            disabled={busy}
            title={`Nearest ${c.label.replace(/^\S+\s/, "").toLowerCase()}`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {error && <div className="map-banner error">{error}</div>}
      {warning && !error && <div className="map-banner warn">{warning}</div>}

      {payload?.needs_origin && (
        <div className="map-banner info">
          Nucleus needs your position to answer that. Enter a grid above and press Find.
        </div>
      )}

      <div className="map-results">
        {facilities.map((facility, index) => (
          // Row, not button: the delete control is itself a button, and nesting
          // one inside another is invalid and unreachable by keyboard.
          <div
            key={facility.id}
            className={`map-result ${focusId === facility.id ? "active" : ""}`}
          >
            <button className="map-result-main" onClick={() => selectFacility(facility)}>
              <span className="map-result-rank" style={{ background: kindColor(facility.kind) }}>
                {index + 1}
              </span>
              <span className="map-result-body">
                <span className="map-result-name">
                  {facility.name}
                  {!facility.verified && <span className="map-badge unverified">UNVERIFIED</span>}
                </span>
                <span className="map-result-meta">
                  {facility.label} · {formatDistance(facility.distance_km)} {facility.compass}
                </span>
                <span className="map-result-grid">{facility.grid}</span>
                {facility.note && <span className="map-result-note">{facility.note}</span>}
              </span>
            </button>
            {facility.source === "operator" && (
              <button
                className="map-icon-btn tiny"
                title="Delete this pin"
                onClick={() => removePin(facility.id)}
              >
                🗑
              </button>
            )}
          </div>
        ))}
      </div>

      {route && (
        <div className="map-route-card">
          <div className="map-route-line">
            <strong>{formatDistance(route.distance_km)}</strong>
            <span>
              bearing {Math.round(route.bearing_deg)}° ({route.compass})
            </span>
          </div>
          {route.is_straight_line && (
            <p className="map-route-caveat">
              Straight-line distance. Road distance runs 20–40% longer, and <strong>no ETA</strong>{" "}
              is given — none can be computed without the road network.
            </p>
          )}
        </div>
      )}

      <section className="map-pins">
        <div className="map-pins-head">
          <span>Your pins ({myPois.length})</span>
          <div>
            <button
              className={`map-btn ${pinMode ? "primary" : ""}`}
              onClick={() => {
                setPinMode((on) => !on);
                setDraftPin(null);
              }}
            >
              {pinMode ? "Cancel" : "Drop pin"}
            </button>
            {myPois.length > 0 && (
              <button className="map-btn danger" onClick={handleWipePins}>
                Wipe
              </button>
            )}
          </div>
        </div>

        {pinMode && (
          <p className="map-pin-privacy">
            Click anywhere on the map to place the marker — or type an exact
            coordinate below.
          </p>
        )}

        {/* Mark an exact coordinate without clicking: MGRS grid or lat, lon. */}
        {!draftPin && (
          <form className="map-mark-row" onSubmit={markCoordinate}>
            <input
              className="map-input"
              placeholder="Mark a coordinate — 42S WD 1234 5678 or 28.6139, 77.2090"
              value={markText}
              onChange={(e) => setMarkText(e.target.value)}
            />
            <button className="map-btn primary" type="submit" disabled={busy || !markText.trim()}>
              Mark
            </button>
          </form>
        )}

        {draftPin && (
          <form className="map-pin-form" onSubmit={savePin}>
            <div className="map-pin-coords">
              {draftPin.lat.toFixed(5)}, {draftPin.lon.toFixed(5)}
            </div>
            <input
              className="map-input"
              placeholder="Name — e.g. Evac point Alpha"
              value={poiForm.name}
              onChange={(e) => setPoiForm({ ...poiForm, name: e.target.value })}
              autoFocus
            />
            <select
              className="map-select"
              value={poiForm.kind}
              onChange={(e) => setPoiForm({ ...poiForm, kind: e.target.value })}
            >
              {poiKinds.map((k) => (
                <option key={k.kind} value={k.kind}>
                  {k.label}
                </option>
              ))}
            </select>
            <input
              className="map-input"
              placeholder="Note (stays on this device)"
              value={poiForm.note}
              onChange={(e) => setPoiForm({ ...poiForm, note: e.target.value })}
            />
            <div className="map-pin-actions">
              <button className="map-btn primary" type="submit" disabled={busy || !poiForm.name.trim()}>
                Save pin
              </button>
              <button className="map-btn" type="button" onClick={() => setDraftPin(null)}>
                Discard
              </button>
            </div>
            <p className="map-pin-privacy">
              Encrypted on this device, including the coordinates. Destroyed by a hard wipe. The
              note is never sent to the cloud.
            </p>
          </form>
        )}

        {!draftPin &&
          myPois.map((poi) => (
            <div key={poi.id} className="map-pin-row">
              <span className="map-pin-dot" style={{ background: kindColor(poi.kind) }} />
              <span className="map-pin-name">
                {poi.name}
                <span className="map-pin-grid">{poi.grid}</span>
              </span>
              <button className="map-icon-btn tiny" onClick={() => removePin(poi.id)} title="Delete">
                🗑
              </button>
            </div>
          ))}
      </section>
    </aside>
  );
}
