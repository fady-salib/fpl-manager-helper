use crate::data::{DataSet, Player, id};
use good_lp::{
    Expression, Solution, SolverModel, WithInitialSolution, WithTimeLimit,
    solvers::{SolutionStatus, microlp::microlp},
    variable, variables,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, HashMap, HashSet},
    time::Instant,
};

/// Selection preference, never a replacement for the model's mean prediction.
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum RiskMode {
    Conservative,
    #[default]
    Balanced,
    Aggressive,
}
pub fn utility(p: &Player, k: usize, mode: RiskMode) -> f64 {
    let mean = points(p, k);
    let n = p.risk_history.len();
    if mode == RiskMode::Balanced || n < 3 || mean <= 0. {
        return mean;
    }
    let mut observed = p.risk_history.clone();
    observed.sort_by(f64::total_cmp);
    let average = observed.iter().sum::<f64>() / n as f64;
    let reliability = (p.expected_minutes / 90.).clamp(0., 1.);
    let shrink = n as f64 / (n as f64 + 5.);
    let fixtures = p.weeks.get(k).map_or(0, |w| w.fixtures.len()).max(1) as f64;
    let adjustment = match mode {
        RiskMode::Aggressive => {
            (observed[((n - 1) as f64 * 0.85).ceil() as usize] - average).max(0.) * reliability
        }
        RiskMode::Conservative => {
            -(average - observed[((n - 1) as f64 * 0.15).floor() as usize]).max(0.)
        }
        RiskMode::Balanced => 0.,
    };
    // Empirical historical spread, shrunk for small samples; not calibrated quantiles.
    mean + 0.65 * shrink * adjustment * fixtures.sqrt()
}

