const DATA_URL = "./data/routing-data.json";
const DISPLAY_URL = "./data/network-display.geojson";
const DATA_CACHE_NAME = "gridnberg-data-v1";
const DATA_CACHE_VERSION = "2026-07-02";
const DATA_CACHE_PREFIX = "gridnberg-data-";
const LOADING_MODAL_HIDE_MS = 180;
const MESH_3D_DEFAULT_BOOST = 0;
const NETWORK_INTENSITY_DEFAULT = 50;
const NETWORK_SOURCE_ID = "routing-network";
const NETWORK_LINE_LAYERS = [
  "routing-network-slope-glow",
  "routing-network-slope-core",
];
const DECK_3D_LAYER_ID = "routing-network-3d";
const DECK_3D_BEFORE_LAYER_ID = "route-distance-halo";
const DECK_3D_LINE_WIDTH_PIXELS = 1.65;
const MESH_3D_ALTITUDE_MULTIPLIER = 0.18;
const MESH_3D_VIEW = {
  pitch: 62,
  bearing: -28,
};

const SLOPE_COLOR_STOPS = [
  [0, "#3c2b7d"],
  [2, "#8c34af"],
  [5, "#d93096"],
  [8.33, "#ff207f"],
  [15, "#ff9b67"],
  [25, "#fff8ee"],
];

const SCENARIOS = [
  {
    key: "distance",
    label: "2D shortest",
    color: "#2bd4ff",
    source: "route-distance",
    summaryId: "distance-summary",
    lengthId: "distance-length",
    width: 5.8,
  },
  {
    key: "accessible",
    label: "Accessible",
    color: "#ff9568",
    source: "route-accessible",
    summaryId: "accessible-summary",
    lengthId: "accessible-length",
    width: 4.4,
  },
  {
    key: "comfort",
    label: "Comfort",
    color: "#b72a88",
    source: "route-comfort",
    summaryId: "comfort-summary",
    lengthId: "comfort-length",
    width: 3.3,
  },
];

const COST_INDEX = {
  distance: 0,
  comfortForward: 1,
  comfortReverse: 2,
  accessibleForward: 3,
  accessibleReverse: 4,
};

const state = {
  map: null,
  data: null,
  networkDisplayData: null,
  adjacency: null,
  bounds: null,
  originNode: null,
  destNode: null,
  originMarker: null,
  destMarker: null,
  routeRequest: 0,
  slopeHoverIndex: null,
  slopePopup: null,
  activeSlopeSegmentId: null,
  mesh3dBoost: MESH_3D_DEFAULT_BOOST,
  networkIntensity: NETWORK_INTENSITY_DEFAULT,
  deckOverlay: null,
  deck3dData: null,
  elevationStats: null,
  slopeColorCache: new Map(),
  routeVisibility: {
    distance: true,
    accessible: true,
    comfort: true,
  },
  panelCollapsed: false,
  infoModalReturnFocus: null,
};

const SLOPE_HOVER_INDEX_CELL_SIZE = 0.002;
const SLOPE_HOVER_PIXEL_TOLERANCE = 12;

const ROUTE_SHADOW = {
  blur: 2,
  opacity: 0.92,
  widthPadding: [11, 15, 20],
};

const DEFAULT_ROUTE = {
  origin: [-73.989501, 40.665623],
  destination: [-73.97337292730204, 40.66892073171586],
};

const darkRasterStyle = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    "carto-dark": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    {
      id: "carto-dark",
      type: "raster",
      source: "carto-dark",
      paint: {
        "raster-opacity": 0.82,
        "raster-brightness-min": 0.02,
        "raster-brightness-max": 0.72,
        "raster-saturation": -0.75,
      },
    },
  ],
};

function setStatus(message) {
  document.getElementById("status").textContent = message;
  setLoadingMessage(message);
}

function setLoadingMessage(message, note) {
  const modal = document.getElementById("loading-modal");
  if (!modal || modal.hidden) return;

  const messageEl = document.getElementById("loading-message");
  const noteEl = document.getElementById("loading-note");
  if (messageEl) messageEl.textContent = message;
  if (noteEl && note) noteEl.textContent = note;
}

function hideLoadingModal() {
  const modal = document.getElementById("loading-modal");
  if (!modal || modal.hidden) return;

  modal.setAttribute("aria-busy", "false");
  modal.classList.add("is-hiding");
  window.setTimeout(() => {
    modal.hidden = true;
  }, LOADING_MODAL_HIDE_MS);
}

function showLoadingError(message) {
  const modal = document.getElementById("loading-modal");
  if (!modal) return;

  modal.hidden = false;
  modal.setAttribute("aria-busy", "false");
  modal.classList.remove("is-hiding");
  modal.classList.add("loading-modal--error");

  const title = document.getElementById("loading-title");
  if (title) title.textContent = "Could not load data";
  setLoadingMessage(message, "Check the data files, then refresh the page.");
}

function syncScenarioColors() {
  for (const scenario of SCENARIOS) {
    document.documentElement.style.setProperty(
      `--route-${scenario.key}`,
      scenario.color,
    );
  }
}

function formatMeters(value) {
  if (!Number.isFinite(value)) return "--";
  if (value >= 1000) return `${(value / 1000).toFixed(2)} km`;
  return `${Math.round(value)} m`;
}

function formatSignedMeters(value) {
  if (!Number.isFinite(value)) return "--";
  const rounded = Math.round(value);
  return `${rounded > 0 ? "+" : ""}${rounded} m`;
}

