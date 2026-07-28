import MapPanel from "../components/MapPanel";
import "./MapPage.css";

/**
 * Standalone map, for working the offline layer directly: search facilities from
 * any grid, drop and delete operator pins, confirm what a region contains.
 *
 * The chat sidebar is the same component with a `payload` — this page just runs
 * it without one, so its own search controls drive it.
 */
export default function MapPage() {
  return (
    <div className="map-page">
      <div className="map-page-intro">
        <h1>Offline Map</h1>
        <p>
          Nothing here reaches the network like searching, ranking and bearings are
          computed locally, which is why it works with the radio off.
        </p>
      </div>
      <MapPanel variant="page" />
    </div>
  );
}
