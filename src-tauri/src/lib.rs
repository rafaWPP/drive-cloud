use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct Backend(Mutex<CommandChild>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // The backend is local to this installation. Telegram data is not
            // stored in the read-only application directory or a temp folder.
            let data_dir = app.path().app_local_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;
            let command = app
                .shell()
                .sidecar("drive-cloud-backend")?
                .env("DRIVE_CLOUD_DATA_DIR", data_dir.to_string_lossy().to_string());
            let (_events, child) = command.spawn()?;
            app.manage(Backend(Mutex::new(child)));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Falha ao iniciar o Drive Cloud");

    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(backend) = handle.try_state::<Backend>() {
                if let Ok(mut child) = backend.0.lock() {
                    let _ = child.kill();
                }
            }
        }
    });
}