function markerElement(kind, label) {
  const el = document.createElement("div");
  el.className = `pin pin--${kind}`;
  el.innerHTML = `<span>${label}</span>`;
  return el;
}

function createMap() {
  if (!window.maplibregl) {
    setStatus("MapLibre could not load");
    return null;
  }

  setStatus("Initializing map");
  const map = new maplibregl.Map({
    container: "map",
    style: darkRasterStyle,
    center: [-73.98144, 40.66727],
    zoom: 14.35,
    pitch: 0,
    bearing: 0,
    attributionControl: true,
    canvasContextAttributes: { antialias: true },
  });

  map.addControl(
    new maplibregl.NavigationControl({
      visualizePitch: false,
      showCompass: true,
    }),
    "bottom-right",
  );

  let bootstrapped = false;
  const startWhenStyleIsReady = () => {
    if (bootstrapped || !map.isStyleLoaded()) return;
    bootstrapped = true;
    bootstrap().catch((error) => {
      console.error(error);
      const message = error.message || "Could not start app";
      setStatus(message);
      showLoadingError(message);
    });
  };

  map.on("load", startWhenStyleIsReady);
  map.on("style.load", startWhenStyleIsReady);
  map.on("styledata", startWhenStyleIsReady);
  window.setTimeout(startWhenStyleIsReady, 500);

  return map;
}

async function bootstrap() {
  setStatus("Checking local data");
  const { routingData, networkDisplayData } = await loadAppData();

  state.data = routingData;
  state.networkDisplayData = networkDisplayData;
  setStatus(
    `${state.data.segments.length.toLocaleString()} segments loaded; building graph`,
  );

  state.bounds = computeBounds(state.data.nodes);
  addNetworkLayer(state.networkDisplayData);
  addRouteLayers();
  state.adjacency = buildAdjacency(state.data);
  addMarkers();
  wireControls();
  await routeAll({ fit: true });
  setLoadingMessage("Ready", "Data is saved locally for this browser.");
  hideLoadingModal();
}

async function loadAppData() {
  await pruneOldDataCaches();
  const routingData = await loadCachedJson(DATA_URL, "routing data");
  const networkDisplayData = await loadCachedJson(DISPLAY_URL, "slope display");
  return { routingData, networkDisplayData };
}

async function loadCachedJson(url, label) {
  const requestUrl = cacheUrlFor(url);
  const cacheAvailable = "caches" in window;
  let cache = null;

  if (cacheAvailable) {
    try {
      cache = await caches.open(DATA_CACHE_NAME);
      const cached = await cache.match(requestUrl);
      if (cached) {
        setStatus(`Loading saved ${label}`);
        setLoadingMessage(
          `Loading saved ${label}`,
          "Using the local copy stored in this browser.",
        );
        try {
          return await cached.json();
        } catch (error) {
          console.warn(`Cached ${label} could not be read; refreshing.`, error);
          await cache.delete(requestUrl);
        }
      }
    } catch (error) {
      console.warn("Local data cache is unavailable.", error);
      cache = null;
    }
  }

  setStatus(`Downloading ${label}`);
  setLoadingMessage(
    `Downloading ${label}`,
    cache
      ? "Saving a local copy for the next visit."
      : "Local data cache is unavailable in this browser.",
  );

  const response = await fetch(requestUrl);
  if (!response.ok) {
    throw new Error(`Could not load ${url}`);
  }

  const responseForCache = response.clone();
  const json = await response.json();

  if (cache) {
    setLoadingMessage(
      `Saving ${label} locally`,
      "Next visit can use the saved copy.",
    );
    try {
      await cache.put(requestUrl, responseForCache);
    } catch (error) {
      console.warn(`Could not save ${label} locally.`, error);
      setLoadingMessage(
        `${label} loaded`,
        "Browser storage could not keep a local copy.",
      );
    }
  }

  return json;
}

function cacheUrlFor(url) {
  const cacheUrl = new URL(url, window.location.href);
  cacheUrl.searchParams.set("gridnberg-data", DATA_CACHE_VERSION);
  return cacheUrl.toString();
}

async function pruneOldDataCaches() {
  if (!("caches" in window)) return;

  try {
    const cacheNames = await caches.keys();
    await Promise.all(
      cacheNames
        .filter(
          (cacheName) =>
            cacheName.startsWith(DATA_CACHE_PREFIX) &&
            cacheName !== DATA_CACHE_NAME,
        )
        .map((cacheName) => caches.delete(cacheName)),
    );
  } catch (error) {
    console.warn("Could not prune old local data caches.", error);
  }
}

function computeBounds(nodes) {
  const bounds = new maplibregl.LngLatBounds();
  for (const node of nodes) {
    bounds.extend([node[0], node[1]]);
  }
  return bounds;
}

function fitRouteView() {
  const bounds = new maplibregl.LngLatBounds();
  let hasBounds = false;

  if (state.originNode != null) {
    bounds.extend(nodeLngLat(state.originNode));
    hasBounds = true;
  }
  if (state.destNode != null) {
    bounds.extend(nodeLngLat(state.destNode));
    hasBounds = true;
  }

  for (const scenario of SCENARIOS) {
    const source = state.map.getSource(scenario.source);
    const coordinates = source?._data?.features?.[0]?.geometry?.coordinates;
    if (!coordinates) continue;
    for (const coordinate of coordinates) {
      bounds.extend(coordinate);
      hasBounds = true;
    }
  }

  if (!hasBounds) return;

  state.map.fitBounds(bounds, {
    padding: {
      top: 160,
      right: 82,
      bottom: 82,
      left: window.innerWidth > 720 ? 360 : 54,
    },
    duration: 700,
    maxZoom: 14.35,
  });
}