fn horizon() -> usize {
    3
}
fn free() -> u64 {
    1
}
fn maximum() -> u64 {
    2
}
#[derive(Clone, Deserialize, Default)]
pub struct Request {
    #[serde(default = "horizon")]
    pub horizon: usize,
    #[serde(default)]
    pub risk_mode: RiskMode,
    #[serde(default)]
    pub owned: Vec<u64>,
    #[serde(default)]
    pub sale_prices: BTreeMap<u64, u64>,
    #[serde(default)]
    pub bank: u64,
    #[serde(default = "free")]
    pub free_transfers: u64,
    #[serde(default = "maximum")]
    pub max_transfers: u64,
    #[serde(default)]
    pub locked: Vec<u64>,
    #[serde(default)]
    pub excluded: Vec<u64>,
    #[serde(default)]
    pub chip: Option<String>,
    #[serde(default)]
    pub available_chip_ids: Vec<u64>,
    #[serde(default)]
    pub previous_chip: Option<String>,
}
#[derive(Clone, Debug, Serialize)]
pub struct WeekPlan {
    pub event: u64,
    pub xi: Vec<u64>,
    pub bench: Vec<u64>,
    pub captain: u64,
    pub vice_captain: u64,
    pub points: f64,
    pub selection_score: f64,
}
#[derive(Clone, Debug, Serialize)]
pub struct Plan {
    pub squad: Vec<u64>,
    pub weeks: Vec<WeekPlan>,
    pub transfers_in: Vec<u64>,
    pub transfers_out: Vec<u64>,
    pub bank: u64,
    pub hit: u64,
    pub expected_points: f64,
    pub selection_score: f64,
    pub risk_mode: RiskMode,
    pub optimal: bool,
    pub elapsed_ms: f64,
    pub method: String,
}
fn quota(pos: u64) -> usize {
    match pos {
        1 => 2,
        2 | 3 => 5,
        4 => 3,
        _ => 0,
    }
}
fn points(p: &Player, k: usize) -> f64 {
    p.weeks.get(k).map(|w| w.points).unwrap_or(0.)
}
pub fn validate(players: &[Player], squad: &[u64]) -> Result<(), String> {
    if squad.len() != 15 || squad.iter().collect::<HashSet<_>>().len() != 15 {
        return Err("Select 15 distinct players".into());
    }
    let selected: Vec<_> = squad
        .iter()
        .map(|i| {
            players
                .iter()
                .find(|p| p.id == *i)
                .ok_or_else(|| format!("Unknown player {i}"))
        })
        .collect::<Result<_, _>>()?;
    for pos in 1..=4 {
        if selected.iter().filter(|p| p.position == pos).count() != quota(pos) {
            return Err("Squad needs 2 GKs, 5 defenders, 5 midfielders and 3 forwards".into());
        }
    }
    let mut clubs = HashMap::new();
    for p in selected {
        *clubs.entry(p.team).or_insert(0) += 1;
    }
    if clubs.values().any(|n| *n > 3) {
        return Err("Maximum three players per club".into());
    }
    Ok(())
}
pub fn lineup(
    players: &[Player],
    squad: &[u64],
    horizon: usize,
    chip: Option<&str>,
    risk_mode: RiskMode,
) -> Result<Vec<WeekPlan>, String> {
    validate(players, squad)?;
    let pool: Vec<_> = players.iter().filter(|p| squad.contains(&p.id)).collect();
    let mut weeks = Vec::new();
    for k in 0..horizon {
        let mut groups: Vec<Vec<&Player>> = (1..=4)
            .map(|pos| pool.iter().copied().filter(|p| p.position == pos).collect())
            .collect();
        for group in &mut groups {
            group.sort_by(|a, b| {
                utility(b, k, risk_mode)
                    .total_cmp(&utility(a, k, risk_mode))
                    .then(a.id.cmp(&b.id))
            });
        }
        let mut best: Option<WeekPlan> = None;
        for d in 3..=5 {
            for m in 2..=5 {
                let f = 10 - d - m;
                if !(1..=3).contains(&f) {
                    continue;
                }
                let mut xi = vec![groups[0][0]];
                xi.extend(groups[1].iter().take(d));
                xi.extend(groups[2].iter().take(m));
                xi.extend(groups[3].iter().take(f));
                let mut ranked = xi.clone();
                ranked.sort_by(|a, b| {
                    utility(b, k, risk_mode)
                        .total_cmp(&utility(a, k, risk_mode))
                        .then(a.id.cmp(&b.id))
                });
                let cap = ranked[0].id;
                let vice = ranked[1].id;
                let mut bench: Vec<_> = pool
                    .iter()
                    .copied()
                    .filter(|p| !xi.iter().any(|x| x.id == p.id))
                    .collect();
                bench.sort_by(|a, b| {
                    (a.position != 1)
                        .cmp(&(b.position != 1))
                        .then(utility(b, k, risk_mode).total_cmp(&utility(a, k, risk_mode)))
                        .then(a.id.cmp(&b.id))
                });
                let sum: f64 = if k == 0 && chip == Some("bboost") {
                    pool.iter().map(|p| points(p, k)).sum()
                } else {
                    xi.iter().map(|p| points(p, k)).sum()
                };
                let expected = sum
                    + points(ranked[0], k)
                        * if k == 0 && chip == Some("3xc") {
                            2.
                        } else {
                            1.
                        };
                let chosen = if k == 0 && chip == Some("bboost") {
                    &pool
                } else {
                    &xi
                };
                let score = chosen.iter().map(|p| utility(p, k, risk_mode)).sum::<f64>()
                    + utility(ranked[0], k, risk_mode)
                        * if k == 0 && chip == Some("3xc") {
                            2.
                        } else {
                            1.
                        };
                if best.as_ref().is_none_or(|b| score > b.selection_score) {
                    best = Some(WeekPlan {
                        event: pool[0].weeks.get(k).ok_or("No upcoming gameweek")?.event,
                        xi: xi.iter().map(|p| p.id).collect(),
                        bench: bench.iter().map(|p| p.id).collect(),
                        captain: cap,
                        vice_captain: vice,
                        points: expected,
                        selection_score: score,
                    });
                }
            }
        }
        weeks.push(best.ok_or("No valid starting formation")?);
    }
    Ok(weeks)
}
fn check_request(data: &DataSet, r: &Request) -> Result<(), String> {
    data.check_rules(r.horizon)?;
    if r.horizon == 0 || r.horizon > 8 || r.horizon > data.events.len() {
        return Err("Choose an available 1–8 gameweek horizon".into());
    }
    if r.free_transfers > 5 || r.max_transfers > 20 || r.bank > 10000 {
        return Err("Invalid bank or transfer limits".into());
    }
    if r.locked.len() > 15 || r.locked.iter().any(|i| r.excluded.contains(i)) {
        return Err("Conflicting player locks and exclusions".into());
    }
    for i in r.locked.iter().chain(r.excluded.iter()) {
        if !data.players.iter().any(|p| p.id == *i) {
            return Err("Unknown locked/excluded player".into());
        }
    }
    if !r.owned.is_empty() {
        validate(&data.players, &r.owned)?;
        if (r.max_transfers > 0 || matches!(r.chip.as_deref(), Some("wildcard" | "freehit")))
            && (r.sale_prices.len() != 15 || r.owned.iter().any(|i| !r.sale_prices.contains_key(i)))
        {
            return Err("Confirm selling prices for all 15 players".into());
        }
        for (i, sale) in &r.sale_prices {
            if *sale
                > data
                    .players
                    .iter()
                    .find(|p| p.id == *i)
                    .ok_or("Unknown selling price")?
                    .cost
            {
                return Err("Selling price exceeds the market price".into());
            }
        }
    }
    if let Some(chip) = r.chip.as_deref() {
        if r.owned.is_empty() {
            return Err("Chips require an existing confirmed squad".into());
        }
        let event = data.events[0].id;
        let allowed = data.bootstrap["chips"].as_array().is_some_and(|chips| {
            chips.iter().any(|c| {
                c["name"].as_str() == Some(chip)
                    && r.available_chip_ids.contains(&id(&c["id"]))
                    && id(&c["start_event"]) <= event
                    && event <= id(&c["stop_event"])
            })
        });
        if !allowed || (chip == "freehit" && r.previous_chip.as_deref() == Some("freehit")) {
            return Err("Chip is not confirmed available in this gameweek".into());
        }
    }
    Ok(())
}
pub fn solve(data: &DataSet, r: &Request) -> Result<Plan, String> {
    let start = Instant::now();
    check_request(data, r)?;
    let chip = r.chip.as_deref();
    let transfer_chip = matches!(chip, Some("wildcard" | "freehit"));
    if chip == Some("freehit") && r.horizon > 1 {
        if r.owned.is_empty() {
            return Err("Free Hit needs an existing squad to revert to".into());
        }
        let mut first = r.clone();
        first.horizon = 1;
        let mut plan = solve(data, &first)?;
        let original = lineup(&data.players, &r.owned, r.horizon, None, r.risk_mode)?;
        plan.weeks.extend(original.into_iter().skip(1));
        plan.expected_points = plan.weeks.iter().map(|w| w.points).sum();
        plan.selection_score = plan.weeks.iter().map(|w| w.selection_score).sum();
        plan.bank = r.bank;
        plan.elapsed_ms = start.elapsed().as_secs_f64() * 1000.;
        plan.method.push_str(" Free Hit lasts for the first gameweek only; later lineups revert to the original squad and bank.");
        return Ok(plan);
    }
    if !r.owned.is_empty() && r.max_transfers == 0 && !transfer_chip {
        if r.locked.iter().any(|i| !r.owned.contains(i))
            || r.excluded.iter().any(|i| r.owned.contains(i))
        {
            return Err("Locks conflict with a fixed squad".into());
        }
        let weeks = lineup(&data.players, &r.owned, r.horizon, chip, r.risk_mode)?;
        return Ok(Plan {
            squad: r.owned.clone(),
            expected_points: weeks.iter().map(|w| w.points).sum(),
            selection_score: weeks.iter().map(|w| w.selection_score).sum(),
            risk_mode: r.risk_mode,
            weeks,
            transfers_in: vec![],
            transfers_out: vec![],
            bank: r.bank,
            hit: 0,
            optimal: true,
            elapsed_ms: start.elapsed().as_secs_f64() * 1000.,
            method: "Exact native formation enumeration for your fixed squad".into(),
        });
    }
    let effective = |p: &Player| {
        if r.owned.contains(&p.id) {
            r.sale_prices.get(&p.id).copied().unwrap_or(p.cost)
        } else {
            p.cost
        }
    };
    // Safe dominance reduction: a club may supply at most three players. A fourth
    // same-position player dominated in price and every week is never necessary.
    let usable: Vec<&Player> = data
        .players
        .iter()
        .filter(|p| (!r.excluded.contains(&p.id)) && (p.purchasable || r.owned.contains(&p.id)))
        .collect();
    let pool: Vec<&Player> = usable
        .iter()
        .copied()
        .filter(|p| {
            r.locked.contains(&p.id)
                || r.owned.contains(&p.id)
                || usable
                    .iter()
                    .filter(|q| {
                        q.id != p.id
                            && q.team == p.team
                            && q.position == p.position
                            && effective(q) <= effective(p)
                            && (0..r.horizon)
                                .all(|k| utility(q, k, r.risk_mode) >= utility(p, k, r.risk_mode))
                            && (effective(q) < effective(p)
                                || (0..r.horizon).any(|k| {
                                    utility(q, k, r.risk_mode) > utility(p, k, r.risk_mode)
                                })
                                || q.id < p.id)
                    })
                    .take(3)
                    .count()
                    < 3
        })
        .collect();
    if r.locked.iter().any(|i| !pool.iter().any(|p| p.id == *i)) {
        return Err("A locked player is unavailable for purchase".into());
    }
    let mut seed = r.owned.clone();
    if seed.is_empty() {
        let mut clubs = HashMap::new();
        for pos in [1, 4, 2, 3] {
            let mut group: Vec<_> = pool.iter().copied().filter(|p| p.position == pos).collect();
            group.sort_by_key(|p| p.cost);
            for p in group {
                if seed
                    .iter()
                    .filter(|i| pool.iter().any(|p| p.id == **i && p.position == pos))
                    .count()
                    >= quota(pos)
                {
                    break;
                }
                if *clubs.get(&p.team).unwrap_or(&0) < 3 {
                    seed.push(p.id);
                    *clubs.entry(p.team).or_insert(0) += 1;
                }
            }
        }
    }
    let seed_ok = validate(&data.players, &seed).is_ok()
        && r.locked.iter().all(|i| seed.contains(i))
        && r.excluded.iter().all(|i| !seed.contains(i))
        && seed
            .iter()
            .filter_map(|i| pool.iter().find(|p| p.id == *i))
            .map(|p| effective(p))
            .sum::<u64>()
            <= if r.owned.is_empty() {
                1000
            } else {
                r.bank + r.sale_prices.values().sum::<u64>()
            };
    let mut vars = variables!();
    let xs: Vec<_> = pool.iter().map(|_| vars.add(variable().binary())).collect();
    let ys: Vec<Vec<_>> = (0..r.horizon)
        .map(|_| pool.iter().map(|_| vars.add(variable().binary())).collect())
        .collect();
    let cs: Vec<Vec<_>> = (0..r.horizon)
        .map(|_| pool.iter().map(|_| vars.add(variable().binary())).collect())
        .collect();
    let paid = vars.add(variable().integer().min(0).max(15));
    let mut objective = -4. * paid;
    for k in 0..r.horizon {
        for (i, p) in pool.iter().enumerate() {
            objective += utility(p, k, r.risk_mode)
                * (if k == 0 && chip == Some("bboost") {
                    xs[i]
                } else {
                    ys[k][i]
                });
            objective += utility(p, k, r.risk_mode)
                * if k == 0 && chip == Some("3xc") {
                    2.
                } else {
                    1.
                }
                * cs[k][i];
        }
    }
    let mut problem = vars
        .maximise(objective)
        .using(microlp)
        .with_time_limit(10.0);
    let all: Expression = xs.iter().copied().sum();
    problem = problem.with(all.eq(15));
    for pos in 1..=4 {
        let total: Expression = pool
            .iter()
            .enumerate()
            .filter(|(_, p)| p.position == pos)
            .map(|(i, _)| xs[i])
            .sum();
        problem = problem.with(total.eq(quota(pos) as f64));
    }
    for team in pool.iter().map(|p| p.team).collect::<HashSet<_>>() {
        let total: Expression = pool
            .iter()
            .enumerate()
            .filter(|(_, p)| p.team == team)
            .map(|(i, _)| xs[i])
            .sum();
        problem = problem.with(total.leq(3));
    }
    for (i, p) in pool.iter().enumerate() {
        if r.locked.contains(&p.id) {
            problem = problem.with(Expression::from(xs[i]).eq(1));
        }
    }
    let spend: Expression = pool
        .iter()
        .enumerate()
        .map(|(i, p)| effective(p) as f64 * xs[i])
        .sum();
    problem = problem.with(spend.leq(if r.owned.is_empty() {
        1000.
    } else {
        (r.bank + r.sale_prices.values().sum::<u64>()) as f64
    }));
    if r.owned.is_empty() || transfer_chip {
        problem = problem.with(Expression::from(paid).eq(0));
    } else {
        let retained: Expression = pool
            .iter()
            .enumerate()
            .filter(|(_, p)| r.owned.contains(&p.id))
            .map(|(i, _)| xs[i])
            .sum();
        problem = problem.with(retained.clone().geq((15 - r.max_transfers.min(15)) as f64));
        problem = problem.with((paid + retained).geq(15. - r.free_transfers as f64));
    }
    for k in 0..r.horizon {
        problem = problem
            .with(ys[k].iter().copied().sum::<Expression>().eq(11))
            .with(cs[k].iter().copied().sum::<Expression>().eq(1));
        for i in 0..pool.len() {
            problem = problem
                .with((ys[k][i] - xs[i]).leq(0))
                .with((cs[k][i] - ys[k][i]).leq(0));
        }
        for (pos, min, max) in [(1, 1, 1), (2, 3, 5), (3, 2, 5), (4, 1, 3)] {
            let n: Expression = pool
                .iter()
                .enumerate()
                .filter(|(_, p)| p.position == pos)
                .map(|(i, _)| ys[k][i])
                .sum();
            problem = problem.with(n.clone().geq(min)).with(n.leq(max));
        }
    }
    if seed_ok {
        let seed_weeks = lineup(&data.players, &seed, r.horizon, chip, r.risk_mode)?;
        let mut initial = vec![(paid, 0.)];
        for (i, p) in pool.iter().enumerate() {
            initial.push((xs[i], if seed.contains(&p.id) { 1. } else { 0. }));
            for k in 0..r.horizon {
                initial.push((
                    ys[k][i],
                    if seed_weeks[k].xi.contains(&p.id) {
                        1.
                    } else {
                        0.
                    },
                ));
                initial.push((
                    cs[k][i],
                    if seed_weeks[k].captain == p.id {
                        1.
                    } else {
                        0.
                    },
                ));
            }
        }
        problem = problem.with_initial_solution(initial);
    }
    let solution=problem.solve().map_err(|e|format!("No feasible squad within the native solve limit: {e}. Try a shorter horizon or adjust locks."))?;
    let squad: Vec<_> = pool
        .iter()
        .enumerate()
        .filter(|(i, _)| solution.value(xs[*i]) > 0.5)
        .map(|(_, p)| p.id)
        .collect();
    validate(&data.players, &squad)?;
    let weeks = lineup(&data.players, &squad, r.horizon, chip, r.risk_mode)?;
    let ins: Vec<_> = if r.owned.is_empty() {
        vec![]
    } else {
        squad
            .iter()
            .copied()
            .filter(|i| !r.owned.contains(i))
            .collect()
    };
    let outs: Vec<_> = r
        .owned
        .iter()
        .copied()
        .filter(|i| !squad.contains(i))
        .collect();
    let hit = if transfer_chip || r.owned.is_empty() {
        0
    } else {
        ins.len().saturating_sub(r.free_transfers as usize) as u64 * 4
    };
    let bank = if r.owned.is_empty() {
        1000 - squad
            .iter()
            .map(|i| data.players.iter().find(|p| p.id == *i).unwrap().cost)
            .sum::<u64>()
    } else {
        r.bank + outs.iter().map(|i| r.sale_prices[i]).sum::<u64>()
            - ins
                .iter()
                .map(|i| data.players.iter().find(|p| p.id == *i).unwrap().cost)
                .sum::<u64>()
    };
    Ok(Plan{selection_score:weeks.iter().map(|w|w.selection_score).sum::<f64>()-hit as f64,risk_mode:r.risk_mode,squad,weeks:weeks.clone(),expected_points:weeks.iter().map(|w|w.points).sum::<f64>()-hit as f64,transfers_in:ins,transfers_out:outs,bank,hit,optimal:matches!(solution.status(),SolutionStatus::Optimal),elapsed_ms:start.elapsed().as_secs_f64()*1000.,method:"Native Rust MILP: fixed squad over the horizon; selected risk utility, weekly XI and captain. Reported expected points remain the model mean. Bench and vice ranked by selected risk utility; no autosub expectation. A time-limited feasible plan is labeled rather than claimed optimal.".into()})
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{Event, Week};
    use serde_json::json;
    fn sample() -> DataSet {
        let mut players = Vec::new();
        for (pos, count) in [(1, 4), (2, 10), (3, 10), (4, 6)] {
            for _ in 0..count {
                let i = players.len() as u64 + 1;
                players.push(Player {
                    id: i,
                    name: format!("Test {i}"),
                    full_name: String::new(),
                    position: pos,
                    club: format!("C{}", i % 10),
                    team: i % 10 + 1,
                    cost: 50,
                    ownership: 10.,
                    status: "a".into(),
                    news: String::new(),
                    form: 3.,
                    actual_points: 10.,
                    expected_points: (i * 7 % 13) as f64,
                    expected_minutes: 80.,
                    probabilities: BTreeMap::new(),
                    weeks: vec![
                        Week {
                            event: 11,
                            points: (i * 7 % 13) as f64,
                            fixtures: vec![],
                        },
                        Week {
                            event: 12,
                            points: (i * 3 % 11) as f64,
                            fixtures: vec![],
                        },
                    ],
                    history_samples: 5,
                    purchasable: true,
                    last_points: vec![],
                    risk_history: vec![],
                });
            }
        }
        DataSet {
            players,
            events: vec![
                Event {
                    id: 11,
                    deadline: "2030-01-01T00:00:00Z".into(),
                    name: "GW11".into(),
                },
                Event {
                    id: 12,
                    deadline: "2030-01-08T00:00:00Z".into(),
                    name: "GW12".into(),
                },
            ],
            bootstrap: json!({"game_config":{"settings":{"static_content_url":"https://example.test/2026_27/"}},"events":[],"chips":[{"id":1,"name":"freehit","start_event":1,"stop_event":19}]}),
            fixtures: vec![],
            snapshot_at: String::new(),
            model_version: String::new(),
            report: json!({}),
            compute_ms: 0.,
        }
    }
    #[test]
    fn playing_style_changes_captain_but_never_inflates_points() {
        let mut data = sample();
        let base = solve(
            &data,
            &serde_json::from_value(json!({"horizon":1})).unwrap(),
        )
        .unwrap();
        for p in &mut data.players {
            p.weeks[0].points = 5.;
            p.expected_minutes = 90.;
            p.risk_history = vec![5.; 10];
        }
        let steady = base.squad[0];
        let volatile = base.squad[1];
        data.players
            .iter_mut()
            .find(|p| p.id == volatile)
            .unwrap()
            .risk_history = vec![0., 0., 0., 0., 0., 0., 0., 10., 15., 25.];
        data.players
            .iter_mut()
            .find(|p| p.id == steady)
            .unwrap()
            .weeks[0]
            .points = 5.1;
        let aggressive = lineup(&data.players, &base.squad, 1, None, RiskMode::Aggressive).unwrap();
        let conservative =
            lineup(&data.players, &base.squad, 1, None, RiskMode::Conservative).unwrap();
        assert_eq!(aggressive[0].captain, volatile);
        assert_eq!(conservative[0].captain, steady);
        assert!(aggressive[0].selection_score > aggressive[0].points);
        assert!(conservative[0].selection_score <= conservative[0].points);
        assert!(aggressive[0].points <= 60.2);
        for mode in ["aggressive", "balanced", "conservative"] {
            let request: Request =
                serde_json::from_value(json!({"horizon":2,"risk_mode":mode})).unwrap();
            let plan = solve(&data, &request).unwrap();
            validate(&data.players, &plan.squad).unwrap();
            assert!(plan.bank <= 1000);
            let expected = plan.weeks.iter().map(|w| w.points).sum::<f64>();
            assert!((plan.expected_points - expected).abs() < 1e-8);
            assert!(
                (plan.selection_score - plan.weeks.iter().map(|w| w.selection_score).sum::<f64>())
                    .abs()
                    < 1e-8
            );
        }
    }
    #[test]
    fn sparse_and_zero_minute_players_get_no_upside_bonus() {
        let mut p = sample().players.remove(0);
        p.risk_history = vec![0., 20.];
        assert_eq!(utility(&p, 0, RiskMode::Aggressive), points(&p, 0));
        p.risk_history = vec![0., 0., 0., 20., 20.];
        p.expected_minutes = 0.;
        assert_eq!(utility(&p, 0, RiskMode::Aggressive), points(&p, 0));
        assert!(serde_json::from_value::<Request>(json!({"risk_mode":"extreme"})).is_err());
    }
    #[test]
    fn native_squad_and_lineup_constraints() {
        let data = sample();
        let r: Request = serde_json::from_value(json!({"horizon":2})).unwrap();
        let plan = solve(&data, &r).unwrap();
        validate(&data.players, &plan.squad).unwrap();
        assert!(plan.bank <= 1000);
        assert_eq!(plan.weeks.len(), 2);
        for w in plan.weeks {
            assert_eq!(w.xi.len(), 11);
            assert_eq!(w.bench.len(), 4);
            assert!(w.xi.contains(&w.captain));
            assert_ne!(w.captain, w.vice_captain);
            assert!(w.bench.iter().all(|i| !w.xi.contains(i)));
        }
    }
    #[test]
    fn fixed_team_does_not_require_finances() {
        let data = sample();
        let initial = solve(
            &data,
            &serde_json::from_value(json!({"horizon":1})).unwrap(),
        )
        .unwrap();
        let fixed: Request =
            serde_json::from_value(json!({"horizon":2,"owned":initial.squad,"max_transfers":0}))
                .unwrap();
        let plan = solve(&data, &fixed).unwrap();
        assert!(plan.optimal);
        assert!(plan.transfers_in.is_empty());
        assert_eq!(plan.hit, 0);
    }
    #[test]
    fn transfer_prices_required() {
        let data = sample();
        let initial = solve(
            &data,
            &serde_json::from_value(json!({"horizon":1})).unwrap(),
        )
        .unwrap();
        let request =
            serde_json::from_value(json!({"horizon":1,"owned":initial.squad,"max_transfers":1}))
                .unwrap();
        assert!(
            solve(&data, &request)
                .unwrap_err()
                .contains("selling prices")
        );
    }
    #[test]
    fn club_and_duplicate_rejection() {
        let data = sample();
        assert!(validate(&data.players, &[1; 15]).is_err());
    }
    #[test]
    fn transfers_and_hits() {
        let data = sample();
        let original = solve(
            &data,
            &serde_json::from_value(json!({"horizon":1})).unwrap(),
        )
        .unwrap();
        let sales: BTreeMap<_, _> = original.squad.iter().map(|i| (*i, 50)).collect();
        let r=serde_json::from_value(json!({"horizon":2,"owned":original.squad,"sale_prices":sales,"max_transfers":1,"free_transfers":0,"bank":0})).unwrap();
        let plan = solve(&data, &r).unwrap();
        assert!(plan.transfers_in.len() <= 1);
        assert_eq!(plan.hit, plan.transfers_in.len() as u64 * 4);
    }
    #[test]
    fn season_guard() {
        let mut data = sample();
        data.bootstrap["game_config"]["settings"]["static_content_url"] =
            json!("https://example.test/2027_28/");
        assert!(
            solve(
                &data,
                &serde_json::from_value(json!({"horizon":1})).unwrap()
            )
            .unwrap_err()
            .contains("Season rules")
        );
    }
    #[test]
    fn freehit_reverts_after_first_week() {
        let data = sample();
        let original = solve(
            &data,
            &serde_json::from_value(json!({"horizon":1})).unwrap(),
        )
        .unwrap();
        let sales: BTreeMap<_, _> = original.squad.iter().map(|i| (*i, 50)).collect();
        let r=serde_json::from_value(json!({"horizon":2,"owned":original.squad,"sale_prices":sales,"chip":"freehit","available_chip_ids":[1],"bank":0})).unwrap();
        let plan = solve(&data, &r).unwrap();
        assert!(plan.weeks[1].xi.iter().all(|i| original.squad.contains(i)));
        assert_eq!(plan.bank, 0);
        assert!(plan.method.contains("revert"));
    }
    #[test]
    fn new_team_cannot_use_fake_selling_prices() {
        let mut data = sample();
        for player in &mut data.players {
            player.cost = 80;
        }
        let sales: BTreeMap<_, _> = data.players.iter().map(|p| (p.id, 0)).collect();
        let request: Request =
            serde_json::from_value(json!({"horizon":1,"sale_prices":sales})).unwrap();
        assert!(solve(&data, &request).is_err());
    }
}
