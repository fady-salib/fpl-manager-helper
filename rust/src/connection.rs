//! Explicit local browser pairing. Never receives an FPL cookie or password.
use super::*;
use std::collections::HashMap;

pub struct Pairing {
    token: String,
    created: Instant,
    purpose: Purpose,
    result: Option<Value>,
    in_progress: bool,
}
enum Purpose {
    Verify {
        name: String,
        manager: String,
        desktop: bool,
    },
    SellingPrices {
        reference: u64,
    },
}
#[derive(Deserialize)]
pub struct Names {
    name: String,
    manager: String,
    known_entry_id: Option<u64>,
    #[serde(default)]
    desktop: bool,
}
#[derive(Deserialize)]
pub struct Token {
    token: String,
}
#[derive(Deserialize)]
pub struct Reference {
    reference: u64,
}
#[derive(Deserialize)]
pub struct Complete {
    token: String,
    reference: u64,
    sale_prices: Option<BTreeMap<u64, u64>>,
    bank: Option<u64>,
    free_transfers: Option<u64>,
}
fn key(name: &str, manager: &str) -> String {
    format!(
        "{}\n{}",
        team_search::normalise(name),
        team_search::normalise(manager)
    )
}
fn verified(entry: &Value, reference: u64, name: &str, manager: &str) -> Result<Value, String> {
    let c = team_search::saved_candidate(entry, reference, name)
        .ok_or("The signed-in FPL team name does not match. Check both names and try again.")?;
    if team_search::normalise(&c.manager) != team_search::normalise(manager) {
        return Err("The manager name does not match the signed-in account. Enter the full manager name shown on FPL.".into());
    }
    Ok(
        json!({"reference":c.reference,"name":c.name,"manager":c.manager,"rank":c.rank,"exact":true}),
    )
}
fn registry(app: &App) -> HashMap<String, u64> {
    std::fs::read(app.root.join("data/account-connections.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default()
}
pub async fn start(
    State(app): State<App>,
    headers: HeaderMap,
    Json(names): Json<Names>,
) -> ApiResult {
    origin(&app, &headers)?;
    let name =
        team_search::validate_name(&names.name).map_err(|e| fail(StatusCode::BAD_REQUEST, e))?;
    let manager = team_search::validate_name(&names.manager).map_err(|_| {
        fail(
            StatusCode::BAD_REQUEST,
            "Enter your full FPL manager name (1–80 characters).",
        )
    })?;
    if names.desktop {
        return create_pairing(
            &app,
            Purpose::Verify {
                name,
                manager,
                desktop: true,
            },
        );
    }
    let known = names
        .known_entry_id
        .or_else(|| registry(&app).get(&key(&name, &manager)).copied());
    if let Some(reference) = known.filter(|i| (1..=1_000_000_000).contains(i))
        && let Ok(entry) = app.fetch(&format!("entry/{reference}/")).await
        && let Ok(candidate) = verified(&entry, reference, &name, &manager)
    {
        return Ok(Json(json!({"candidate":candidate})));
    }
    create_pairing(
        &app,
        Purpose::Verify {
            name,
            manager,
            desktop: false,
        },
    )
}
pub async fn start_prices(
    State(app): State<App>,
    headers: HeaderMap,
    Json(request): Json<Reference>,
) -> ApiResult {
    origin(&app, &headers)?;
    if !(1..=1_000_000_000).contains(&request.reference) {
        return Err(fail(StatusCode::BAD_REQUEST, "Connect your FPL team first"));
    }
    create_pairing(
        &app,
        Purpose::SellingPrices {
            reference: request.reference,
        },
    )
}

fn create_pairing(app: &App, purpose: Purpose) -> ApiResult {
    let page = match purpose {
        Purpose::Verify { desktop: false, .. } => "/",
        Purpose::Verify { desktop: true, .. } => "/transfers",
        Purpose::SellingPrices { .. } => "/transfers",
    };
    let prices = matches!(purpose, Purpose::SellingPrices { .. });
    let mut bytes = [0u8; 32];
    getrandom::getrandom(&mut bytes).map_err(|_| {
        fail(
            StatusCode::INTERNAL_SERVER_ERROR,
            "Could not create a secure pairing token",
        )
    })?;
    let token = bytes.iter().map(|b| format!("{b:02x}")).collect::<String>();
    *app.pairing.lock().unwrap() = Some(Pairing {
        token: token.clone(),
        created: Instant::now(),
        purpose,
        result: None,
        in_progress: false,
    });
    Ok(Json(
        json!({"token":token,"url":format!("https://fantasy.premierleague.com{page}#fpl-local={token}&port={}&prices={}",app.port,u8::from(prices)),"expires_seconds":300}),
    ))
}
pub async fn status(
    State(app): State<App>,
    headers: HeaderMap,
    Json(request): Json<Token>,
) -> ApiResult {
    origin(&app, &headers)?;
    let guard = app.pairing.lock().unwrap();
    let pair = guard
        .as_ref()
        .filter(|p| p.token == request.token && p.created.elapsed() < Duration::from_secs(300))
        .ok_or_else(|| {
            fail(
                StatusCode::GONE,
                "Connection expired or replaced. Click Connect again.",
            )
        })?;
    let waiting = pair.result.is_none();
    Ok(Json(match pair.purpose {
        Purpose::Verify { desktop: true, .. } => json!({"account":pair.result,"waiting":waiting}),
        Purpose::Verify { desktop: false, .. } => {
            json!({"candidate":pair.result,"waiting":waiting})
        }
        Purpose::SellingPrices { .. } => json!({"sale_prices":pair.result,"waiting":waiting}),
    }))
}
fn validate_prices(
    prices: Option<BTreeMap<u64, u64>>,
) -> Result<BTreeMap<u64, u64>, (StatusCode, Json<Value>)> {
    prices
        .filter(|prices| {
            prices.len() == 15
                && prices
                    .iter()
                    .all(|(&id, &price)| id > 0 && (1..=1000).contains(&price))
        })
        .ok_or_else(|| {
            fail(
                StatusCode::BAD_REQUEST,
                "FPL did not return 15 valid selling prices",
            )
        })
}

pub async fn complete(State(app): State<App>, Json(request): Json<Complete>) -> ApiResult {
    // A 256-bit, five-minute, one-use token is required. No browser CORS grants.
    if !(1..=1_000_000_000).contains(&request.reference) {
        return Err(fail(StatusCode::BAD_REQUEST, "Invalid account reference"));
    }
    let (name, manager, desktop_prices) = {
        let mut guard = app.pairing.lock().unwrap();
        let p = guard
            .as_mut()
            .filter(|p| {
                p.token == request.token
                    && p.created.elapsed() < Duration::from_secs(300)
                    && p.result.is_none()
                    && !p.in_progress
            })
            .ok_or_else(|| {
                fail(
                    StatusCode::FORBIDDEN,
                    "Invalid, expired or already used pairing token",
                )
            })?;
        match &p.purpose {
            Purpose::Verify {
                name,
                manager,
                desktop,
            } => {
                if !desktop && request.sale_prices.is_some() {
                    return Err(fail(
                        StatusCode::BAD_REQUEST,
                        "Start a selling-price import first",
                    ));
                }
                let prices = if *desktop {
                    if request.bank.is_some_and(|bank| bank > 10000)
                        || request.free_transfers.is_some_and(|free| free > 5)
                    {
                        return Err(fail(
                            StatusCode::BAD_REQUEST,
                            "FPL returned invalid transfer finances",
                        ));
                    }
                    Some(validate_prices(request.sale_prices)?)
                } else {
                    None
                };
                p.in_progress = true;
                (name.clone(), manager.clone(), prices)
            }
            Purpose::SellingPrices { reference } => {
                if *reference != request.reference {
                    return Err(fail(
                        StatusCode::CONFLICT,
                        "Sign in to the FPL account connected to this manager",
                    ));
                }
                let prices = validate_prices(request.sale_prices)?;
                p.result = Some(json!(prices));
                return Ok(Json(json!({"imported":true})));
            }
        }
    };
    let result = async {
        let entry = app.fetch(&format!("entry/{}/", request.reference)).await?;
        verified(&entry, request.reference, &name, &manager)
    }
    .await;
    let mut guard = app.pairing.lock().unwrap();
    let p = guard
        .as_mut()
        .filter(|p| p.token == request.token && p.created.elapsed() < Duration::from_secs(300))
        .ok_or_else(|| fail(StatusCode::GONE, "Connection was replaced or expired"))?;
    p.in_progress = false;
    let candidate = result.map_err(|e| fail(StatusCode::CONFLICT, e))?;
    // Fail visibly if remembering a connection fails; do not overwrite a corrupt registry.
    let path = app.root.join("data/account-connections.json");
    let mut saved: HashMap<String, u64> = if path.exists() {
        serde_json::from_slice(
            &std::fs::read(&path).map_err(|e| fail(StatusCode::INTERNAL_SERVER_ERROR, e))?,
        )
        .map_err(|_| {
            fail(
                StatusCode::CONFLICT,
                "Saved connections file is unreadable; preserve it and repair it before pairing.",
            )
        })?
    } else {
        HashMap::new()
    };
    saved.insert(key(&name, &manager), request.reference);
    std::fs::create_dir_all(app.root.join("data"))
        .map_err(|e| fail(StatusCode::INTERNAL_SERVER_ERROR, e))?;
    let temporary = path.with_extension("json.tmp");
    std::fs::write(&temporary, serde_json::to_vec_pretty(&saved).unwrap())
        .map_err(|e| fail(StatusCode::INTERNAL_SERVER_ERROR, e))?;
    // Windows rename cannot replace an existing file. Copy is guarded by the pairing mutex.
    std::fs::copy(&temporary, &path).map_err(|e| fail(StatusCode::INTERNAL_SERVER_ERROR, e))?;
    let _ = std::fs::remove_file(temporary);
    p.result = Some(match desktop_prices {
        Some(prices) => {
            json!({"candidate":candidate,"sale_prices":prices,"bank":request.bank,"free_transfers":request.free_transfers})
        }
        None => candidate,
    });
    Ok(Json(json!({"connected":true})))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn both_names_must_match() {
        let v = json!({"name":"My XI","player_first_name":"Alice","player_last_name":"Smith"});
        assert!(verified(&v, 10, " my xi ", "ALICE  Smith").is_ok());
        assert!(verified(&v, 10, "My XI", "Bob Smith").is_err());
        assert!(verified(&v, 10, "Other", "Alice Smith").is_err());
    }
    #[test]
    fn key_separates_names() {
        assert_ne!(key("ab", "c"), key("a", "bc"));
    }
}