function addNetworkLayer(networkDisplayData) {
  state.map.addSource(NETWORK_SOURCE_ID, {
    type: "geojson",
    data: networkDisplayData,
  });

  state.map.addLayer({
    id: "routing-network-slope-glow",
    type: "line",
    source: NETWORK_SOURCE_ID,
    layout: {
      "line-cap": "round",
      "line-join": "round",
    },
    paint: {
      "line-color": slopeColorExpression(),
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        9,
        0.7,
        12,
        1.6,
        15,
        3.4,
        18,
        6.8,
      ],
      "line-blur": 1.2,
      "line-opacity": 0.52,
    },
  });

  state.map.addLayer({
    id: "routing-network-slope-core",
    type: "line",
    source: NETWORK_SOURCE_ID,
    layout: {
      "line-cap": "round",
      "line-join": "round",
    },
    paint: {
      "line-color": slopeColorExpression(),
      "line-width": [
        "interpolate",
        ["linear"],
        ["zoom"],
        9,
        0.28,
        12,
        0.75,
        15,
        1.75,
        18,
        3.4,
      ],
      "line-opacity": 1,
    },
  });

  updateNetworkLayerStyle();
}

function slopeColorExpression() {
  return [
    "interpolate",
    ["linear"],
    ["get", "steep"],
    ...SLOPE_COLOR_STOPS.flatMap(([value, color]) => [value, color]),
  ];
}

function networkIntensityRatio() {
  return Math.max(0, Math.min(1, state.networkIntensity / 100));
}

function addRouteLayers() {
  for (const scenario of SCENARIOS) {
    state.map.addSource(scenario.source, {
      type: "geojson",
      data: emptyFeatureCollection(),
    });

    state.map.addLayer({
      id: `${scenario.source}-halo`,
      type: "line",
      source: scenario.source,
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": "#040405",
        "line-width": routeShadowWidthExpression(scenario),
        "line-blur": ROUTE_SHADOW.blur,
        "line-opacity": ROUTE_SHADOW.opacity,
      },
    });

    state.map.addLayer({
      id: scenario.source,
      type: "line",
      source: scenario.source,
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": scenario.color,
        "line-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          9,
          Math.max(2, scenario.width - 2),
          14,
          scenario.width,
          18,
          scenario.width + 2.2,
        ],
        "line-opacity": 0.96,
      },
    });
  }
}

function routeShadowWidthExpression(scenario) {
  return [
    "interpolate",
    ["linear"],
    ["zoom"],
    9,
    scenario.width + ROUTE_SHADOW.widthPadding[0],
    14,
    scenario.width + ROUTE_SHADOW.widthPadding[1],
    18,
    scenario.width + ROUTE_SHADOW.widthPadding[2],
  ];
}

function getElevationStats(data) {
  if (state.elevationStats) return state.elevationStats;

  let min = Infinity;
  let max = -Infinity;
  for (const node of data.nodes) {
    const z = node[2];
    if (!Number.isFinite(z)) continue;
    min = Math.min(min, z);
    max = Math.max(max, z);
  }

  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    min = 0;
    max = 1;
  }

  state.elevationStats = {
    min,
    max,
    range: Math.max(1, max - min),
  };
  return state.elevationStats;
}

function emptyFeatureCollection() {
  return {
    type: "FeatureCollection",
    features: [],
  };
}

function buildAdjacency(data) {
  const adjacency = Array.from({ length: data.nodes.length }, () => []);
  for (let i = 0; i < data.segments.length; i += 1) {
    const segment = data.segments[i];
    adjacency[segment.a].push({
      to: segment.b,
      segmentIndex: i,
      reverse: false,
      distance: segment.c[COST_INDEX.distance],
      comfort: segment.c[COST_INDEX.comfortForward],
      accessible: segment.c[COST_INDEX.accessibleForward],
      dz: segment.dz ?? 0,
    });
    adjacency[segment.b].push({
      to: segment.a,
      segmentIndex: i,
      reverse: true,
      distance: segment.c[COST_INDEX.distance],
      comfort: segment.c[COST_INDEX.comfortReverse],
      accessible: segment.c[COST_INDEX.accessibleReverse],
      dz: -(segment.dz ?? 0),
    });
  }
  return adjacency;
}

function addMarkers() {
  const originStart = findNearestNode(DEFAULT_ROUTE.origin);
  const destStart = findNearestNode(DEFAULT_ROUTE.destination);
  state.originNode = originStart;
  state.destNode = destStart;

  state.originMarker = new maplibregl.Marker({
    element: markerElement("origin", "O"),
    draggable: true,
    anchor: "center",
  })
    .setLngLat(nodeLngLat(originStart))
    .addTo(state.map);

  state.destMarker = new maplibregl.Marker({
    element: markerElement("dest", "D"),
    draggable: true,
    anchor: "center",
  })
    .setLngLat(nodeLngLat(destStart))
    .addTo(state.map);

  state.originMarker.on("dragend", () => {
    state.originNode = snapMarkerToNode(state.originMarker);
    routeAll();
  });

  state.destMarker.on("dragend", () => {
    state.destNode = snapMarkerToNode(state.destMarker);
    routeAll();
  });
}

