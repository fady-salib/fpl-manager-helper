//! Scoped public team-name search. FPL has no global manager/team-name search API.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

fn first_page() -> u32 {
    1
}
#[derive(Clone, Deserialize)]
pub struct Request {
    pub name: String,
    #[serde(default)]
    pub league_url: String,
    #[serde(default = "first_page")]
    pub page: u32,
    #[serde(default)]
    pub known_entry_id: Option<u64>,
}
#[derive(Clone, Serialize)]
pub struct Candidate {
    pub reference: u64,
    pub name: String,
    pub manager: String,
    pub rank: Option<u64>,
    pub exact: bool,
}
pub fn normalise(name: &str) -> String {
    name.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}
pub fn validate_name(name: &str) -> Result<String, String> {
    let value = name.split_whitespace().collect::<Vec<_>>().join(" ");
    if value.is_empty() || value.chars().count() > 80 || value.chars().any(char::is_control) {
        return Err("Enter your FPL team name (1–80 characters).".into());
    }
    Ok(value)
}
pub fn league_id(value: &str) -> Result<u64, String> {
    let value = value.trim();
    let url = reqwest::Url::parse(value)
        .map_err(|_| "Paste a public classic mini-league link from your FPL Leagues page.")?;
    if url.scheme() != "https"
        || url.host_str() != Some("fantasy.premierleague.com")
        || !url.username().is_empty()
        || url.password().is_some()
        || url.port().is_some_and(|p| p != 443)
    {
        return Err("Use an HTTPS classic league link on fantasy.premierleague.com.".into());
    }
    let path: Vec<_> = url
        .path_segments()
        .ok_or("Invalid league link")?
        .filter(|p| !p.is_empty())
        .collect();
    if path.len() != 4 || path[0] != "leagues" || path[2] != "standings" || path[3] != "c" {
        return Err("Use a public classic mini-league link ending /leagues/…/standings/c. Head-to-head links and invitation codes are not supported.".into());
    }
    path[1]
        .parse::<u64>()
        .ok()
        .filter(|i| (1..=1_000_000_000).contains(i))
        .ok_or("Invalid classic league reference".into())
}
pub fn candidates(page: &Value, name: &str) -> Result<Vec<Candidate>, String> {
    let query = normalise(name);
    let rows = page["standings"]["results"].as_array().ok_or("This league does not expose public classic standings. Try another public mini-league or select your squad manually.")?;
    let mut result = BTreeMap::new();
    for row in rows {
        let Some(reference) = row["entry"].as_u64().filter(|i| *i > 0) else {
            continue;
        };
        let Some(team_name) = row["entry_name"].as_str() else {
            continue;
        };
        let folded = normalise(team_name);
        if folded.contains(&query) {
            result.insert(
                reference,
                Candidate {
                    reference,
                    name: team_name.into(),
                    manager: row["player_name"]
                        .as_str()
                        .unwrap_or("Manager name unavailable")
                        .into(),
                    rank: row["rank"].as_u64(),
                    exact: folded == query,
                },
            );
        }
    }
    let mut result: Vec<_> = result.into_values().collect();
    result.sort_by(|a, b| {
        b.exact
            .cmp(&a.exact)
            .then(a.rank.unwrap_or(u64::MAX).cmp(&b.rank.unwrap_or(u64::MAX)))
            .then(a.reference.cmp(&b.reference))
    });
    Ok(result)
}
pub fn saved_candidate(entry: &Value, reference: u64, name: &str) -> Option<Candidate> {
    let team_name = entry["name"].as_str()?;
    if normalise(team_name) != normalise(name) {
        return None;
    }
    Some(Candidate {
        reference,
        name: team_name.into(),
        manager: format!(
            "{} {}",
            entry["player_first_name"].as_str().unwrap_or(""),
            entry["player_last_name"].as_str().unwrap_or("")
        )
        .trim()
        .into(),
        rank: entry["summary_overall_rank"].as_u64(),
        exact: true,
    })
}
pub fn response(
    name: &str,
    league: &str,
    candidates: Vec<Candidate>,
    scanned: usize,
    next: Option<u32>,
    saved: bool,
) -> Value {
    json!({"query":name,"league":league,"candidates":candidates,"scanned":scanned,"next_page":next,"complete":next.is_none(),"saved_connection":saved,"notice":if saved {"Matched your saved connection. Search the league instead to choose another team with the same name."} else {"Names are not unique. Choose the matching team and manager. This searches the supplied league, not every FPL manager."}})
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn whitespace_and_case() {
        assert_eq!(normalise("  ØDEGAARD   FC  "), "ødegaard fc");
    }
    #[test]
    fn real_classic_url() {
        assert_eq!(
            league_id(
                "https://fantasy.premierleague.com/leagues/123/standings/c/?page_standings=2"
            )
            .unwrap(),
            123
        );
    }
    #[test]
    fn reject_other_hosts_and_league_kinds() {
        for link in [
            "https://example.com/leagues/1/standings/c",
            "https://fantasy.premierleague.com.evil.test/leagues/1/standings/c",
            "http://fantasy.premierleague.com/leagues/1/standings/c",
            "https://fantasy.premierleague.com/leagues/1/standings/h",
            "123456",
        ] {
            assert!(league_id(link).is_err(), "{link}");
        }
    }
    #[test]
    fn duplicate_names_remain_distinct() {
        let p = json!({"standings":{"results":[{"entry":10,"entry_name":"My XI","player_name":"Alice","rank":3},{"entry":20,"entry_name":"my xi","player_name":"Bob","rank":7},{"entry":30,"entry_name":"Other","player_name":"Alice","rank":8}]}});
        let c = candidates(&p, " MY XI ").unwrap();
        assert_eq!(c.len(), 2);
        assert!(c.iter().all(|c| c.exact));
        assert_ne!(c[0].reference, c[1].reference);
    }
    #[test]
    fn blank_names_and_bad_schema() {
        assert!(validate_name("  ").is_err());
        assert!(validate_name(&"x".repeat(81)).is_err());
        assert!(candidates(&json!({}), "My XI").is_err());
    }
    #[test]
    fn saved_reference_must_match_current_name() {
        assert!(saved_candidate(&json!({"name":"Other XI"}), 10, "My XI").is_none());
        assert!(saved_candidate(&json!({"name":"MY XI"}), 10, "my xi").is_some());
    }
    #[test]
    fn partial_search_not_claimed_complete() {
        let r = response("My XI", "Public league", vec![], 100, Some(3), false);
        assert_eq!(r["complete"], false);
        assert_eq!(r["next_page"], 3);
    }
}
