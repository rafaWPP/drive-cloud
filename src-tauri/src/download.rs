//! Native, bounded-memory downloads for the desktop app.
//! The destination is chosen by a native OS dialog, never by an untrusted URL
//! or caller-supplied filesystem path. Existing files are never replaced.

use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri_plugin_dialog::DialogExt;

const MAX_DOWNLOAD_BYTES: u64 = 512 * 1024 * 1024;

fn valid_id(value: &str) -> bool {
    let raw = value.as_bytes();
    raw.len() == 36
        && raw.iter().enumerate().all(|(i, b)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                *b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
}

fn safe_suggestion(name: &str) -> String {
    let candidate = name.rsplit(['/', '\\']).next().unwrap_or("arquivo");
    let filtered: String = candidate
        .chars()
        .map(|c| {
            if c.is_control() || matches!(c, '<' | '>' | ':' | '"' | '|' | '?' | '*') {
                '_'
            } else {
                c
            }
        })
        .take(180)
        .collect();
    let trimmed = filtered.trim().trim_matches('.').trim();
    if trimmed.is_empty() || trimmed.eq_ignore_ascii_case("con") || trimmed.eq_ignore_ascii_case("nul") {
        "arquivo".to_string()
    } else {
        trimmed.to_string()
    }
}

fn temp_path(destination: &Path) -> Result<PathBuf, String> {
    let parent = destination.parent().ok_or("Destino de download inválido.")?;
    if !parent.is_dir() {
        return Err("A pasta selecionada não existe.".to_string());
    }
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "Relógio do sistema inválido.")?
        .as_nanos();
    Ok(parent.join(format!(".drive-cloud-{}-{stamp}.part", std::process::id())))
}

fn save_stream(origin: &str, file_id: &str, expected_size: u64, destination: &Path) -> Result<(), String> {
    if !valid_id(file_id) {
        return Err("Identificador de arquivo inválido.".to_string());
    }
    if expected_size > MAX_DOWNLOAD_BYTES {
        return Err("Arquivo maior que o limite atual de download (512 MB).".to_string());
    }
    if destination.exists() {
        return Err("O destino já existe. Escolha outro nome para preservar seus arquivos.".to_string());
    }

    let temporary = temp_path(destination)?;
    let result = (|| -> Result<(), String> {
        let client = reqwest::blocking::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .no_proxy() // Local file bytes must never pass through an HTTP proxy.
            .timeout(Duration::from_secs(60 * 60 * 2))
            .build()
            .map_err(|_| "Não foi possível preparar o download.".to_string())?;
        // origin comes exclusively from the running Tauri backend state.
        let url = format!("{origin}/api/cloud/download/{file_id}");
        let response = client
            .get(&url)
            .send()
            .map_err(|_| "Conexão com o conector local indisponível.".to_string())?;
        if !response.status().is_success() {
            return Err(format!("Download recusado pelo conector (HTTP {}).", response.status().as_u16()));
        }
        if let Some(length) = response.content_length() {
            if length > MAX_DOWNLOAD_BYTES || length != expected_size {
                return Err("Tamanho do arquivo recebido não confere com o catálogo.".to_string());
            }
        }
        if let Some(content_type) = response.headers().get(reqwest::header::CONTENT_TYPE) {
            if !content_type.to_str().unwrap_or("").starts_with("application/octet-stream") {
                return Err("O conector retornou um formato de download inesperado.".to_string());
            }
        }

        // A private sidecar file in the user's chosen directory ensures the
        // download never needs a 512-MB WebView Blob or a Rust in-memory buffer.
        let mut output = OpenOptions::new()
            .write(true).create_new(true)
            .open(&temporary)
            .map_err(|_| "Não foi possível criar o arquivo temporário de download.".to_string())?;
        let mut limited = response.take(MAX_DOWNLOAD_BYTES + 1);
        let count = io::copy(&mut limited, &mut output)
            .map_err(|_| "Download interrompido ou disco sem espaço.".to_string())?;
        if count != expected_size {
            return Err("Download incompleto: quantidade de bytes diferente do catálogo.".to_string());
        }
        output.sync_all().map_err(|_| "Não foi possível confirmar os dados no disco.".to_string())?;
        drop(output);

        // hard_link atomically reserves a new name without overwriting it.
        // Filesystems without hard links use an exclusive copy as fallback.
        if fs::hard_link(&temporary, destination).is_err() {
            let mut exclusive = OpenOptions::new()
                .write(true).create_new(true)
                .open(destination)
                .map_err(|_| "O arquivo de destino já existe ou não pode ser criado.".to_string())?;
            let copy_result = (|| -> io::Result<()> {
                let mut source = fs::File::open(&temporary)?;
                io::copy(&mut source, &mut exclusive)?;
                exclusive.flush()?;
                exclusive.sync_all()
            })();
            if copy_result.is_err() {
                drop(exclusive);
                let _ = fs::remove_file(destination);
                return Err("Não foi possível finalizar a cópia no disco.".to_string());
            }
        }
        Ok(())
    })();

    // This only removes a staging file created by the application.
    let _ = fs::remove_file(&temporary);
    result
}