function wireControls() {
  document.getElementById("fit-button").addEventListener("click", fitRouteView);
  wireSlopeHover();
  wireMesh3dControls();

  document.querySelectorAll("[data-route-toggle]").forEach((input) => {
    const key = input.dataset.routeToggle;
    input.checked = state.routeVisibility[key];
    input.addEventListener("change", (event) => {
      setRouteVisibility(key, event.target.checked);
    });
  });
}

function wireMesh3dControls() {
  const slider = document.getElementById("mesh-3d-boost");
  const intensitySlider = document.getElementById("network-intensity");
  if (!slider || !intensitySlider) return;

  state.mesh3dBoost = readMesh3dBoost(slider);
  state.networkIntensity = readNetworkIntensity(intensitySlider);
  syncMesh3dControls();
  updateNetworkLayerStyle();

  slider.addEventListener("input", (event) => {
    setMesh3dBoost(readMesh3dBoost(event.target));
  });

  intensitySlider.addEventListener("input", (event) => {
    setNetworkIntensity(readNetworkIntensity(event.target));
  });
}

function readMesh3dBoost(input) {
  const value = Number(input?.value);
  return Number.isFinite(value) ? value : MESH_3D_DEFAULT_BOOST;
}

function readNetworkIntensity(input) {
  const value = Number(input?.value);
  return Number.isFinite(value) ? value : NETWORK_INTENSITY_DEFAULT;
}

function syncMesh3dControls() {
  const slider = document.getElementById("mesh-3d-boost");
  const output = document.getElementById("mesh-3d-boost-value");
  const intensitySlider = document.getElementById("network-intensity");
  const intensityOutput = document.getElementById("network-intensity-value");

  if (slider) slider.value = String(state.mesh3dBoost);
  if (output) output.textContent = `${Math.round(state.mesh3dBoost)}x`;
  if (intensitySlider) intensitySlider.value = String(state.networkIntensity);
  if (intensityOutput) {
    intensityOutput.textContent = `${Math.round(state.networkIntensity)}%`;
  }
}

function wirePanelCollapse() {
  const panel = document.getElementById("routing-panel");
  const button = document.getElementById("panel-collapse-button");
  const content = document.getElementById("panel-content");
  if (!panel || !button || !content) return;

  button.addEventListener("click", () => {
    setPanelCollapsed(!state.panelCollapsed);
  });

  setPanelCollapsed(state.panelCollapsed);
}

function setPanelCollapsed(collapsed) {
  const panel = document.getElementById("routing-panel");
  const button = document.getElementById("panel-collapse-button");
  const content = document.getElementById("panel-content");
  if (!panel || !button || !content) return;

  state.panelCollapsed = collapsed;
  panel.classList.toggle("is-collapsed", collapsed);
  button.setAttribute("aria-expanded", String(!collapsed));
  button.setAttribute(
    "aria-label",
    collapsed ? "Expand routing panel" : "Collapse routing panel",
  );
  button.title = collapsed ? "Expand panel" : "Collapse panel";
  content.setAttribute("aria-hidden", String(collapsed));

  if (collapsed) {
    panel.scrollTop = 0;
  }
}

function wireInfoModal() {
  const modal = document.getElementById("info-modal");
  const panel = modal?.querySelector(".info-modal__panel");
  const openButton = document.getElementById("info-button");
  if (!modal || !panel || !openButton) return;

  openButton.addEventListener("click", () => openInfoModal(openButton));
  modal.querySelectorAll("[data-info-close]").forEach((element) => {
    element.addEventListener("click", closeInfoModal);
  });

  document.addEventListener("keydown", (event) => {
    if (modal.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeInfoModal();
      return;
    }
    if (event.key === "Tab") {
      trapInfoModalFocus(event, modal);
    }
  });
}

function openInfoModal(returnFocusElement) {
  const modal = document.getElementById("info-modal");
  const panel = modal?.querySelector(".info-modal__panel");
  if (!modal || !panel) return;

  state.infoModalReturnFocus = returnFocusElement || document.activeElement;
  modal.hidden = false;
  document.body.classList.add("has-info-modal");
  modal.scrollTop = 0;
  panel.scrollTop = 0;
  modal.querySelector(".info-modal__content")?.scrollTo({ top: 0 });
  panel.focus({ preventScroll: true });
}

function closeInfoModal() {
  const modal = document.getElementById("info-modal");
  if (!modal || modal.hidden) return;

  modal.hidden = true;
  document.body.classList.remove("has-info-modal");
  if (state.infoModalReturnFocus?.focus) {
    state.infoModalReturnFocus.focus({ preventScroll: true });
  }
  state.infoModalReturnFocus = null;
}

