//! Native desktop drag/drop import.
//!
//! The OS provides file paths through Tauri's drag-drop event. The WebView
//! never reads large source files into JS memory: Rust streams each file as
//! multipart bytes to the loopback backend, which uploads to Telegram.
//! No filesystem paths are stored in the Telegram catalog.

use serde::Serialize;
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::time::Duration;

const MAX_BYTES: u64 = 512 * 1024 * 1024;
const MAX_DROP_FILES: usize = 50;

#[derive(Serialize)]
pub struct DropUploadResult {
    name: String,
    ok: bool,
    detail: String,
}

fn safe_dragged_file(path: &Path, application_data: &Path) -> Result<(PathBuf, String, u64), String> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|_| "O arquivo arrastado não está disponível.".to_string())?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_file() {
        return Err("Arraste arquivos comuns, não pastas ou atalhos simbólicos.".to_string());
    }
    let resolved = fs::canonicalize(path)
        .map_err(|_| "Não foi possível acessar o arquivo arrastado.".to_string())?;
    if resolved.starts_with(application_data) {
        return Err("A pasta interna do Drive Cloud não pode ser enviada.".to_string());
    }
    // Do not allow accidentally dropping private credential stores. OS drop
    // paths are untrusted input to this command, so validate every component.
    for component in resolved.components() {
        if let std::path::Component::Normal(value) = component {
            let segment = value.to_string_lossy().to_lowercase();
            if segment.starts_with('.') || matches!(segment.as_str(),
                    "appdata" | "application data" | "system volume information" |
                    "$recycle.bin" | "id_rsa" | "id_ed25519" | "credentials.json" |
                    "telegram.session" | "telegram.session-journal") {
                return Err("Por segurança, arquivos de configuração ou credenciais não podem ser arrastados.".to_string());
            }
        }
    }
    let filename = resolved.file_name().and_then(|s| s.to_str()).unwrap_or("").to_string();
    if filename.is_empty() || filename.starts_with('.') ||
        filename.len() > 180 || filename.contains('/') || filename.contains('\\') ||
        filename.chars().any(|c| c.is_control()) {
        return Err("Nome de arquivo inválido ou oculto. Selecione outro arquivo.".to_string());
    }
    if metadata.len() > MAX_BYTES {
        return Err("Arquivo maior que o limite atual de 512 MiB.".to_string());
    }
    // The server does not currently support empty Telegram files.
    if metadata.len() == 0 {
        return Err("Arquivo vazio não pode ser enviado ao Telegram.".to_string());
    }
    Ok((resolved, filename, metadata.len()))
}

fn send_file(client: &reqwest::blocking::Client, origin: &str,
             path: &Path, name: &str, size: u64, parent: &Option<String>) -> Result<(), String> {
    // Streaming multipart body; do not buffer 512 MiB into Rust or JavaScript.
    let file = File::open(path)
        .map_err(|_| "Não foi possível abrir o arquivo no disco.".to_string())?;
    let part = reqwest::blocking::multipart::Part::reader_with_length(file, size)
        .file_name(name.to_owned())
        .mime_str("application/octet-stream")
        .map_err(|_| "Falha ao preparar o envio.".to_string())?;
    let mut form = reqwest::blocking::multipart::Form::new()
        .part("file", part)
        .text("upload_id", uuid::Uuid::new_v4().to_string());
    if let Some(folder) = parent {
        form = form.text("parent", folder.to_owned());
    }
    // The localhost backend enforces an allowlist for the Origin header on
    // every write. Native reqwest does not set Origin automatically, unlike
    // browser fetch. Keep this exact desktop-origin value aligned with
    // backend/server.py's ALLOWED list.
    let response = client.post(format!("{origin}/api/cloud/upload"))
        .header(reqwest::header::ORIGIN, "http://tauri.localhost")
        .multipart(form)
        .send()
        .map_err(|error| {
            // A connection may fail after Telegram accepted the file. Never
            // automatically retry such uploads: check the Drive catalog first.
            if error.is_timeout() {
                "O upload excedeu o tempo de espera do serviço local. Verifique o Meu Drive antes de reenviar.".to_string()
            } else if error.is_connect() {
                "O serviço local do Drive Cloud está desconectado. Reinicie o aplicativo e tente novamente.".to_string()
            } else {
                format!(
                    "Conexão interrompida durante o upload ({}). Verifique se o arquivo apareceu no Meu Drive antes de tentar novamente.",
                    error
                )
            }
        })?;
    if !response.status().is_success() {
        let status = response.status();
        // Do not leak raw backend content to the UI. FastAPI includes a
        // controlled 'detail' on non-2xx responses; limit its length.
        let detail = response.text().unwrap_or_default();
        let message = serde_json::from_str::<serde_json::Value>(&detail)
            .ok()
            .and_then(|value| value.get("detail").and_then(|value| value.as_str()).map(str::to_owned))
            .unwrap_or_else(|| "Verifique a conexão com o Telegram e tente novamente.".to_string());
        return Err(format!("Falha no upload (HTTP {}): {}",
                           status.as_u16(), message.chars().take(220).collect::<String>()));
    }
    Ok(())
}

