mod download;
use std::net::TcpListener;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct Backend {
    process: Mutex<Option<CommandChild>>,
    origin: String,
}

#[tauri::command]
fn backend_origin(state: tauri::State<'_, Backend>) -> String {
    state.origin.clone()
}

/// Wait for the sidecar to bind its actual dynamic port. Do not confuse
/// PyInstaller startup time with a Telegram logout; both Linux and Windows
/// can take several seconds to unpack the first time.
fn wait_for_origin(origin: &str, deadline: Duration) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .no_proxy()
        .connect_timeout(Duration::from_millis(850))
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|_| "Não foi possível iniciar a verificação local.".to_string())?;
    let start = Instant::now();
    loop {
        if let Ok(response) = client.get(format!("{origin}/api/health")).send() {
            if response.status().is_success() {
                return Ok(());
            }
        }
        if start.elapsed() >= deadline {
            return Err("O conector local não respondeu após 45 segundos. "
                .to_string()
                + "Sua sessão do Telegram permanece salva. "
                + "Verifique o arquivo backend-startup.log no diretório de dados do aplicativo.");
        }
        std::thread::sleep(Duration::from_millis(350));
    }
}

#[tauri::command]
async fn wait_backend_ready(state: tauri::State<'_, Backend>) -> Result<(), String> {
    let origin = state.origin.clone();
    tauri::async_runtime::spawn_blocking(move || {
        wait_for_origin(&origin, Duration::from_secs(45))
    })
    .await
    .map_err(|_| "A verificação do conector foi interrompida.".to_string())?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![backend_origin, wait_backend_ready, download::download_cloud_file])
        .setup(|app| {
            let data_dir = app.path().app_local_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;

            // Let the OS choose an unused loopback port, avoiding hard-coded
            // conflicts with existing services on the user's computer.
            let listener = TcpListener::bind(("127.0.0.1", 0))?;
            let port = listener.local_addr()?.port();
            drop(listener);

            let command = app
                .shell()
                .sidecar("drive-cloud-backend")?
                .env("DRIVE_CLOUD_DATA_DIR", data_dir.to_string_lossy().to_string())
                .env("DRIVE_CLOUD_BACKEND_PORT", port.to_string());
            let (_events, child) = command.spawn()?;
            app.manage(Backend {
                process: Mutex::new(Some(child)),
                origin: format!("http://127.0.0.1:{port}"),
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Falha ao iniciar o Drive Cloud");

    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(backend) = handle.try_state::<Backend>() {
                if let Ok(mut guard) = backend.process.lock() {
                    if let Some(mut child) = guard.take() {
                        // Uvicorn shuts down normally, awaiting Telegram session
                        // flush on Linux AND Windows. Force-kill only as fallback.
                        if child.write(b"drive-cloud:shutdown\n").is_ok() {
                            std::thread::sleep(Duration::from_millis(1700));
                        }
                        let _ = child.kill();
                    }
                }
            }
        }
    });
}

#[cfg(test)]
mod readiness_tests {
    use super::*;
    use std::io::{Read, Write};

    #[test]
    fn backend_ready_waits_for_health_on_dynamic_port() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let thread = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut input = [0u8; 1024];
            let _ = stream.read(&mut input);
            stream.write_all(
                b"HTTP/1.1 200 OK\r\nContent-Length: 14\r\nConnection: close\r\n\r\n{\"ready\":true}",
            ).unwrap();
        });
        let result = wait_for_origin(
            &format!("http://127.0.0.1:{port}"),
            Duration::from_secs(3),
        );
        thread.join().unwrap();
        assert!(result.is_ok(), "{result:?}");
    }

    #[test]
    fn backend_missing_returns_error_not_false_logout() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        let result = wait_for_origin(
            &format!("http://127.0.0.1:{port}"),
            Duration::from_millis(150),
        );
        assert!(result.is_err());
    }
}