function trapInfoModalFocus(event, modal) {
  const focusable = Array.from(
    modal.querySelectorAll(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  );
  if (!focusable.length) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function setLayerVisibility(layerId, visible) {
  if (!state.map.getLayer(layerId)) return;
  state.map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
}

function setMesh3dBoost(value) {
  const previousBoost = state.mesh3dBoost;
  state.mesh3dBoost = Math.max(0, Math.min(1000, value));
  syncMesh3dControls();
  updateNetworkLayerStyle();

  if (previousBoost <= 0 && state.mesh3dBoost > 0) {
    state.map.easeTo({
      pitch: MESH_3D_VIEW.pitch,
      bearing: MESH_3D_VIEW.bearing,
      duration: 850,
    });
  } else if (previousBoost > 0 && state.mesh3dBoost <= 0) {
    hideSlopeHover();
    state.map.easeTo({
      pitch: 0,
      bearing: 0,
      duration: 650,
    });
  }

  setStatus(
    state.mesh3dBoost > 0
      ? `Slope network height boost ${Math.round(state.mesh3dBoost)}x`
      : "Flat slope network",
  );
}

function setNetworkIntensity(value) {
  state.networkIntensity = Math.max(0, Math.min(100, value));
  syncMesh3dControls();
  updateNetworkLayerStyle();
}

function updateNetworkLayerStyle() {
  if (!state.map) return;

  const use3d = state.mesh3dBoost > 0 && deck3dAvailable();
  setNativeNetworkVisibility(!use3d);
  updateNativeNetworkOpacity();
  updateDeck3dOverlay(use3d);
  syncRendererStateAttributes(use3d);

  if (state.mesh3dBoost > 0 && !deck3dAvailable()) {
    setStatus("3D network needs deck.gl to finish loading");
  }
}

function syncRendererStateAttributes(use3d) {
  const root = document.documentElement;
  root.dataset.networkRenderer = use3d ? "deck-3d" : "maplibre-2d";
  root.dataset.deckAvailable = String(deck3dAvailable());
  root.dataset.deckOverlayActive = String(use3d);
  root.dataset.deckPathCount = String(state.deck3dData?.length || 0);
  root.dataset.heightBoost = String(state.mesh3dBoost);
  root.dataset.networkOpacity = String(networkIntensityRatio());
}

function setNativeNetworkVisibility(visible) {
  for (const layerId of NETWORK_LINE_LAYERS) {
    setLayerVisibility(layerId, visible);
  }
}

function updateNativeNetworkOpacity() {
  const ratio = networkIntensityRatio();
  const opacities = {
    "routing-network-slope-glow": ratio * 0.52,
    "routing-network-slope-core": ratio,
  };

  for (const [layerId, opacity] of Object.entries(opacities)) {
    if (state.map.getLayer(layerId)) {
      state.map.setPaintProperty(layerId, "line-opacity", opacity);
    }
  }
}

function deck3dAvailable() {
  return Boolean(window.deck?.MapboxOverlay && window.deck?.PathLayer);
}

function updateDeck3dOverlay(visible) {
  if (!state.deckOverlay && !visible) return;
  if (!deck3dAvailable()) return;

  const overlay = ensureDeck3dOverlay();
  overlay.setProps({
    layers: visible ? [createDeck3dLayer()] : [],
  });
}

function ensureDeck3dOverlay() {
  if (state.deckOverlay) return state.deckOverlay;

  state.deckOverlay = new deck.MapboxOverlay({
    interleaved: true,
    layers: [],
  });
  state.map.addControl(state.deckOverlay);
  return state.deckOverlay;
}

function createDeck3dLayer() {
  const alpha = Math.round(networkIntensityRatio() * 255);

  return new deck.PathLayer({
    id: DECK_3D_LAYER_ID,
    data: getDeck3dData(),
    beforeId: DECK_3D_BEFORE_LAYER_ID,
    getPath: (segment) => segment.path,
    getColor: (segment) => [...segment.color, alpha],
    getWidth: DECK_3D_LINE_WIDTH_PIXELS,
    widthUnits: "pixels",
    widthMinPixels: 0.7,
    widthMaxPixels: 3.2,
    capRounded: true,
    jointRounded: true,
    billboard: true,
    opacity: 1,
    pickable: false,
    _pathType: "open",
    modelMatrix: deck3dModelMatrix(),
    parameters: {
      depthTest: true,
      depthMask: true,
    },
    updateTriggers: {
      getColor: [alpha],
    },
  });
}

function deck3dModelMatrix() {
  const zScale = state.mesh3dBoost * MESH_3D_ALTITUDE_MULTIPLIER;
  return [
    1, 0, 0, 0,
    0, 1, 0, 0,
    0, 0, zScale, 0,
    0, 0, 0, 1,
  ];
}

function getDeck3dData() {
  if (!state.deck3dData) {
    state.deck3dData = buildDeck3dData(state.data);
  }
  return state.deck3dData;
}

function buildDeck3dData(data) {
  const stats = getElevationStats(data);
  const paths = [];

  for (const segment of data.segments) {
    const coordinates = segment.g;
    if (!coordinates || coordinates.length < 2) continue;

    paths.push({
      path: buildDeck3dPath(segment, stats),
      color: slopeColorArray(mesh3dSegmentSteepness(segment)),
    });
  }

  return paths;
}

function buildDeck3dPath(segment, stats) {
  const coordinates = segment.g;
  const values = new Float64Array(coordinates.length * 3);
  const nodeA = state.data.nodes[segment.a];
  const nodeB = state.data.nodes[segment.b];
  const startZ = Number.isFinite(nodeA?.[2]) ? nodeA[2] : 0;
  const endZ = Number.isFinite(nodeB?.[2]) ? nodeB[2] : startZ + (segment.dz || 0);
  const totalLength = Math.max(segment.l || 0, 1);
  let runningLength = 0;

  for (let i = 0; i < coordinates.length; i += 1) {
    if (i > 0) {
      runningLength += approximateLngLatDistance(coordinates[i - 1], coordinates[i]);
    }

    const ratio = Math.max(0, Math.min(1, runningLength / totalLength));
    const currentZ = startZ + (endZ - startZ) * ratio;
    const offset = i * 3;

    values[offset] = coordinates[i][0];
    values[offset + 1] = coordinates[i][1];
    values[offset + 2] = Math.max(0, currentZ - stats.min);
  }

  return values;
}

function approximateLngLatDistance(a, b) {
  const lat = ((a[1] + b[1]) / 2) * (Math.PI / 180);
  const metersPerDegreeLat = 111320;
  const metersPerDegreeLng = metersPerDegreeLat * Math.cos(lat);
  return Math.hypot(
    (b[0] - a[0]) * metersPerDegreeLng,
    (b[1] - a[1]) * metersPerDegreeLat,
  );
}

function mesh3dSegmentSteepness(segment) {
  if (Number.isFinite(segment.st)) return Math.max(0, segment.st);
  if (Number.isFinite(segment.gr)) return Math.abs(segment.gr);
  return 0;
}

function slopeColorArray(steepness) {
  const cacheKey = Math.round(Math.max(0, steepness) * 10) / 10;
  const cached = state.slopeColorCache.get(cacheKey);
  if (cached) return cached;

  const value = Math.max(0, Math.min(25, cacheKey));
  let lower = SLOPE_COLOR_STOPS[0];
  let upper = SLOPE_COLOR_STOPS[SLOPE_COLOR_STOPS.length - 1];

  for (let i = 1; i < SLOPE_COLOR_STOPS.length; i += 1) {
    if (value <= SLOPE_COLOR_STOPS[i][0]) {
      lower = SLOPE_COLOR_STOPS[i - 1];
      upper = SLOPE_COLOR_STOPS[i];
      break;
    }
  }

  const span = Math.max(0.000001, upper[0] - lower[0]);
  const t = Math.max(0, Math.min(1, (value - lower[0]) / span));
  const start = hexToRgb(lower[1]);
  const end = hexToRgb(upper[1]);
  const color = [
    Math.round(start[0] + (end[0] - start[0]) * t),
    Math.round(start[1] + (end[1] - start[1]) * t),
    Math.round(start[2] + (end[2] - start[2]) * t),
  ];

  state.slopeColorCache.set(cacheKey, color);
  return color;
}

function hexToRgb(hex) {
  const value = hex.replace("#", "");
  return [
    Number.parseInt(value.slice(0, 2), 16),
    Number.parseInt(value.slice(2, 4), 16),
    Number.parseInt(value.slice(4, 6), 16),
  ];
}

function setRouteVisibility(key, visible) {
  state.routeVisibility[key] = visible;
  const scenario = SCENARIOS.find((item) => item.key === key);
  if (!scenario) return;
  setLayerVisibility(`${scenario.source}-halo`, visible);
  setLayerVisibility(scenario.source, visible);
}

function wireSlopeHover() {
  state.slopePopup = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    className: "segment-hover-popup",
    anchor: "bottom",
    offset: [0, -10],
    maxWidth: "220px",
    focusAfterOpen: false,
  });

  state.map.on("mousemove", handleSlopeMouseMove);
  state.map.on("movestart", hideSlopeHover);
  state.map.getCanvas().addEventListener("mouseleave", hideSlopeHover);
}

