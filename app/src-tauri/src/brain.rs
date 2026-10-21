//! 파이썬 서비스 접속 정보와 실행. 규약: docs/brain-protocol.md
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

#[derive(serde::Serialize, serde::Deserialize, Debug, PartialEq)]
pub struct Endpoint {
    pub port: u16,
    pub token: String,
}

/// 이 앱이 띄운 파이썬 서비스 프로세스. 앱을 끌 때 함께 끈다 (다른 곳에서 띄운 파이썬 서비스는 건드리지 않는다)
pub struct BrainProcess(pub Mutex<Option<Child>>);

pub fn parse_endpoint(s: &str) -> Result<Endpoint, String> {
    serde_json::from_str(s).map_err(|e| e.to_string())
}

/// 파이썬 서비스가 시작할 때 쓰는 접속 정보 파일. 경로는 파이썬 서비스의 config.data_dir()와 같다
pub fn endpoint() -> Result<Endpoint, String> {
    let appdata = std::env::var_os("APPDATA").ok_or("APPDATA 환경 변수가 없습니다")?;
    let path = PathBuf::from(appdata).join("TamagotchiChatBot").join("brain").join("brain.json");
    parse_endpoint(&std::fs::read_to_string(path).map_err(|e| e.to_string())?)
}

/// 개발 환경: 저장소 brain/의 가상환경 파이썬으로 띄운다. 배포용 묶음은 아직 범위 밖
pub fn ensure_running(state: &BrainProcess) -> Result<(), String> {
    let mut slot = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(child) = slot.as_mut() {
        if child.try_wait().map_err(|e| e.to_string())?.is_none() {
            return Ok(());
        }
    }
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("brain");
    let mut cmd = Command::new(dir.join(".venv").join("Scripts").join("python.exe"));
    cmd.args(["-m", "brain"]).current_dir(&dir);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: 콘솔 창을 띄우지 않는다
    }
    *slot = Some(cmd.spawn().map_err(|e| format!("파이썬 서비스 실행 실패: {e}"))?);
    Ok(())
}

pub fn stop(state: &BrainProcess) {
    if let Ok(mut slot) = state.0.lock() {
        if let Some(mut child) = slot.take() {
            let _ = child.kill();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_endpoint_and_ignores_extra_fields() {
        let e = parse_endpoint(r#"{"port": 50123, "token": "abc", "pid": 42}"#).unwrap();
        assert_eq!(e, Endpoint { port: 50123, token: "abc".into() });
    }

    #[test]
    fn rejects_missing_token() {
        assert!(parse_endpoint(r#"{"port": 1}"#).is_err());
    }
}
