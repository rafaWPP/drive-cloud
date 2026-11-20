mod download;
use std::net::TcpListener;
use std::sync::Mutex;
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![backend_origin, download::download_cloud_file])
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
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                    }
                }
            }
        }
    });
}
