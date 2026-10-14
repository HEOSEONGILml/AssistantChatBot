const SERVICE: &str = "TamagotchiChatBot";
const ALLOWED: [&str; 2] = ["typesafe", "gemini"];

fn entry(name: &str) -> Result<keyring::Entry, String> {
    if !ALLOWED.contains(&name) { return Err(format!("unknown key name: {name}")); }
    keyring::Entry::new(SERVICE, name).map_err(|e| e.to_string())
}

pub fn set(name: &str, value: &str) -> Result<(), String> {
    if value.trim().is_empty() { return Err("빈 키는 저장하지 않습니다".into()); }
    entry(name)?.set_password(value.trim()).map_err(|e| e.to_string())
}

pub fn has(name: &str) -> Result<bool, String> {
    match entry(name)?.get_password() {
        Ok(_) => Ok(true),
        Err(keyring::Error::NoEntry) => Ok(false),
        Err(e) => Err(e.to_string()),
    }
}

pub fn delete(name: &str) -> Result<(), String> {
    match entry(name)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
