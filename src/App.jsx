import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Map,
  RefreshCw,
  Server,
  X
} from "lucide-react";
import { api } from "./api";

function formatDate(value) {
  return new Date(value).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short"
  });
}

function Stats({ incidents }) {
  const high = incidents.filter(
    (item) => item.severity === "high"
  ).length;

  const medium = incidents.filter(
    (item) => item.severity === "medium"
  ).length;

  const districts = new Set(
    incidents.map((item) => item.district_name)
  ).size;

  return (
    <section className="stats">
      <div className="stat">
        <span>Active incidents</span>
        <strong>{incidents.length}</strong>
      </div>

      <div className="stat danger">
        <span>High severity</span>
        <strong>{high}</strong>
      </div>

      <div className="stat warning">
        <span>Medium severity</span>
        <strong>{medium}</strong>
      </div>

      <div className="stat">
        <span>Affected districts</span>
        <strong>{districts}</strong>
      </div>
    </section>
  );
}

function IncidentTable({ incidents, onSelect }) {
  if (!incidents.length) {
    return <div className="empty">No incidents found.</div>;
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Incident</th>
            <th>District</th>
            <th>Severity</th>
            <th>Triggered</th>
          </tr>
        </thead>

        <tbody>
          {incidents.map((incident) => (
            <tr
              key={incident.id}
              onClick={() => onSelect(incident)}
            >
              <td>
                <strong>
                  {incident.type.replaceAll("_", " ")}
                </strong>
                <small>
                  {incident.description || "No description"}
                </small>
              </td>

              <td>{incident.district_name || "Unknown"}</td>

              <td>
                <span className={`badge ${incident.severity}`}>
                  {incident.severity}
                </span>
              </td>

              <td>{formatDate(incident.triggered_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IncidentMap({ incidents, onSelect }) {
  return (
    <div className="map">
      <span className="map-caption">
        Aktau operational map
      </span>

      {incidents.map((incident, index) => (
        <button
          key={incident.id}
          className={`marker ${incident.severity}`}
          style={{
            left: `${12 + ((index * 23) % 78)}%`,
            top: `${18 + ((index * 29) % 65)}%`
          }}
          title={incident.type}
          onClick={() => onSelect(incident)}
        />
      ))}

      {!incidents.length && (
        <div className="empty">No incidents available.</div>
      )}
    </div>
  );
}

function GraphView({ graph }) {
  const nodes = graph?.nodes || [];

  return (
    <div className="graph">
      <div className="graph-meta">
        <span>{nodes.length} nodes</span>
        <span>{graph?.edges?.length || 0} relationships</span>
      </div>

      <div className="graph-canvas">
        {nodes.map((node, index) => (
          <div
            key={node.id}
            className={`graph-node ${node.severity}`}
            style={{
              left: `${50 + Math.cos(index) * 32}%`,
              top: `${50 + Math.sin(index) * 32}%`
            }}
            title={`${node.incident_type} - ${node.district_name}`}
          >
            {node.id}
          </div>
        ))}

        {!nodes.length && (
          <div className="empty">No graph data.</div>
        )}
      </div>
    </div>
  );
}

function IncidentDrawer({ incident, onClose }) {
  if (!incident) return null;

  return (
    <div className="drawer-layer" onClick={onClose}>
      <aside
        className="drawer"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="close" onClick={onClose}>
          <X size={20} />
        </button>

        <span className="eyebrow">INCIDENT #{incident.id}</span>

        <h2>{incident.type.replaceAll("_", " ")}</h2>

        <span className={`badge ${incident.severity}`}>
          {incident.severity}
        </span>

        <dl>
          <dt>District</dt>
          <dd>{incident.district_name || "Unknown"}</dd>

          <dt>Triggered</dt>
          <dd>{formatDate(incident.triggered_at)}</dd>

          <dt>Description</dt>
          <dd>{incident.description || "No description"}</dd>

          <dt>Coordinates</dt>
          <dd>
            {incident.lat}, {incident.lng}
          </dd>
        </dl>
      </aside>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("overview");
  const [incidents, setIncidents] = useState([]);
  const [graph, setGraph] = useState({});
  const [selected, setSelected] = useState(null);
  const [online, setOnline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [filters, setFilters] = useState({
    district: "",
    severity: "",
    type: ""
  });

  const districts = useMemo(
    () =>
      [...new Set(
        incidents
          .map((item) => item.district_name)
          .filter(Boolean)
      )],
    [incidents]
  );

  async function loadData() {
    try {
      setLoading(true);
      setError("");

      const [incidentData, graphData, health] =
        await Promise.all([
          api.incidents(filters),
          api.graph(),
          api.health()
        ]);

      setIncidents(incidentData);
      setGraph(graphData);
      setOnline(health.status === "healthy");
    } catch (requestError) {
      setError(requestError.message);
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [
    filters.district,
    filters.severity,
    filters.type
  ]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">AI</div>

          <div>
            <strong>Aktau Intelligence</strong>
            <small>Incident command center</small>
          </div>
        </div>

        <nav>
          <button
            className={page === "overview" ? "active" : ""}
            onClick={() => setPage("overview")}
          >
            <Activity size={17} />
            Overview
          </button>

          <button
            className={page === "map" ? "active" : ""}
            onClick={() => setPage("map")}
          >
            <Map size={17} />
            Incident map
          </button>

          <button
            className={page === "graph" ? "active" : ""}
            onClick={() => setPage("graph")}
          >
            <BarChart3 size={17} />
            Correlation graph
          </button>
        </nav>

        <div className="connection">
          <Server size={15} />
          <span className={online ? "online" : "offline"}>
            {online
              ? "Backend connected"
              : "Backend unavailable"}
          </span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <span className="eyebrow">
              CITY OPERATIONS / AKTAU
            </span>

            <h1>
              {page === "overview" && "Incident overview"}
              {page === "map" && "Live incident map"}
              {page === "graph" &&
                "Incident correlation graph"}
            </h1>
          </div>

          <button className="refresh" onClick={loadData}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </header>

        {error && <div className="error">{error}</div>}

        {loading ? (
          <div className="loading">
            Loading live backend data...
          </div>
        ) : (
          <>
            {page === "overview" && (
              <>
                <Stats incidents={incidents} />

                <section className="panel">
                  <div className="panel-header">
                    <div>
                      <span className="eyebrow">
                        REAL-TIME FEED
                      </span>
                      <h2>Latest incidents</h2>
                    </div>

                    <button
                      className="secondary"
                      onClick={() => setPage("map")}
                    >
                      Open map
                    </button>
                  </div>

                  <IncidentTable
                    incidents={incidents.slice(0, 10)}
                    onSelect={setSelected}
                  />
                </section>
              </>
            )}

            {page === "map" && (
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <span className="eyebrow">
                      GEOSPATIAL MONITORING
                    </span>
                    <h2>Incident map</h2>
                  </div>
                </div>

                <div className="filters">
                  <select
                    value={filters.district}
                    onChange={(event) =>
                      setFilters({
                        ...filters,
                        district: event.target.value
                      })
                    }
                  >
                    <option value="">All districts</option>

                    {districts.map((district) => (
                      <option key={district}>
                        {district}
                      </option>
                    ))}
                  </select>

                  <select
                    value={filters.severity}
                    onChange={(event) =>
                      setFilters({
                        ...filters,
                        severity: event.target.value
                      })
                    }
                  >
                    <option value="">All severity</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>

                  <input
                    placeholder="Incident type"
                    value={filters.type}
                    onChange={(event) =>
                      setFilters({
                        ...filters,
                        type: event.target.value
                      })
                    }
                  />
                </div>

                <IncidentMap
                  incidents={incidents}
                  onSelect={setSelected}
                />
              </section>
            )}

            {page === "graph" && (
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <span className="eyebrow">
                      RELATIONSHIP ANALYSIS
                    </span>
                    <h2>Correlation graph</h2>
                  </div>
                </div>

                <GraphView graph={graph} />
              </section>
            )}
          </>
        )}
      </main>

      <IncidentDrawer
        incident={selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