function handleSlopeMouseMove(event) {
  if (state.mesh3dBoost > 0) return;

  const segment = findNearestSlopeSegment(event);
  if (!segment) {
    hideSlopeHover();
    return;
  }

  state.map.getCanvas().style.cursor = "crosshair";
  if (state.activeSlopeSegmentId !== segment.id) {
    state.slopePopup.setDOMContent(createSlopePopupContent(segment));
    state.activeSlopeSegmentId = segment.id;
  }

  state.slopePopup.setLngLat(event.lngLat);
  if (!state.slopePopup.isOpen()) {
    state.slopePopup.addTo(state.map);
  }
}

function hideSlopeHover() {
  state.activeSlopeSegmentId = null;
  if (state.map) {
    state.map.getCanvas().style.cursor = "";
  }
  if (state.slopePopup?.isOpen()) {
    state.slopePopup.remove();
  }
}

function ensureSlopeHoverIndex() {
  if (!state.slopeHoverIndex) {
    state.slopeHoverIndex = buildSegmentHoverIndex();
  }
  return state.slopeHoverIndex;
}

function buildSegmentHoverIndex() {
  const cells = new Map();
  const cellSize = SLOPE_HOVER_INDEX_CELL_SIZE;

  for (let i = 0; i < state.data.segments.length; i += 1) {
    const coordinates = state.data.segments[i].g;
    if (!coordinates || coordinates.length < 2) continue;

    let minLng = Infinity;
    let minLat = Infinity;
    let maxLng = -Infinity;
    let maxLat = -Infinity;

    for (const coordinate of coordinates) {
      minLng = Math.min(minLng, coordinate[0]);
      minLat = Math.min(minLat, coordinate[1]);
      maxLng = Math.max(maxLng, coordinate[0]);
      maxLat = Math.max(maxLat, coordinate[1]);
    }

    const minCellX = Math.floor(minLng / cellSize);
    const maxCellX = Math.floor(maxLng / cellSize);
    const minCellY = Math.floor(minLat / cellSize);
    const maxCellY = Math.floor(maxLat / cellSize);

    for (let x = minCellX; x <= maxCellX; x += 1) {
      for (let y = minCellY; y <= maxCellY; y += 1) {
        const key = `${x}:${y}`;
        const bucket = cells.get(key);
        if (bucket) {
          bucket.push(i);
        } else {
          cells.set(key, [i]);
        }
      }
    }
  }

  return { cellSize, cells };
}

