use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeMap, fs, path::Path};

#[derive(Clone, Deserialize, Serialize)]
pub struct Model {
    pub schema: u32,
    pub version: String,
    pub features: Vec<String>,
    pub metadata: Value,
    pub predictors: BTreeMap<String, Predictor>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Predictor {
    Baseline {
        index: usize,
    },
    Constant {
        value: f64,
    },
    Trees {
        imputer: Vec<f64>,
        trees: Vec<Tree>,
        average: bool,
        float32: bool,
    },
}
#[derive(Clone, Deserialize, Serialize)]
pub struct Tree {
    feature: Vec<i32>,
    threshold: Vec<f64>,
    left: Vec<i32>,
    right: Vec<i32>,
    value: Vec<f64>,
    missing_left: Vec<bool>,
}
impl Tree {
    fn predict(&self, x: &[f64]) -> f64 {
        let mut i = 0;
        while self.left[i] >= 0 {
            let v = x[self.feature[i] as usize];
            let left = if v.is_nan() {
                self.missing_left[i]
            } else {
                v <= self.threshold[i]
            };
            i = if left { self.left[i] } else { self.right[i] } as usize;
        }
        self.value[i]
    }
    fn valid(&self, features: usize) -> bool {
        let n = self.feature.len();
        n > 0
            && [
                self.threshold.len(),
                self.left.len(),
                self.right.len(),
                self.value.len(),
                self.missing_left.len(),
            ]
            .iter()
            .all(|s| *s == n)
            && (0..n).all(|i| {
                self.left[i] < 0
                    || (self.feature[i] >= 0
                        && (self.feature[i] as usize) < features
                        && (self.left[i] as usize) > i
                        && (self.left[i] as usize) < n
                        && self.right[i] >= 0
                        && (self.right[i] as usize) > i
                        && (self.right[i] as usize) < n)
            })
    }
}
impl Predictor {
    pub fn predict(&self, x: &[f64]) -> f64 {
        match self {
            Self::Baseline { index } => {
                if x[*index].is_finite() {
                    x[*index]
                } else {
                    0.
                }
            }
            Self::Constant { value } => *value,
            Self::Trees {
                imputer,
                trees,
                average,
                float32,
            } => {
                let values: Vec<_> = x
                    .iter()
                    .enumerate()
                    .map(|(i, v)| {
                        let value = if v.is_finite() { *v } else { imputer[i] };
                        if *float32 {
                            (value as f32) as f64
                        } else {
                            value
                        }
                    })
                    .collect();
                let total: f64 = trees.iter().map(|t| t.predict(&values)).sum();
                if *average {
                    total / trees.len() as f64
                } else {
                    total
                }
            }
        }
    }
}
impl Model {
    pub fn load(path: &Path) -> Result<Self, String> {
        let model: Self = serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        let expected: Vec<String> = [3, 5, 10]
            .into_iter()
            .flat_map(|w| {
                crate::data::STATS
                    .into_iter()
                    .map(move |s| format!("{s}_{w}"))
            })
            .chain(["total_points_avg".into(), "minutes_avg".into()])
            .collect();
        if model.schema != 1
            || model.features != expected
            || !model.predictors.contains_key("total_points")
            || !model.predictors.contains_key("minutes")
        {
            return Err("Unsupported native model schema".into());
        }
        for predictor in model.predictors.values() {
            let ok = match predictor {
                Predictor::Baseline { index } => *index < model.features.len(),
                Predictor::Constant { value } => value.is_finite(),
                Predictor::Trees { imputer, trees, .. } => {
                    imputer.len() == model.features.len()
                        && !trees.is_empty()
                        && trees.iter().all(|t| t.valid(model.features.len()))
                }
            };
            if !ok {
                return Err("Invalid native model tree arrays".into());
            }
        }
        Ok(model)
    }
    pub fn predict(&self, features: &[f64]) -> BTreeMap<String, f64> {
        self.predictors
            .iter()
            .map(|(key, p)| {
                let v = p.predict(features);
                (
                    key.clone(),
                    if key == "minutes" {
                        v.clamp(0., 90.)
                    } else if key == "total_points" {
                        v
                    } else {
                        v.clamp(0., 1.)
                    },
                )
            })
            .collect()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn baseline_handles_missing() {
        assert_eq!(Predictor::Baseline { index: 0 }.predict(&[f64::NAN]), 0.);
    }
    #[test]
    fn tree_traversal() {
        let t = Tree {
            feature: vec![0, -1, -1],
            threshold: vec![2., 0., 0.],
            left: vec![1, -1, -1],
            right: vec![2, -1, -1],
            value: vec![0., 3., 8.],
            missing_left: vec![true, false, false],
        };
        assert!(t.valid(1));
        assert_eq!(t.predict(&[1.]), 3.);
        assert_eq!(t.predict(&[3.]), 8.);
        assert_eq!(t.predict(&[f64::NAN]), 3.);
    }
}
