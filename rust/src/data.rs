use crate::model::Model;
use chrono::{DateTime, Utc};
use rusqlite::Connection;
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashMap},
    path::Path,
    time::Instant,
};

pub const STATS: [&str; 9] = [
    "total_points",
    "minutes",
    "goals_scored",
    "assists",
    "clean_sheets",
    "bonus",
    "expected_goals",
    "expected_assists",
    "starts",
];
pub fn number(v: &Value) -> f64 {
    v.as_f64()
        .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        .unwrap_or(f64::NAN)
}
pub fn id(v: &Value) -> u64 {
    v.as_u64().unwrap_or(0)
}
pub fn stamp(v: &Value) -> i64 {
    v.as_str()
        .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
        .map(|d| d.timestamp())
        .unwrap_or(i64::MAX)
}
fn text(v: &Value) -> String {
    v.as_str().unwrap_or("").into()
}

#[derive(Clone, Serialize)]
pub struct Event {
    pub id: u64,
    pub deadline: String,
    pub name: String,
}
#[derive(Clone, Serialize)]
pub struct Game {
    pub opponent: String,
    pub home: bool,
    pub difficulty: u64,
    pub kickoff: String,
}
#[derive(Clone, Serialize)]
pub struct Week {
    pub event: u64,
    pub points: f64,
    pub fixtures: Vec<Game>,
}
#[derive(Clone, Serialize)]
pub struct Player {
    pub id: u64,
    pub name: String,
    pub full_name: String,
    pub position: u64,
    pub club: String,
    pub team: u64,
    pub cost: u64,
    pub ownership: f64,
    pub status: String,
    pub news: String,
    pub form: f64,
    pub actual_points: f64,
    pub expected_points: f64,
    pub expected_minutes: f64,
    pub probabilities: BTreeMap<String, f64>,
    pub weeks: Vec<Week>,
    pub history_samples: usize,
    pub purchasable: bool,
    pub last_points: Vec<f64>,
    pub risk_history: Vec<f64>,
}
#[derive(Clone)]
pub struct DataSet {
    pub players: Vec<Player>,
    pub events: Vec<Event>,
    pub bootstrap: Value,
    pub fixtures: Vec<Value>,
    pub snapshot_at: String,
    pub model_version: String,
    pub report: Value,
    pub compute_ms: f64,
}
pub fn lag_features(history: &[Value], event: u64, now: i64) -> (Vec<f64>, usize) {
    let mut past: Vec<_> = history
        .iter()
        .filter(|h| {
            id(&h["round"]) < event
                && stamp(&h["kickoff_time"])
                    .checked_add(10800)
                    .is_some_and(|t| t < now)
        })
        .collect();
    past.sort_by_key(|h| stamp(&h["kickoff_time"]));
    let mean = |stat: &str, window: usize| {
        let start = past.len().saturating_sub(window);
        let values: Vec<f64> = past[start..]
            .iter()
            .map(|h| number(&h[stat]))
            .filter(|v| v.is_finite())
            .collect();
        if values.is_empty() {
            f64::NAN
        } else {
            values.iter().sum::<f64>() / values.len() as f64
        }
    };
    let mut result = Vec::with_capacity(29);
    for window in [3, 5, 10] {
        for stat in STATS {
            result.push(mean(stat, window));
        }
    }
    result.push(mean("total_points", usize::MAX));
    result.push(mean("minutes", usize::MAX));
    (result, past.len())
}
pub fn read_snapshots(root: &Path) -> Result<HashMap<String, (String, Value)>, String> {
    let db = root.join("data/fpl.sqlite");
    if !db.exists() {
        return Err("No public snapshots. Use Refresh data to download them.".into());
    }
    let con = Connection::open(db).map_err(|e| e.to_string())?;
    let mut statement=con.prepare("SELECT endpoint,fetched_at,payload FROM (SELECT endpoint,fetched_at,payload,ROW_NUMBER() OVER (PARTITION BY endpoint ORDER BY fetched_at DESC,id DESC) r FROM snapshots) WHERE r=1").map_err(|e|e.to_string())?;
    let records = statement
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
            ))
        })
        .map_err(|e| e.to_string())?;
    let mut out = HashMap::new();
    for row in records {
        let (e, t, p) = row.map_err(|e| e.to_string())?;
        out.insert(e, (t, serde_json::from_str(&p).map_err(|e| e.to_string())?));
    }
    Ok(out)
}
impl DataSet {
    pub fn load(root: &Path, model: Option<&Model>, now: i64) -> Result<Self, String> {
        let start = Instant::now();
        let mut snapshots = read_snapshots(root)?;
        let (snapshot_at, b) = snapshots
            .remove("bootstrap-static/")
            .ok_or("No player metadata cached")?;
        let fixtures = snapshots
            .remove("fixtures/")
            .and_then(|(_, f)| f.as_array().cloned())
            .ok_or("No fixtures cached")?;
        let mut events: Vec<Event> = b["events"]
            .as_array()
            .ok_or("Missing gameweeks")?
            .iter()
            .filter(|e| stamp(&e["deadline_time"]) > now)
            .take(8)
            .map(|e| Event {
                id: id(&e["id"]),
                deadline: text(&e["deadline_time"]),
                name: text(&e["name"]),
            })
            .collect();
        events.sort_by_key(|e| e.id);
        let first = events.first().map(|e| e.id).unwrap_or(u64::MAX);
        let clubs: HashMap<u64, String> = b["teams"]
            .as_array()
            .ok_or("Missing clubs")?
            .iter()
            .map(|t| (id(&t["id"]), text(&t["short_name"])))
            .collect();
        let mut games: HashMap<(u64, u64), Vec<Game>> = HashMap::new();
        for f in &fixtures {
            let event = id(&f["event"]);
            for home in [true, false] {
                let (team, opp, difficulty) = if home {
                    (
                        id(&f["team_h"]),
                        id(&f["team_a"]),
                        id(&f["team_h_difficulty"]),
                    )
                } else {
                    (
                        id(&f["team_a"]),
                        id(&f["team_h"]),
                        id(&f["team_a_difficulty"]),
                    )
                };
                games.entry((team, event)).or_default().push(Game {
                    opponent: clubs.get(&opp).cloned().unwrap_or_default(),
                    home,
                    difficulty,
                    kickoff: text(&f["kickoff_time"]),
                });
            }
        }
        let mut players = Vec::new();
        for p in b["elements"].as_array().ok_or("Missing players")? {
            let pid = id(&p["id"]);
            let team = id(&p["team"]);
            let history = snapshots
                .get(&format!("element-summary/{pid}/"))
                .and_then(|(_, h)| h["history"].as_array())
                .cloned()
                .unwrap_or_default();
            let (x, samples) = lag_features(&history, first, now);
            let values = model.map(|m| m.predict(&x)).unwrap_or_default();
            let baseline = 0.7 * number(&p["form"]) + 0.3 * number(&p["points_per_game"]);
            let points = values
                .get("total_points")
                .copied()
                .unwrap_or(if baseline.is_finite() { baseline } else { 0. });
            let minutes = values
                .get("minutes")
                .copied()
                .unwrap_or_else(|| if x[10].is_finite() { x[10] } else { 0. });
            let weeks = events
                .iter()
                .map(|e| {
                    let fs = games.get(&(team, e.id)).cloned().unwrap_or_default();
                    Week {
                        event: e.id,
                        points: points * fs.len() as f64,
                        fixtures: fs,
                    }
                })
                .collect();
            let mut last: Vec<_> = history
                .iter()
                .filter(|h| {
                    id(&h["round"]) < first
                        && stamp(&h["kickoff_time"])
                            .checked_add(10800)
                            .is_some_and(|t| t < now)
                })
                .collect();
            last.sort_by_key(|h| stamp(&h["kickoff_time"]));
            let risk_history = last
                .iter()
                .rev()
                .take(10)
                .map(|h| number(&h["total_points"]))
                .filter(|v| v.is_finite())
                .collect();
            let last_points = last
                .iter()
                .rev()
                .take(5)
                .rev()
                .map(|h| number(&h["total_points"]))
                .filter(|p| p.is_finite())
                .collect();
            let probabilities = values
                .into_iter()
                .filter(|(k, _)| k != "total_points" && k != "minutes")
                .collect();
            players.push(Player {
                id: pid,
                name: text(&p["web_name"]),
                full_name: format!("{} {}", text(&p["first_name"]), text(&p["second_name"])),
                position: id(&p["element_type"]),
                club: clubs.get(&team).cloned().unwrap_or_default(),
                team,
                cost: id(&p["now_cost"]),
                ownership: {
                    let n = number(&p["selected_by_percent"]);
                    if n.is_finite() { n } else { 0. }
                },
                status: text(&p["status"]),
                news: text(&p["news"]),
                form: {
                    let n = number(&p["form"]);
                    if n.is_finite() { n } else { 0. }
                },
                actual_points: number(&p["total_points"]),
                expected_points: points,
                expected_minutes: minutes,
                probabilities,
                weeks,
                history_samples: samples,
                purchasable: !p["removed"].as_bool().unwrap_or(false)
                    && p["can_select"].as_bool().unwrap_or(true),
                last_points,
                risk_history,
            });
        }
        players.sort_by(|a, b| b.expected_points.total_cmp(&a.expected_points));
        Ok(Self {
            players,
            events,
            bootstrap: b,
            fixtures,
            snapshot_at,
            model_version: model
                .map(|m| m.version.clone())
                .unwrap_or("Form baseline".into()),
            report: model.map(|m| m.metadata.clone()).unwrap_or(json!({})),
            compute_ms: start.elapsed().as_secs_f64() * 1000.,
        })
    }
    pub fn response(&self) -> Value {
        let players: Vec<Value> = self.players.iter().map(|p| {
            let mut v = serde_json::to_value(p).unwrap();
            v["risk_scores"] = json!({
                "aggressive":(0..p.weeks.len()).map(|k|crate::optimize::utility(p,k,crate::optimize::RiskMode::Aggressive)).collect::<Vec<_>>(),
                "conservative":(0..p.weeks.len()).map(|k|crate::optimize::utility(p,k,crate::optimize::RiskMode::Conservative)).collect::<Vec<_>>(),
                "balanced":p.weeks.iter().map(|w|w.points).collect::<Vec<_>>()});
            v
        }).collect();
        json!({"players":players,"events":self.events,"teams":self.bootstrap["teams"],"chips":self.bootstrap["chips"],"snapshot_at":self.snapshot_at,"model_version":self.model_version,"report":self.report,"compute_ms":self.compute_ms,"season":self.bootstrap["game_config"]["settings"]["static_content_url"],"rules":self.bootstrap["game_config"]["rules"],"fixture_count":self.fixtures.len(),"generated_at":Utc::now().to_rfc3339()})
    }
    pub fn check_rules(&self, horizon: usize) -> Result<(), String> {
        let season = self.bootstrap["game_config"]["settings"]["static_content_url"]
            .as_str()
            .unwrap_or("");
        if !season.trim_end_matches('/').ends_with("2026_27") {
            return Err(
                "Season rules need review before optimization; read-only pages remain available."
                    .into(),
            );
        }
        for e in self.bootstrap["events"].as_array().into_iter().flatten() {
            if self
                .events
                .iter()
                .take(horizon)
                .any(|x| x.id == id(&e["id"]))
                && e["overrides"].as_object().is_some_and(|o| {
                    o.iter().any(|(k, v)| {
                        ["rules", "scoring", "element_types", "pick_multiplier"]
                            .contains(&k.as_str())
                            && !v.is_null()
                            && v != &json!({})
                            && v != &json!([])
                    })
                })
            {
                return Err("This gameweek has special rules requiring review".into());
            }
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_same_round_or_future_results() {
        let h = vec![
            json!({"round":1,"kickoff_time":"2026-01-01T12:00:00Z","total_points":4,"minutes":90}),
            json!({"round":2,"kickoff_time":"2026-01-02T12:00:00Z","total_points":999,"minutes":90}),
        ];
        let (x, n) = lag_features(&h, 2, stamp(&json!("2026-01-03T12:00:00Z")));
        assert_eq!(n, 1);
        assert_eq!(x[0], 4.);
        assert!(x[2].is_nan());
    }
    #[test]
    fn completion_cutoff() {
        let h = vec![json!({"round":1,"kickoff_time":"2026-01-01T12:00:00Z","total_points":4})];
        assert_eq!(
            lag_features(&h, 2, stamp(&json!("2026-01-01T13:00:00Z"))).1,
            0
        );
    }
}
