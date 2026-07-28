/**
 * Client for the offline maps API.
 *
 * Every call here hits the local backend. Nothing in this file reaches the
 * internet, and nothing should: the whole point of the maps layer is that a
 * position never leaves the device. If you find yourself adding a third-party
 * tile or geocoding URL, that is the bug.
 */

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (response.status === 204) return null;

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      // FastAPI validation errors arrive as a list of {loc, msg}.
      if (Array.isArray(body.detail)) {
        detail = body.detail.map((e) => e.msg).join("; ");
      } else if (body.detail) {
        detail = body.detail;
      }
    } catch {
      /* body was not JSON; keep the status line */
    }
    throw new Error(detail);
  }

  return response.json();
}

/** What is installed and what the map layer can do right now. */
export const mapStatus = () => request("/maps/status");

/** Interpret a chat question without going through /nucleus/query. */
export const resolveMapQuery = (body) =>
  request("/maps/resolve", { method: "POST", body: JSON.stringify(body) });

/**
 * Nearest facilities to a position.
 * Pass either `grid` or `lat`+`lon` — never both; the backend rejects that.
 */
export const searchFacilities = (body) =>
  request("/maps/search", { method: "POST", body: JSON.stringify(body) });

/** Every facility in a region, for a map overview — no origin, no distances. */
export const listFacilities = (region) => {
  const query = region ? `?region=${encodeURIComponent(region)}` : "";
  return request(`/maps/facilities${query}`);
};

/**
 * Resolve a typed position (MGRS grid or "lat, lon") to {lat, lon, grid}.
 * Used to mark an exact coordinate by typing it instead of clicking the map.
 */
export const resolvePosition = (text) => {
  const t = (text || "").trim();
  const coord = /^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$/.exec(t);
  const q = coord
    ? `lat=${coord[1]}&lon=${coord[2]}`
    : `grid=${encodeURIComponent(t)}`;
  return request(`/maps/position?${q}`);
};

export const listPois = () => request("/maps/poi");

export const createPoi = (body) =>
  request("/maps/poi", { method: "POST", body: JSON.stringify(body) });

export const deletePoi = (id) =>
  request(`/maps/poi/${encodeURIComponent(id)}`, { method: "DELETE" });

export const wipePois = () => request("/maps/poi/wipe", { method: "POST" });

/** Style URL for a region and theme, or null when no region is installed. */
export const styleUrl = (region, theme = "day") =>
  region
    ? `/maps/tiles/${encodeURIComponent(region)}/style.json?theme=${encodeURIComponent(theme)}`
    : null;

/**
 * Colour per facility kind. Operator pins are drawn differently regardless of
 * kind (see `verified`), because provenance outranks category when a medic is
 * deciding where to take a casualty.
 */
export const KIND_COLORS = {
  hospital: "#f28b82",
  clinic: "#f6a6a0",
  aid_station: "#fbbcb6",
  doctors: "#e8a0a0",
  pharmacy: "#c98f8f",
  helipad: "#8ab4f8",
  evac_point: "#a5c8fa",
  casualty_collection_point: "#b8d4fb",
  airfield: "#6f9de0",
  fire_station: "#fde293",
  police: "#a3c9f0",
  shelter: "#81c995",
  water_point: "#7fd0c0",
  fuel: "#c5a5f0",
  // Planning markers — operator annotations, distinct from facility hues.
  waypoint: "#8ab4f8",
  objective: "#c58af9",
  hazard: "#f28b82",
  rally_point: "#81c995",
  observation_post: "#fde293",
};

export const kindColor = (kind) => KIND_COLORS[kind] || "#9aa0a6";

/** A grid, or decimal degrees when the position is outside MGRS coverage. */
export const formatDistance = (km) =>
  km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
