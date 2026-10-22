//! 백엔드 접속 정보와 실행. 규약: docs/backend-protocol.md
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

#[derive(serde::Serialize, serde::Deserialize, Debug, PartialEq)]
pub struct Endpoint {
    pub port: u16,
    pub token: String,
}

/// 이 앱이 띄운 백엔드 프로세스. 앱을 끌 때 함께 끈다 (다른 곳에서 띄운 백엔드는 건드리지 않는다)
pub struct BackendProcess(pub Mutex<Option<Child>>);

pub fn parse_endpoint(s: &str) -> Result<Endpoint, String> {
    serde_json::from_str(s).map_err(|e| e.to_string())
}

/// 백엔드가 시작할 때 쓰는 접속 정보 파일. 경로는 백엔드의 config.data_dir()와 같다
pub fn endpoint() -> Result<Endpoint, String> {
    let appdata = std::env::var_os("APPDATA").ok_or("APPDATA 환경 변수가 없습니다")?;
    let path = PathBuf::from(appdata).join("TamagotchiChatBot").join("backend").join("backend.json");
    parse_endpoint(&std::fs::read_to_string(path).map_err(|e| e.to_string())?)
}

/// 개발 환경: 저장소 backend/의 가상환경 파이썬으로 띄운다. 배포용 묶음은 아직 범위 밖
pub fn ensure_running(state: &BackendProcess) -> Result<(), String> {
    let mut slot = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(child) = slot.as_mut() {
        if child.try_wait().map_err(|e| e.to_string())?.is_none() {
            return Ok(());
        }
    }
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("backend");
    let mut cmd = Command::new(dir.join(".venv").join("Scripts").join("python.exe"));
    cmd.args(["-m", "backend"]).current_dir(&dir);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: 콘솔 창을 띄우지 않는다
    }
    *slot = Some(cmd.spawn().map_err(|e| format!("백엔드 실행 실패: {e}"))?);
    Ok(())
}

/// taskkill 인자: 프로세스 트리째(/T) 강제로(/F) 끈다
pub fn kill_tree_args(pid: u32) -> Vec<String> {
    vec!["/PID".into(), pid.to_string(), "/T".into(), "/F".into()]
}

/// 백엔드가 띄운 screenpipe·Claude Code까지 남지 않게 프로세스 트리째 끈다 (백엔드 계획 Ruling 13)
pub fn stop(state: &BackendProcess) {
    let Ok(mut slot) = state.0.lock() else { return };
    let Some(mut child) = slot.take() else { return };
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let killed = Command::new("taskkill")
            .args(kill_tree_args(child.id()))
            .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
            .status();
        if !matches!(killed, Ok(s) if s.success()) {
            let _ = child.kill();
        }
    }
    #[cfg(not(windows))]
    let _ = child.kill();
    let _ = child.wait();
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
    fn kill_tree_args_kills_whole_tree_by_force() {
        assert_eq!(kill_tree_args(1234), ["/PID", "1234", "/T", "/F"]);
    }

    #[test]
    fn rejects_missing_token() {
        assert!(parse_endpoint(r#"{"port": 1}"#).is_err());
    }
}