#[tauri::command]
pub async fn download_cloud_file(
    app: tauri::AppHandle,
    state: tauri::State<'_, crate::Backend>,
    file_id: String,
    suggested_name: String,
    expected_size: u64,
) -> Result<Option<String>, String> {
    if !valid_id(&file_id) {
        return Err("Identificador de arquivo inválido.".to_string());
    }
    let origin = state.origin.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let proposal = safe_suggestion(&suggested_name);
        // Blocking dialogs must run off the UI thread.
        let selected = app.dialog().file()
            .set_title("Salvar arquivo do Drive Cloud")
            .set_file_name(proposal)
            .blocking_save_file();
        let Some(selected) = selected else {
            return Ok(None); // The user cancelled; nothing was written.
        };
        let destination = selected
            .into_path()
            .map_err(|_| "Selecione uma pasta local para este download.".to_string())?;
        save_stream(&origin, &file_id, expected_size, &destination)?;
        Ok(Some(destination.to_string_lossy().to_string()))
    })
    .await
    .map_err(|_| "Erro interno ao finalizar o download.".to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invalid_id_cannot_change_download_path() {
        assert!(valid_id("11111111-2222-3333-4444-555555555555"));
        assert!(!valid_id("../etc/passwd"));
        assert!(!valid_id("11111111/2222/3333/4444/555555555555"));
    }

    #[test]
    fn file_suggestions_remove_path_and_unsafe_characters() {
        assert_eq!(safe_suggestion("../other/foto.jpg"), "foto.jpg");
        assert_eq!(safe_suggestion("pasta\\segredo.txt"), "segredo.txt");
        assert_eq!(safe_suggestion("a:b?.pdf"), "a_b_.pdf");
    }

    #[test]
    fn existing_destination_is_never_overwritten() {
        let parent = std::env::temp_dir();
        let filename = format!(
            "drive-cloud-test-{}-{}",
            std::process::id(),
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()
        );
        let destination = parent.join(filename);
        fs::write(&destination, b"must stay untouched").unwrap();
        let response = save_stream(
            "http://127.0.0.1:1",
            "11111111-2222-3333-4444-555555555555",
            21,
            &destination,
        );
        assert!(response.is_err());
        assert_eq!(fs::read(&destination).unwrap(), b"must stay untouched");
        fs::remove_file(destination).unwrap();
    }
    #[test]
    fn streams_http_response_to_disk_with_correct_size() {
        use std::net::TcpListener;
        use std::thread;

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0u8; 1024];
            let _ = stream.read(&mut request);
            stream.write_all(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello",
            ).unwrap();
        });
        let filename = format!(
            "drive-cloud-integration-{}-{}.bin",
            std::process::id(),
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()
        );
        let target = std::env::temp_dir().join(filename);
        let result = save_stream(
            &format!("http://127.0.0.1:{port}"),
            "11111111-2222-3333-4444-555555555555",
            5,
            &target,
        );
        server.join().unwrap();
        assert!(result.is_ok(), "{result:?}");
        assert_eq!(fs::read(&target).unwrap(), b"hello");
        fs::remove_file(target).unwrap();
    }

}