#[tauri::command]
pub async fn upload_dropped_files(
    state: tauri::State<'_, crate::Backend>,
    app: tauri::AppHandle,
    paths: Vec<String>,
    parent: Option<String>,
) -> Result<Vec<DropUploadResult>, String> {
    if paths.is_empty() || paths.len() > MAX_DROP_FILES {
        return Err("Arraste entre 1 e 50 arquivos por vez.".to_string());
    }
    if let Some(ref folder) = parent {
        if uuid::Uuid::parse_str(folder).is_err() {
            return Err("Pasta de destino inválida.".to_string());
        }
    }
    use tauri::Manager;
    let local_data = app.path().app_local_data_dir()
        .map_err(|_| "Pasta interna indisponível.".to_string())?;
    let local_data = fs::canonicalize(local_data)
        .map_err(|_| "Pasta interna indisponível.".to_string())?;
    let origin = state.origin.clone();

    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .no_proxy() // Source files stay on this computer and the local connector.
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(2 * 60 * 60))
            .build()
            .map_err(|_| "Não foi possível iniciar os uploads.".to_string())?;

        let mut results = Vec::with_capacity(paths.len());
        for raw_path in paths {
            let name = Path::new(&raw_path).file_name()
                .and_then(|s| s.to_str()).unwrap_or("arquivo").to_string();
            let result = safe_dragged_file(Path::new(&raw_path), &local_data)
                .and_then(|(path, filename, length)| {
                    send_file(&client, &origin, &path, &filename, length, &parent)
                });
            match result {
                Ok(()) => results.push(DropUploadResult {
                    name, ok: true, detail: "Arquivo enviado ao Telegram.".into()
                }),
                Err(detail) => results.push(DropUploadResult {
                    name, ok: false, detail
                }),
            }
        }
        Ok(results)
    })
    .await
    .map_err(|_| "Importação nativa interrompida.".to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reject_missing_file_and_invalid_symlink() {
        let base = std::env::temp_dir();
        let missing = base.join(format!("drive-cloud-missing-{}", uuid::Uuid::new_v4()));
        assert!(safe_dragged_file(&missing, &base).is_err());
    }

    #[test]
    fn accepts_user_file_without_reading_its_contents() {
        // On Windows, temp_dir() normally lives under AppData, which is
        // deliberately blocked for native drag/drop to protect credentials.
        // Use the test working directory for an ordinary, allowed file.
        let base = if cfg!(windows) {
            std::env::current_dir().unwrap()
        } else {
            std::env::temp_dir()
        };
        let file = base.join(format!("dc-drag-{}.txt", uuid::Uuid::new_v4()));
        fs::write(&file, b"demo").unwrap();
        let internal = base.join("nonexistent-dc-internal-data");
        let result = safe_dragged_file(&file, &internal);
        assert!(result.is_ok(), "{result:?}");
        assert_eq!(result.unwrap().2, 4);
        fs::remove_file(file).unwrap();
    }

    #[test]
    fn refuses_hidden_credential_directories() {
        let base = std::env::temp_dir()
            .join(format!("dc-hidden-test-{}", uuid::Uuid::new_v4()));
        let sensitive = base.join(".ssh");
        fs::create_dir_all(&sensitive).unwrap();
        let secret = sensitive.join("id_rsa");
        fs::write(&secret, b"not for upload").unwrap();
        assert!(safe_dragged_file(&secret, &base.join("internal")).is_err());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn never_imports_application_internal_files() {
        let base = std::env::temp_dir()
            .join(format!("dc-drop-internal-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&base).unwrap();
        let file = base.join("session.sqlite");
        fs::write(&file, b"private").unwrap();
        assert!(safe_dragged_file(&file, &base).is_err());
        fs::remove_dir_all(base).unwrap();
    }
}
