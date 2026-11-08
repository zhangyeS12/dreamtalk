use serde::{Deserialize, Serialize};
#[derive(Deserialize, Serialize)]
pub struct CallRequest { pub operation: String, pub payload: String }
