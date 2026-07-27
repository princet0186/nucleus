"""Offline maps: OpenStreetMap vector tiles, POI search, and map-intent routing.

Everything in this package runs on-device against files in ``settings.TILES_DIR``.
No map query ever reaches the network, because it cannot: the egress sanitizer in
``backend/services/privacy`` tokenizes every grid and coordinate before a prompt
leaves, so the cloud model never receives a position it could resolve.

Layers:
    geo         geodesy primitives + MGRS <-> WGS84 (no deps beyond ``mgrs``)
    mbtiles     read-only MBTiles reader (vector tiles, gzip passthrough)
    catalog     discovers installed regions in TILES_DIR
    style       TileJSON + a self-contained tactical MapLibre style
    poi_index   read-only R*Tree over OSM facilities (public data, not wiped)
    user_poi    operator-added places: Fernet-encrypted, wiped with nucleus.db
    facilities  merged OSM + operator search, provenance-tagged
    routing     RouteProvider seam; straight-line today, Valhalla/OSRM later
    intent      local map-intent detection (regex, zero egress)
    resolver    orchestrates intent -> origin -> facilities -> map payload
"""