function findNearestSlopeSegment(event) {
  const index = ensureSlopeHoverIndex();
  let candidateIndexes = getSlopeHoverCandidates(index, event.lngLat, 1);
  if (candidateIndexes.length === 0) {
    candidateIndexes = getSlopeHoverCandidates(index, event.lngLat, 2);
  }

  let bestSegment = null;
  let bestDistance = Infinity;

  for (const segmentIndex of candidateIndexes) {
    const segment = state.data.segments[segmentIndex];
    const distance = distanceToPolylinePixels(event.point, segment.g);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestSegment = segment;
    }
  }

  if (bestDistance > SLOPE_HOVER_PIXEL_TOLERANCE) return null;
  return bestSegment;
}

function getSlopeHoverCandidates(index, lngLat, searchRadius) {
  const cellX = Math.floor(lngLat.lng / index.cellSize);
  const cellY = Math.floor(lngLat.lat / index.cellSize);
  const seen = new Set();
  const candidates = [];

  for (let x = cellX - searchRadius; x <= cellX + searchRadius; x += 1) {
    for (let y = cellY - searchRadius; y <= cellY + searchRadius; y += 1) {
      const bucket = index.cells.get(`${x}:${y}`);
      if (!bucket) continue;
      for (const segmentIndex of bucket) {
        if (seen.has(segmentIndex)) continue;
        seen.add(segmentIndex);
        candidates.push(segmentIndex);
      }
    }
  }

  return candidates;
}

function distanceToPolylinePixels(point, coordinates) {
  let bestDistance = Infinity;

  for (let i = 1; i < coordinates.length; i += 1) {
    const start = state.map.project(coordinates[i - 1]);
    const end = state.map.project(coordinates[i]);
    bestDistance = Math.min(
      bestDistance,
      distanceToSegmentPixels(point, start, end),
    );
  }

  return bestDistance;
}

function distanceToSegmentPixels(point, start, end) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;

  if (lengthSquared === 0) {
    return Math.hypot(point.x - start.x, point.y - start.y);
  }

  const ratio = Math.max(
    0,
    Math.min(
      1,
      ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared,
    ),
  );
  const closestX = start.x + ratio * dx;
  const closestY = start.y + ratio * dy;
  return Math.hypot(point.x - closestX, point.y - closestY);
}

function createSlopePopupContent(segment) {
  const root = document.createElement("div");
  root.className = "slope-popup";

  const title = document.createElement("div");
  title.className = "slope-popup__title";
  title.textContent = "Street segment";

  const grid = document.createElement("div");
  grid.className = "slope-popup__grid";
  appendSlopePopupRow(grid, "Avg grade", formatGrade(segment.gr, true));
  appendSlopePopupRow(grid, "Max slope", formatGrade(segment.st));
  appendSlopePopupRow(grid, "Elev. change", formatPopupMeters(segment.dz, true));
  appendSlopePopupRow(grid, "Length", formatPopupMeters(segment.l));

  root.append(title, grid);
  return root;
}

function appendSlopePopupRow(grid, label, value) {
  const row = document.createElement("div");
  row.className = "slope-popup__row";

  const labelEl = document.createElement("span");
  labelEl.className = "slope-popup__label";
  labelEl.textContent = label;

  const valueEl = document.createElement("span");
  valueEl.className = "slope-popup__value";
  valueEl.textContent = value;

  row.append(labelEl, valueEl);
  grid.appendChild(row);
}

function formatGrade(value, signed = false) {
  if (!Number.isFinite(value)) return "--";
  const sign = signed && value > 0 ? "+" : "";
  const angle = slopeAngleDegrees(value);
  return `${sign}${value.toFixed(1)}% (${angle.toFixed(1)} deg)`;
}

function slopeAngleDegrees(gradePct) {
  return (Math.atan(Math.abs(gradePct) / 100) * 180) / Math.PI;
}

function formatPopupMeters(value, signed = false) {
  if (!Number.isFinite(value)) return "--";
  const sign = signed && value > 0 ? "+" : "";
  const digits = Math.abs(value) < 10 ? 1 : 0;
  return `${sign}${value.toFixed(digits)} m`;
}

function nodeLngLat(nodeId) {
  const node = state.data.nodes[nodeId];
  return [node[0], node[1]];
}

function snapMarkerToNode(marker) {
  const nearest = findNearestNode(marker.getLngLat().toArray());
  marker.setLngLat(nodeLngLat(nearest));
  return nearest;
}

function findNearestNode(lngLat) {
  const [lng, lat] = lngLat;
  const latScale = Math.cos((lat * Math.PI) / 180);
  let bestNode = 0;
  let bestScore = Infinity;

  for (let i = 0; i < state.data.nodes.length; i += 1) {
    const node = state.data.nodes[i];
    const dx = (node[0] - lng) * latScale;
    const dy = node[1] - lat;
    const score = dx * dx + dy * dy;
    if (score < bestScore) {
      bestScore = score;
      bestNode = i;
    }
  }

  return bestNode;
}

async function routeAll(options = {}) {
  if (!state.adjacency || state.originNode == null || state.destNode == null) {
    return;
  }

  const requestId = (state.routeRequest += 1);
  setStatus("Routing");

  await new Promise((resolve) => requestAnimationFrame(resolve));

  const start = performance.now();
  for (const scenario of SCENARIOS) {
    const route = shortestPath(state.originNode, state.destNode, scenario.key);
    if (requestId !== state.routeRequest) return;
    renderRoute(scenario, route);
  }

  if (options.fit) {
    fitRouteView();
  }

  setStatus(`Routes updated in ${Math.round(performance.now() - start)} ms`);
}

