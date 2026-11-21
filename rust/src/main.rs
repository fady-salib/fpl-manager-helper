mod connection;
mod data;
mod model;
mod optimize;
mod team_search;

use crate::{data::DataSet, model::Model};
use axum::{
    Json, Router,
    extract::{Path as Param, Query, State},
    http::{HeaderMap, StatusCode, header},
    response::{Html, IntoResponse, Response},
    routing::{get, post},
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    path::PathBuf,
    sync::{
        Arc, Mutex, RwLock,
        atomic::{AtomicU64, Ordering},
    },
    time::{Duration, Instant},
};
use tokio::io::AsyncBufReadExt;
use tower_http::compression::CompressionLayer;

#[derive(Clone)]
struct App {
    root: Arc<PathBuf>,
    data: Arc<RwLock<Option<Arc<DataSet>>>>,
    payload: Arc<RwLock<String>>,
    model: Arc<RwLock<Option<Arc<Model>>>>,
    jobs: Arc<Mutex<BTreeMap<u64, Job>>>,
    counter: Arc<AtomicU64>,
    client: reqwest::Client,
    port: u16,
    pairing: Arc<Mutex<Option<connection::Pairing>>>,
    league_cache: Arc<Mutex<BTreeMap<String, (Instant, Value)>>>,
}
#[derive(Clone, Serialize)]
struct Job {
    id: u64,
    kind: String,
    status: String,
    progress: u64,
    logs: Vec<String>,
    result: Option<Value>,
    error: Option<String>,
    elapsed_ms: f64,
}
type ApiResult = Result<Json<Value>, (StatusCode, Json<Value>)>;
fn fail(status: StatusCode, message: impl ToString) -> (StatusCode, Json<Value>) {
    (status, Json(json!({"error":message.to_string()})))
}
impl App {
    fn dataset(&self) -> Result<Arc<DataSet>, String> {
        self.data.read().unwrap().clone().ok_or(
            "No public data yet. Choose Refresh data to download official FPL metadata.".into(),
        )
    }
    fn rebuild(&self) -> Result<(), String> {
        let model = self.model.read().unwrap().clone();
        let data = Arc::new(DataSet::load(
            &self.root,
            model.as_deref(),
            Utc::now().timestamp(),
        )?);
        let payload = data.response().to_string();
        *self.data.write().unwrap() = Some(data);
        *self.payload.write().unwrap() = payload;
        Ok(())
    }
    fn reload_model(&self) -> Result<(), String> {
        let model = Model::load(&self.root.join("models/native-model.json"))?;
        *self.model.write().unwrap() = Some(Arc::new(model));
        self.rebuild()
    }
    fn new_job(&self, kind: &str) -> Result<u64, String> {
        let mut jobs = self.jobs.lock().unwrap();
        if jobs.values().filter(|j| j.status == "running").count() >= 2 {
            return Err("Two tasks are already running. Wait for one to finish.".into());
        }
        if jobs
            .values()
            .any(|j| j.status == "running" && j.kind == kind)
        {
            return Err("That task is already running".into());
        }
        let id = self.counter.fetch_add(1, Ordering::Relaxed);
        jobs.insert(
            id,
            Job {
                id,
                kind: kind.into(),
                status: "running".into(),
                progress: 0,
                logs: vec![format!("Starting {kind}…")],
                result: None,
                error: None,
                elapsed_ms: 0.,
            },
        );
        while jobs.len() > 30 {
            let oldest = *jobs.keys().next().unwrap();
            if jobs[&oldest].status == "running" {
                break;
            }
            jobs.remove(&oldest);
        }
        Ok(id)
    }
    fn log(&self, id: u64, line: impl ToString, progress: u64) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(&id) {
            j.logs.push(line.to_string());
            if j.logs.len() > 300 {
                j.logs.remove(0);
            }
            j.progress = progress.min(99);
        }
    }
    fn finish(&self, id: u64, result: Result<Value, String>, elapsed: f64) {
        if let Some(j) = self.jobs.lock().unwrap().get_mut(&id) {
            j.elapsed_ms = elapsed;
            j.progress = 100;
            match result {
                Ok(v) => {
                    j.status = "done".into();
                    j.result = Some(v);
                }
                Err(e) => {
                    j.status = "failed".into();
                    j.error = Some(e);
                }
            }
        }
    }
    async fn fetch(&self, endpoint: &str) -> Result<Value, String> {
        let url = format!("https://fantasy.premierleague.com/api/{endpoint}");
        for attempt in 0..3 {
            match self.client.get(&url).send().await {
                Ok(r) => {
                    let status = r.status();
                    if status.is_success() {
                        return r
                            .json()
                            .await
                            .map_err(|e| format!("Invalid public API response: {e}"));
                    }
                    if (status.as_u16() == 429 || status.is_server_error()) && attempt < 2 {
                        let wait = r
                            .headers()
                            .get("Retry-After")
                            .and_then(|h| h.to_str().ok())
                            .and_then(|s| s.parse::<u64>().ok())
                            .unwrap_or(1 << attempt);
                        if wait > 60 {
                            return Err("FPL requested a long cooldown. Retry later; cached data is still available.".into());
                        }
                        tokio::time::sleep(Duration::from_secs(wait.max(1))).await;
                        continue;
                    }
                    return Err(format!("FPL API returned HTTP {status}"));
                }
                Err(e) => {
                    if attempt == 2 {
                        return Err(format!("Cannot reach official FPL API: {e}"));
                    }
                }
            }
            tokio::time::sleep(Duration::from_secs(1 << attempt)).await;
        }
        Err("Public API retries exhausted".into())
    }
    fn store(&self, endpoint: &str, value: &Value) -> Result<(), String> {
        std::fs::create_dir_all(self.root.join("data")).map_err(|e| e.to_string())?;
        let con = rusqlite::Connection::open(self.root.join("data/fpl.sqlite"))
            .map_err(|e| e.to_string())?;
        con.busy_timeout(Duration::from_secs(5))
            .map_err(|e| e.to_string())?;
        con.execute_batch("CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,endpoint TEXT NOT NULL,fetched_at TEXT NOT NULL,sha256 TEXT NOT NULL,payload TEXT NOT NULL); CREATE INDEX IF NOT EXISTS endpoint_time ON snapshots(endpoint,fetched_at);").map_err(|e|e.to_string())?;
        // Keep the append-only format used by the existing Python application.
        let body = value.to_string();
        con.execute(
            "INSERT INTO snapshots(endpoint,fetched_at,sha256,payload) VALUES(?1,?2,?3,?4)",
            rusqlite::params![
                endpoint,
                Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros, false),
                format!("{:x}", Sha256::digest(body.as_bytes())),
                body
            ],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }
}
fn origin(app: &App, headers: &HeaderMap) -> Result<(), (StatusCode, Json<Value>)> {
    if let Some(value) = headers.get(header::ORIGIN) {
        let value = value.to_str().unwrap_or("");
        if value != format!("http://127.0.0.1:{}", app.port)
            && value != format!("http://localhost:{}", app.port)
        {
            return Err(fail(
                StatusCode::FORBIDDEN,
                "This action is available only from the local app",
            ));
        }
    }
    Ok(())
}
async fn state(State(app): State<App>) -> Response {
    let body = app.payload.read().unwrap().clone();
    (
        [
            (header::CONTENT_TYPE, "application/json"),
            (header::CACHE_CONTROL, "no-store"),
        ],
        body,
    )
        .into_response()
}
async fn health(State(app): State<App>) -> Json<Value> {
    Json(
        json!({"ok":true,"runtime":"Rust","version":env!("CARGO_PKG_VERSION"),"python_required_for_navigation":false,"data_ready":app.data.read().unwrap().is_some(),"model_ready":app.model.read().unwrap().is_some()}),
    )
}
async fn jobs(State(app): State<App>) -> Json<Value> {
    Json(json!(
        app.jobs
            .lock()
            .unwrap()
            .values()
            .cloned()
            .collect::<Vec<_>>()
    ))
}
async fn job(State(app): State<App>, Param(id): Param<u64>) -> ApiResult {
    app.jobs
        .lock()
        .unwrap()
        .get(&id)
        .map(|j| Json(json!(j)))
        .ok_or_else(|| fail(StatusCode::NOT_FOUND, "Task not found"))
}
#[derive(Deserialize, Default)]
struct TeamLoadQuery {
    expected_name: Option<String>,
    expected_manager: Option<String>,
}
async fn search_teams(
    State(app): State<App>,
    headers: HeaderMap,
    Json(request): Json<team_search::Request>,
) -> ApiResult {
    origin(&app, &headers)?;
    let name =
        team_search::validate_name(&request.name).map_err(|e| fail(StatusCode::BAD_REQUEST, e))?;
    if request.page == 0 || request.page > 10000 {
        return Err(fail(StatusCode::BAD_REQUEST, "Invalid search page"));
    }
    let league = if request.league_url.trim().is_empty() {
        None
    } else {
        Some(
            team_search::league_id(&request.league_url)
                .map_err(|e| fail(StatusCode::BAD_REQUEST, e))?,
        )
    };
    let known = request
        .known_entry_id
        .filter(|i| (1..=1_000_000_000).contains(i));
    if league.is_none() && known.is_none() {
        return Err(fail(
            StatusCode::BAD_REQUEST,
            "FPL has no global team-name search. For the first lookup, paste a public classic mini-league link, or select your squad manually. No team ID is required.",
        ));
    }
    let id = app
        .new_job("team-search")
        .map_err(|e| fail(StatusCode::CONFLICT, e))?;
    let worker = app.clone();
    tokio::spawn(async move {
        let start = Instant::now();
        let result = search_team_names(&worker, id, &name, league, request.page, known).await;
        worker.finish(id, result, start.elapsed().as_secs_f64() * 1000.);
    });
    Ok(Json(json!({"job":id})))
}
async fn search_team_names(
    app: &App,
    job: u64,
    name: &str,
    league: Option<u64>,
    page: u32,
    known: Option<u64>,
) -> Result<Value, String> {
    if page == 1
        && let Some(reference) = known
    {
        app.log(
            job,
            "Checking your saved team connection by its current name",
            10,
        );
        if let Ok(entry) = app.fetch(&format!("entry/{reference}/")).await
            && let Some(candidate) = team_search::saved_candidate(&entry, reference, name)
        {
            return Ok(team_search::response(
                name,
                "Saved connection",
                vec![candidate],
                1,
                None,
                true,
            ));
        }
        if league.is_none() {
            return Err("The saved connection could not be verified under this name. Enter the current name and a public classic mini-league link to search again.".into());
        }
    }
    let league =
        league.ok_or("A public classic mini-league link is needed for a new name search")?;
    let mut matches = BTreeMap::new();
    let mut scanned = 0;
    let mut next = None;
    let mut league_name = String::new();
    // Two pages per explicit action. Never crawl millions of overall-league entries.
    for number in page..page + 2 {
        let endpoint = format!("leagues-classic/{league}/standings/?page_standings={number}");
        app.log(
            job,
            format!("Searching public classic league page {number}…"),
            20 + ((number - page) * 35) as u64,
        );
        let cached = {
            let cache = app.league_cache.lock().unwrap();
            cache
                .get(&endpoint)
                .filter(|(t, _)| t.elapsed() < Duration::from_secs(300))
                .map(|(_, v)| v.clone())
        };
        let response = if let Some(value) = cached {
            value
        } else {
            let value = app.fetch(&endpoint).await?;
            team_search::candidates(&value, name)?;
            let mut cache = app.league_cache.lock().unwrap();
            if cache.len() >= 20
                && let Some(key) = cache.keys().next().cloned()
            {
                cache.remove(&key);
            }
            cache.insert(endpoint, (Instant::now(), value.clone()));
            value
        };
        league_name = response["league"]["name"]
            .as_str()
            .unwrap_or("Public mini-league")
            .into();
        scanned += response["standings"]["results"]
            .as_array()
            .map_or(0, Vec::len);
        for candidate in team_search::candidates(&response, name)? {
            matches.insert(candidate.reference, candidate);
        }
        let has_next = response["standings"]["has_next"]
            .as_bool()
            .ok_or("Invalid public league pagination")?;
        next = if has_next { Some(number + 1) } else { None };
        if !has_next {
            break;
        }
        if number == page {
            tokio::time::sleep(Duration::from_millis(400)).await;
        }
    }
    let mut candidates: Vec<_> = matches.into_values().collect();
    candidates.sort_by(|a, b| {
        b.exact
            .cmp(&a.exact)
            .then(a.rank.unwrap_or(u64::MAX).cmp(&b.rank.unwrap_or(u64::MAX)))
    });
    Ok(team_search::response(
        name,
        &league_name,
        candidates,
        scanned,
        next,
        false,
    ))
}
async fn team(
    State(app): State<App>,
    Param(id): Param<u64>,
    Query(query): Query<TeamLoadQuery>,
) -> ApiResult {
    if id == 0 || id > 1_000_000_000 {
        return Err(fail(
            StatusCode::BAD_REQUEST,
            "Invalid saved team reference. Search for your team by name again.",
        ));
    }
    let entry = app
        .fetch(&format!("entry/{id}/"))
        .await
        .map_err(|e| fail(StatusCode::BAD_GATEWAY, e))?;
    if let Some(expected) = query.expected_name.as_deref() {
        team_search::validate_name(expected).map_err(|e| fail(StatusCode::BAD_REQUEST, e))?;
        if team_search::normalise(entry["name"].as_str().unwrap_or(""))
            != team_search::normalise(expected)
        {
            app.league_cache.lock().unwrap().clear();
            return Err(fail(
                StatusCode::CONFLICT,
                "This team's name changed after the search. Search again before loading; your existing squad was preserved.",
            ));
        }
    }
    if let Some(expected) = query.expected_manager.as_deref() {
        let actual = format!(
            "{} {}",
            entry["player_first_name"].as_str().unwrap_or(""),
            entry["player_last_name"].as_str().unwrap_or("")
        );
        if team_search::normalise(&actual) != team_search::normalise(expected) {
            return Err(fail(
                StatusCode::CONFLICT,
                "Manager name changed. Reconnect before loading; your existing squad was preserved.",
            ));
        }
    }
    let event = data::id(&entry["current_event"]);
    if event == 0 {
        return Err(fail(
            StatusCode::BAD_REQUEST,
            "Public picks are not available before your first deadline. Select your squad manually or build a new team.",
        ));
    }
    let picks = app
        .fetch(&format!("entry/{id}/event/{event}/picks/"))
        .await
        .map_err(|e| fail(StatusCode::BAD_GATEWAY, e))?;
    let owned: Vec<u64> = picks["picks"]
        .as_array()
        .ok_or_else(|| fail(StatusCode::BAD_GATEWAY, "FPL did not return squad picks"))?
        .iter()
        .map(|p| data::id(&p["element"]))
        .collect();
    let data = app
        .dataset()
        .map_err(|e| fail(StatusCode::SERVICE_UNAVAILABLE, e))?;
    optimize::validate(&data.players, &owned).map_err(|e| fail(StatusCode::BAD_REQUEST, e))?;
    Ok(Json(
        json!({"id":id,"name":entry["name"],"event":event,"owned":owned,"note":"Public last-deadline picks. Confirm subsequent transfers and financial information yourself."}),
    ))
}
async fn optimize(
    State(app): State<App>,
    headers: HeaderMap,
    Json(request): Json<optimize::Request>,
) -> ApiResult {
    origin(&app, &headers)?;
    let data = app
        .dataset()
        .map_err(|e| fail(StatusCode::SERVICE_UNAVAILABLE, e))?;
    let id = app
        .new_job("optimize")
        .map_err(|e| fail(StatusCode::CONFLICT, e))?;
    let worker = app.clone();
    tokio::task::spawn_blocking(move || {
        let start = Instant::now();
        worker.log(
            id,
            "Solving official squad, budget and formation constraints in Rust",
            15,
        );
        let result = optimize::solve(&data, &request).map(|p| serde_json::to_value(p).unwrap());
        worker.finish(id, result, start.elapsed().as_secs_f64() * 1000.);
    });
    Ok(Json(json!({"job":id})))
}
#[derive(Deserialize)]
struct TaskRequest {
    kind: String,
}
async fn task(
    State(app): State<App>,
    headers: HeaderMap,
    Json(request): Json<TaskRequest>,
) -> ApiResult {
    origin(&app, &headers)?;
    if !["refresh", "histories", "train", "download"].contains(&request.kind.as_str()) {
        return Err(fail(StatusCode::BAD_REQUEST, "Unsupported task"));
    }
    let id = app
        .new_job(&request.kind)
        .map_err(|e| fail(StatusCode::CONFLICT, e))?;
    let worker = app.clone();
    tokio::spawn(async move {
        let start = Instant::now();
        let result = if request.kind == "refresh" || request.kind == "histories" {
            refresh(&worker, id, request.kind == "histories").await
        } else {
            python_job(&worker, id, &request.kind).await
        };
        worker.finish(id, result, start.elapsed().as_secs_f64() * 1000.);
    });
    Ok(Json(json!({"job":id})))
}
async fn refresh(app: &App, id: u64, histories: bool) -> Result<Value, String> {
    let b = app.fetch("bootstrap-static/").await?;
    let elements = b["elements"]
        .as_array()
        .ok_or("Invalid official player schema")?;
    if elements.is_empty()
        || elements.iter().any(|p| {
            data::id(&p["id"]) == 0
                || data::id(&p["team"]) == 0
                || data::id(&p["element_type"]) == 0
                || !p["now_cost"].is_number()
        })
    {
        return Err("Invalid official player metadata".into());
    }
    let f = app.fetch("fixtures/").await?;
    if !f.is_array() {
        return Err("Invalid official fixture schema".into());
    }
    app.store("bootstrap-static/", &b)?;
    app.store("fixtures/", &f)?;
    app.log(id, "Updated official players, prices and fixtures", 15);
    if histories {
        for (i, p) in elements.iter().enumerate() {
            let pid = data::id(&p["id"]);
            let endpoint = format!("element-summary/{pid}/");
            let h = app.fetch(&endpoint).await?;
            if !h["history"].is_array() {
                return Err(format!("Invalid history for player {pid}"));
            }
            app.store(&endpoint, &h)?;
            if i % 10 == 0 {
                app.log(
                    id,
                    format!("Cached {}/{} player histories", i + 1, elements.len()),
                    15 + (i * 80 / elements.len()) as u64,
                );
            }
            tokio::time::sleep(Duration::from_millis(400)).await;
        }
    }
    app.rebuild()?;
    Ok(
        json!({"updated":true,"histories":histories,"note":"Public snapshots updated. Predictions recomputed locally."}),
    )
}
async fn python_job(app: &App, id: u64, kind: &str) -> Result<Value, String> {
    let local = if cfg!(windows) {
        app.root.join(".venv/Scripts/python.exe")
    } else {
        app.root.join(".venv/bin/python")
    };
    let python = std::env::var_os("FPL_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            if local.exists() {
                local
            } else {
                PathBuf::from("python")
            }
        });
    app.log(
        id,
        "Starting the existing local Python training tools. Other pages remain available.",
        5,
    );
    let mut child=tokio::process::Command::new(python).current_dir(&*app.root).args(["-u","-m","fpl_ai.ml.native_job",kind]).stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::piped()).kill_on_drop(true).spawn().map_err(|e|format!("Python is needed only for training. Run SETUP_LOCAL_TRAINING.bat first. Details: {e}"))?;
    let stderr = child.stderr.take().unwrap();
    let stdout = child.stdout.take().unwrap();
    let log_app = app.clone();
    let reader = tokio::spawn(async move {
        let mut lines = tokio::io::BufReader::new(stderr).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            log_app.log(id, line, 30);
        }
    });
    let mut lines = tokio::io::BufReader::new(stdout).lines();
    while let Some(line) = lines.next_line().await.map_err(|e| e.to_string())? {
        let p = if line.contains("minutes") {
            60
        } else if line.contains("probability") {
            80
        } else {
            20
        };
        app.log(id, line, p);
    }
    let status = child.wait().await.map_err(|e| e.to_string())?;
    let _ = reader.await;
    if !status.success() {
        return Err("Local Python task failed. See the task log above; existing saved models were preserved.".into());
    }
    if kind == "train" {
        app.reload_model()?;
    }
    Ok(json!({"completed":kind,"model_reloaded":kind=="train"}))
}
fn project_root() -> PathBuf {
    if let Some(root) = std::env::var_os("FPL_PROJECT_DIR") {
        return PathBuf::from(root);
    }
    let cwd = std::env::current_dir().unwrap();
    if cwd.join("data").exists() && cwd.join("models").exists() {
        return cwd;
    }
    if let Ok(exe) = std::env::current_exe() {
        for parent in exe.ancestors().skip(1) {
            if parent.join("data").exists() && parent.join("models").exists() {
                return parent.to_path_buf();
            }
        }
    }
    cwd
}
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = project_root();
    // Verification mode is also used by prediction parity tests, without opening a server.
    let args: Vec<_> = std::env::args().collect();
    if args.get(1).map(|s| s.as_str()) == Some("--predict-features") {
        let model = Model::load(&root.join("models/native-model.json"))?;
        let input = std::fs::read_to_string(args.get(2).ok_or("Supply feature JSON file")?)?;
        let rows: Vec<Vec<Option<f64>>> = serde_json::from_str(&input)?;
        if rows.iter().any(|r| r.len() != model.features.len()) {
            return Err("Expected exactly 29 features per row".into());
        }
        let result: Vec<_> = rows
            .iter()
            .map(|r| model.predict(&r.iter().map(|v| v.unwrap_or(f64::NAN)).collect::<Vec<_>>()))
            .collect();
        println!("{}", serde_json::to_string(&result)?);
        return Ok(());
    }
    let port = std::env::var("FPL_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .unwrap_or(7878);
    let model = Model::load(&root.join("models/native-model.json"))
        .map(Arc::new)
        .ok();
    let mut client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .user_agent("FPL-Local-Manager/0.2 public read-only data");
    // Honor explicitly configured public CA bundles without weakening TLS.
    if let Some(path) =
        std::env::var_os("FPL_CA_BUNDLE").or_else(|| std::env::var_os("SSL_CERT_FILE"))
    {
        let pem = std::fs::read(path)?;
        for cert in reqwest::Certificate::from_pem_bundle(&pem)? {
            client = client.add_root_certificate(cert);
        }
    }
    let app = App {
        root: Arc::new(root),
        data: Arc::new(RwLock::new(None)),
        payload: Arc::new(RwLock::new(json!({"players":[],"events":[],"error":"No public data yet. Choose Refresh data.","report":{},"model_version":"No model"}).to_string())),
        model: Arc::new(RwLock::new(model)),
        jobs: Arc::new(Mutex::new(BTreeMap::new())),
        counter: Arc::new(AtomicU64::new(1)),
        client: client.build()?,
        port,
        pairing: Arc::new(Mutex::new(None)),
        league_cache: Arc::new(Mutex::new(BTreeMap::new())),
    };
    let start = Instant::now();
    if let Err(e) = app.rebuild() {
        eprintln!("Using empty workspace: {e}");
    }
    let ticker = app.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            let due = ticker
                .data
                .read()
                .unwrap()
                .as_ref()
                .and_then(|d| d.events.first())
                .is_some_and(|e| data::stamp(&json!(e.deadline)) <= Utc::now().timestamp());
            if due {
                let _ = ticker.rebuild();
            }
        }
    });
    let routes = Router::new()
        .route(
            "/",
            get(|| async { Html(include_str!("../web/index.html")) }),
        )
        .route(
            "/app.css",
            get(|| async {
                (
                    [(header::CONTENT_TYPE, "text/css")],
                    include_str!("../web/app.css"),
                )
            }),
        )
        .route(
            "/app.js",
            get(|| async {
                (
                    [(header::CONTENT_TYPE, "text/javascript")],
                    include_str!("../web/app.js"),
                )
            }),
        )
        .route("/api/health", get(health))
        .route("/api/state", get(state))
        .route("/api/jobs", get(jobs))
        .route("/api/jobs/{id}", get(job))
        .route("/api/team/{id}", get(team))
        .route("/api/team-search", post(search_teams))
        .route("/api/connect/start", post(connection::start))
        .route("/api/connect/prices", post(connection::start_prices))
        .route("/api/connect/status", post(connection::status))
        .route("/api/connect/complete", post(connection::complete))
        .route("/api/optimize", post(optimize))
        .route("/api/tasks", post(task))
        .layer(axum::extract::DefaultBodyLimit::max(65536))
        .layer(CompressionLayer::new())
        .with_state(app);
    let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).await?;
    println!(
        "FPL Manager · Rust\nReady in {:.0} ms · http://127.0.0.1:{port}\nNo Python process is needed for browsing, inference or squad optimization.\nPress Ctrl+C to stop.",
        start.elapsed().as_secs_f64() * 1000.
    );
    axum::serve(listener, routes)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
