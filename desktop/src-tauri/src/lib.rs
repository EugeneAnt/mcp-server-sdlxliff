use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, ChildStdin, Stdio};
use std::sync::Mutex;
use tauri::State;

struct McpServer {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout_reader: Option<BufReader<std::process::ChildStdout>>,
}

struct McpState(Mutex<McpServer>);

#[tauri::command]
fn spawn_mcp_server(
    state: State<McpState>,
    working_dir: String,
) -> Result<String, String> {
    let mut server = state.0.lock().map_err(|e| e.to_string())?;

    if server.child.is_some() {
        return Ok("Server already running".to_string());
    }

    let mut child = Command::new("uv")
        .args(["run", "--directory", &working_dir, "-m", "mcp_server_sdlxliff"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn MCP server: {}", e))?;

    // Take ownership of stdin and stdout
    let stdin = child.stdin.take().ok_or("Failed to get stdin")?;
    let stdout = child.stdout.take().ok_or("Failed to get stdout")?;
    let reader = BufReader::new(stdout);

    server.child = Some(child);
    server.stdin = Some(stdin);
    server.stdout_reader = Some(reader);

    Ok("MCP server started".to_string())
}

#[tauri::command]
fn mcp_request(state: State<McpState>, message: String) -> Result<String, String> {
    let mut server = state.0.lock().map_err(|e| e.to_string())?;

    // Write the request
    {
        let stdin = server.stdin.as_mut().ok_or("No stdin available")?;
        writeln!(stdin, "{}", message).map_err(|e| e.to_string())?;
        stdin.flush().map_err(|e| e.to_string())?;
    }

    // Read the response
    let reader = server.stdout_reader.as_mut().ok_or("No stdout reader")?;
    let mut response = String::new();
    reader.read_line(&mut response).map_err(|e| e.to_string())?;

    Ok(response)
}

#[tauri::command]
fn mcp_notify(state: State<McpState>, message: String) -> Result<(), String> {
    let mut server = state.0.lock().map_err(|e| e.to_string())?;

    let stdin = server.stdin.as_mut().ok_or("No stdin available")?;
    writeln!(stdin, "{}", message).map_err(|e| e.to_string())?;
    stdin.flush().map_err(|e| e.to_string())?;

    Ok(())
}

#[tauri::command]
fn stop_mcp_server(state: State<McpState>) -> Result<String, String> {
    let mut server = state.0.lock().map_err(|e| e.to_string())?;

    server.stdin = None;
    server.stdout_reader = None;

    if let Some(mut child) = server.child.take() {
        let _ = child.kill();
        let _ = child.wait();
        Ok("MCP server stopped".to_string())
    } else {
        Ok("No server running".to_string())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(McpState(Mutex::new(McpServer {
            child: None,
            stdin: None,
            stdout_reader: None,
        })))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_http::init())
        .invoke_handler(tauri::generate_handler![
            spawn_mcp_server,
            mcp_request,
            mcp_notify,
            stop_mcp_server
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}