function shortestPath(startNode, endNode, profile) {
  const nodeCount = state.data.nodes.length;
  const dist = new Float64Array(nodeCount);
  const previousNode = new Int32Array(nodeCount);
  const previousSegment = new Int32Array(nodeCount);
  const previousReverse = new Int8Array(nodeCount);

  dist.fill(Infinity);
  previousNode.fill(-1);
  previousSegment.fill(-1);
  previousReverse.fill(0);

  const heap = new MinHeap();
  dist[startNode] = 0;
  heap.push(startNode, 0);

  while (heap.size > 0) {
    const current = heap.pop();
    if (current.cost !== dist[current.node]) continue;
    if (current.node === endNode) break;

    const edges = state.adjacency[current.node];
    for (const edge of edges) {
      const edgeCost = edge[profile];
      if (!Number.isFinite(edgeCost)) continue;
      const nextCost = current.cost + edgeCost;
      if (nextCost < dist[edge.to]) {
        dist[edge.to] = nextCost;
        previousNode[edge.to] = current.node;
        previousSegment[edge.to] = edge.segmentIndex;
        previousReverse[edge.to] = edge.reverse ? 1 : 0;
        heap.push(edge.to, nextCost);
      }
    }
  }

  if (!Number.isFinite(dist[endNode])) {
    return null;
  }

  const steps = [];
  let cursor = endNode;
  while (cursor !== startNode) {
    const segmentIndex = previousSegment[cursor];
    if (segmentIndex < 0) return null;
    steps.push({
      segmentIndex,
      reverse: previousReverse[cursor] === 1,
    });
    cursor = previousNode[cursor];
  }
  steps.reverse();

  return summarizeRoute(steps, dist[endNode]);
}

function summarizeRoute(steps, cost) {
  let length = 0;
  let gain = 0;
  let loss = 0;
  let maxSteep = 0;
  const coordinates = [];

  for (const step of steps) {
    const segment = state.data.segments[step.segmentIndex];
    length += segment.l ?? 0;
    const dz = step.reverse ? -(segment.dz ?? 0) : segment.dz ?? 0;
    gain += Math.max(0, dz);
    loss += Math.max(0, -dz);
    maxSteep = Math.max(maxSteep, segment.st ?? 0);
    appendRouteCoordinates(
      coordinates,
      step.reverse ? [...segment.g].reverse() : segment.g,
    );
  }

  return {
    cost,
    length,
    gain,
    loss,
    maxSteep,
    feature: {
      type: "Feature",
      properties: {},
      geometry: {
        type: "LineString",
        coordinates,
      },
    },
  };
}

function appendRouteCoordinates(target, nextLine) {
  if (nextLine.length === 0) return;
  if (target.length === 0) {
    target.push(...nextLine);
    return;
  }

  const last = target[target.length - 1];
  if (sameCoordinate(last, nextLine[0])) {
    target.push(...nextLine.slice(1));
    return;
  }

  if (sameCoordinate(last, nextLine[nextLine.length - 1])) {
    target.push(...[...nextLine].reverse().slice(1));
    return;
  }

  target.push(...nextLine);
}

function sameCoordinate(a, b) {
  return Math.abs(a[0] - b[0]) < 0.000001 && Math.abs(a[1] - b[1]) < 0.000001;
}

function renderRoute(scenario, route) {
  const source = state.map.getSource(scenario.source);
  if (!route) {
    source.setData(emptyFeatureCollection());
    document.getElementById(scenario.summaryId).textContent = "No connected route";
    document.getElementById(scenario.lengthId).textContent = "--";
    return;
  }

  source.setData({
    type: "FeatureCollection",
    features: [route.feature],
  });

  document.getElementById(scenario.summaryId).textContent =
    `Gain ${formatSignedMeters(route.gain)} / loss ${formatMeters(route.loss)} / max ${Math.round(route.maxSteep)}%`;
  document.getElementById(scenario.lengthId).textContent = formatMeters(route.length);
}

class MinHeap {
  constructor() {
    this.items = [];
  }

  get size() {
    return this.items.length;
  }

  push(node, cost) {
    const item = { node, cost };
    this.items.push(item);
    this.bubbleUp(this.items.length - 1);
  }

  pop() {
    const root = this.items[0];
    const tail = this.items.pop();
    if (this.items.length > 0) {
      this.items[0] = tail;
      this.sinkDown(0);
    }
    return root;
  }

  bubbleUp(index) {
    const item = this.items[index];
    while (index > 0) {
      const parentIndex = Math.floor((index - 1) / 2);
      const parent = this.items[parentIndex];
      if (item.cost >= parent.cost) break;
      this.items[parentIndex] = item;
      this.items[index] = parent;
      index = parentIndex;
    }
  }

  sinkDown(index) {
    const length = this.items.length;
    const item = this.items[index];

    while (true) {
      const leftIndex = index * 2 + 1;
      const rightIndex = leftIndex + 1;
      let swapIndex = null;

      if (leftIndex < length) {
        const left = this.items[leftIndex];
        if (left.cost < item.cost) swapIndex = leftIndex;
      }

      if (rightIndex < length) {
        const right = this.items[rightIndex];
        const comparisonCost =
          swapIndex === null ? item.cost : this.items[swapIndex].cost;
        if (right.cost < comparisonCost) swapIndex = rightIndex;
      }

      if (swapIndex === null) break;
      this.items[index] = this.items[swapIndex];
      this.items[swapIndex] = item;
      index = swapIndex;
    }
  }
}

syncScenarioColors();
wirePanelCollapse();
wireInfoModal();
state.map = createMap();
