use std::io::{BufRead, BufReader, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;

use futures::StreamExt;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

// ============================================================================
// MCP Server State
// ============================================================================

struct McpServer {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout_reader: Option<BufReader<std::process::ChildStdout>>,
}

struct McpState(Mutex<McpServer>);

// ============================================================================
// Anthropic API State
// ============================================================================

struct ApiKeyState(Mutex<Option<String>>);

#[derive(Clone, Serialize)]
struct ChatEvent {
    event_type: String,
    content: Option<String>,
    tool_use: Option<ToolUseEvent>,
    usage: Option<UsageEvent>,
    error: Option<String>,
}

#[derive(Clone, Serialize)]
struct ToolUseEvent {
    id: String,
    name: String,
    input: serde_json::Value,
}

#[derive(Clone, Serialize)]
struct UsageEvent {
    input_tokens: u32,
    output_tokens: u32,
    cache_read_tokens: Option<u32>,
    cache_write_tokens: Option<u32>,
}

#[derive(Deserialize)]
struct ChatRequest {
    messages: Vec<Message>,
    system_prompt: String,
    tools: Option<Vec<serde_json::Value>>,
    stream_id: String,
    model: Option<String>,
}

// Model constants
const MODEL_HAIKU: &str = "claude-haiku-4-5-20251001";
const MODEL_SONNET: &str = "claude-sonnet-4-5-20250929";

fn select_model(requested: Option<&str>, messages: &[Message]) -> &'static str {
    match requested {
        Some("haiku") => MODEL_HAIKU,
        Some("sonnet") => MODEL_SONNET,
        Some("auto") | None => {
            // Auto-detect based on message content
            // Use Sonnet for translation/QA tasks, Haiku for simple reads
            let last_message = messages.last().and_then(|m| {
                match &m.content {
                    serde_json::Value::String(s) => Some(s.to_lowercase()),
                    _ => None
                }
            });

            if let Some(text) = last_message {
                let needs_sonnet = text.contains("translat")
                    || text.contains("перевод")
                    || text.contains("übersetze")
                    || text.contains("tradui")
                    || text.contains("qa")
                    || text.contains("quality")
                    || text.contains("check")
                    || text.contains("review")
                    || text.contains("fix")
                    || text.contains("correct")
                    || text.contains("update")
                    || text.contains("change")
                    || text.contains("edit")
                    || text.contains("improve");

                if needs_sonnet {
                    MODEL_SONNET
                } else {
                    MODEL_HAIKU
                }
            } else {
                MODEL_SONNET // Default to Sonnet for complex content
            }
        }
        _ => MODEL_SONNET,
    }
}

#[derive(Clone, Deserialize, Serialize)]
struct Message {
    role: String,
    content: serde_json::Value,
}

// ============================================================================
// MCP Server Commands
// ============================================================================

fn find_python() -> Result<String, String> {
    let candidates = [
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "python3",
        "/usr/bin/python3",
    ];

    let mut tried = Vec::new();

    for candidate in candidates {
        if candidate.starts_with('/') {
            if Path::new(candidate).exists() {
                return Ok(candidate.to_string());
            }
            tried.push(format!("{} (not found)", candidate));
        } else {
            match Command::new(candidate).arg("--version").output() {
                Ok(_) => return Ok(candidate.to_string()),
                Err(e) => tried.push(format!("{} ({})", candidate, e)),
            }
        }
    }
    Err(format!("Python not found. Tried: {}", tried.join(", ")))
}

#[tauri::command]
fn spawn_mcp_server(state: State<McpState>) -> Result<String, String> {
    let mut server = state.0.lock().map_err(|e| e.to_string())?;

    if server.child.is_some() {
        return Ok("Server already running".to_string());
    }

    let python = find_python()?;

    let check = Command::new(&python)
        .args(["-c", "import mcp_server_sdlxliff"])
        .output()
        .map_err(|e| format!("Failed to check for mcp_server_sdlxliff: {}", e))?;

    if !check.status.success() {
        let stderr = String::from_utf8_lossy(&check.stderr);
        return Err(format!(
            "mcp-server-sdlxliff not installed for {}. Run: pip install mcp-server-sdlxliff\nError: {}",
            python, stderr.trim()
        ));
    }

    let mut child = Command::new(&python)
        .args(["-m", "mcp_server_sdlxliff"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn MCP server with {}: {}", python, e))?;

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

    {
        let stdin = server.stdin.as_mut().ok_or("No stdin available")?;
        writeln!(stdin, "{}", message).map_err(|e| e.to_string())?;
        stdin.flush().map_err(|e| e.to_string())?;
    }

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

// ============================================================================
// Anthropic API Commands
// ============================================================================

#[tauri::command]
fn set_api_key(state: State<ApiKeyState>, key: String) -> Result<(), String> {
    let mut api_key = state.0.lock().map_err(|e| e.to_string())?;
    *api_key = Some(key);
    Ok(())
}

#[tauri::command]
fn clear_api_key(state: State<ApiKeyState>) -> Result<(), String> {
    let mut api_key = state.0.lock().map_err(|e| e.to_string())?;
    *api_key = None;
    Ok(())
}

#[tauri::command]
fn has_api_key(state: State<ApiKeyState>) -> bool {
    state.0.lock().map(|k| k.is_some()).unwrap_or(false)
}

#[tauri::command]
async fn chat_stream(
    app: AppHandle,
    state: State<'_, ApiKeyState>,
    request: ChatRequest,
) -> Result<(), String> {
    let api_key = {
        let key_guard = state.0.lock().map_err(|e| e.to_string())?;
        key_guard.clone().ok_or("API key not set")?
    };

    let stream_id = request.stream_id.clone();
    let app_clone = app.clone();

    // Spawn the streaming task
    tauri::async_runtime::spawn(async move {
        if let Err(e) = run_chat_stream(app_clone.clone(), api_key, request).await {
            let _ = app_clone.emit(
                &format!("chat-event-{}", stream_id),
                ChatEvent {
                    event_type: "error".to_string(),
                    content: None,
                    tool_use: None,
                    usage: None,
                    error: Some(e),
                },
            );
        }
    });

    Ok(())
}

async fn run_chat_stream(
    app: AppHandle,
    api_key: String,
    request: ChatRequest,
) -> Result<(), String> {
    let client = Client::new();
    let stream_id = request.stream_id;
    let event_name = format!("chat-event-{}", stream_id);

    // Select model based on request or auto-detect
    let model = select_model(request.model.as_deref(), &request.messages);
    log::info!("Using model: {}", model);

    // Emit model selection event
    let _ = app.emit(
        &event_name,
        ChatEvent {
            event_type: "model_selected".to_string(),
            content: Some(model.to_string()),
            tool_use: None,
            usage: None,
            error: None,
        },
    );

    // Build the request body
    let mut body = serde_json::json!({
        "model": model,
        "max_tokens": 8192,
        "stream": true,
        "system": [{
            "type": "text",
            "text": request.system_prompt,
            "cache_control": { "type": "ephemeral" }
        }],
        "messages": request.messages,
    });

    // Add tools with cache control on last tool
    if let Some(tools) = request.tools {
        if !tools.is_empty() {
            let mut tools_with_cache: Vec<serde_json::Value> = tools
                .into_iter()
                .enumerate()
                .map(|(i, mut tool)| {
                    if let serde_json::Value::Object(ref mut obj) = tool {
                        // Add cache_control to last tool
                        if i == obj.len() - 1 {
                            obj.insert(
                                "cache_control".to_string(),
                                serde_json::json!({ "type": "ephemeral" }),
                            );
                        }
                    }
                    tool
                })
                .collect();

            // Fix: apply cache_control to actual last tool
            if let Some(last) = tools_with_cache.last_mut() {
                if let serde_json::Value::Object(ref mut obj) = last {
                    obj.insert(
                        "cache_control".to_string(),
                        serde_json::json!({ "type": "ephemeral" }),
                    );
                }
            }

            body["tools"] = serde_json::Value::Array(tools_with_cache);
        }
    }

    let response = client
        .post("https://api.anthropic.com/v1/messages")
        .header("x-api-key", &api_key)
        .header("anthropic-version", "2023-06-01")
        .header("anthropic-beta", "prompt-caching-2024-07-31")
        .header("content-type", "application/json")
        .body(body.to_string())
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    if !response.status().is_success() {
        let status = response.status();
        let error_body = response.text().await.unwrap_or_default();
        return Err(format!("API error {}: {}", status, error_body));
    }

    let mut stream = response.bytes_stream();
    let mut buffer = String::new();
    let mut total_usage = UsageEvent {
        input_tokens: 0,
        output_tokens: 0,
        cache_read_tokens: Some(0),
        cache_write_tokens: Some(0),
    };

    // Current tool being built
    let mut current_tool_id: Option<String> = None;
    let mut current_tool_name: Option<String> = None;
    let mut current_tool_input = String::new();

    while let Some(chunk_result) = stream.next().await {
        let chunk = chunk_result.map_err(|e| format!("Stream error: {}", e))?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));

        // Process complete SSE events
        while let Some(event_end) = buffer.find("\n\n") {
            let event_data = buffer[..event_end].to_string();
            buffer = buffer[event_end + 2..].to_string();

            // Parse SSE event
            for line in event_data.lines() {
                if let Some(data) = line.strip_prefix("data: ") {
                    if data == "[DONE]" {
                        continue;
                    }

                    if let Ok(event) = serde_json::from_str::<serde_json::Value>(data) {
                        let event_type = event["type"].as_str().unwrap_or("");

                        match event_type {
                            "message_start" => {
                                if let Some(usage) = event["message"]["usage"].as_object() {
                                    total_usage.input_tokens +=
                                        usage.get("input_tokens").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
                                    if let Some(cr) = usage.get("cache_read_input_tokens").and_then(|v| v.as_u64()) {
                                        total_usage.cache_read_tokens = Some(
                                            total_usage.cache_read_tokens.unwrap_or(0) + cr as u32
                                        );
                                    }
                                    if let Some(cw) = usage.get("cache_creation_input_tokens").and_then(|v| v.as_u64()) {
                                        total_usage.cache_write_tokens = Some(
                                            total_usage.cache_write_tokens.unwrap_or(0) + cw as u32
                                        );
                                    }
                                }
                            }
                            "content_block_start" => {
                                let block = &event["content_block"];
                                if block["type"].as_str() == Some("tool_use") {
                                    current_tool_id = block["id"].as_str().map(String::from);
                                    current_tool_name = block["name"].as_str().map(String::from);
                                    current_tool_input.clear();
                                }
                            }
                            "content_block_delta" => {
                                let delta = &event["delta"];
                                if delta["type"].as_str() == Some("text_delta") {
                                    if let Some(text) = delta["text"].as_str() {
                                        let _ = app.emit(
                                            &event_name,
                                            ChatEvent {
                                                event_type: "text".to_string(),
                                                content: Some(text.to_string()),
                                                tool_use: None,
                                                usage: None,
                                                error: None,
                                            },
                                        );
                                    }
                                } else if delta["type"].as_str() == Some("input_json_delta") {
                                    if let Some(json) = delta["partial_json"].as_str() {
                                        current_tool_input.push_str(json);
                                    }
                                }
                            }
                            "content_block_stop" => {
                                // Emit tool use if we were building one
                                if let (Some(id), Some(name)) = (current_tool_id.take(), current_tool_name.take()) {
                                    let input: serde_json::Value = serde_json::from_str(&current_tool_input)
                                        .unwrap_or(serde_json::Value::Object(serde_json::Map::new()));
                                    current_tool_input.clear();

                                    let _ = app.emit(
                                        &event_name,
                                        ChatEvent {
                                            event_type: "tool_use".to_string(),
                                            content: None,
                                            tool_use: Some(ToolUseEvent { id, name, input }),
                                            usage: None,
                                            error: None,
                                        },
                                    );
                                }
                            }
                            "message_delta" => {
                                if let Some(usage) = event["usage"].as_object() {
                                    total_usage.output_tokens +=
                                        usage.get("output_tokens").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
                                }
                            }
                            "message_stop" => {
                                // Emit final usage
                                let _ = app.emit(
                                    &event_name,
                                    ChatEvent {
                                        event_type: "usage".to_string(),
                                        content: None,
                                        tool_use: None,
                                        usage: Some(total_usage.clone()),
                                        error: None,
                                    },
                                );

                                let _ = app.emit(
                                    &event_name,
                                    ChatEvent {
                                        event_type: "done".to_string(),
                                        content: None,
                                        tool_use: None,
                                        usage: None,
                                        error: None,
                                    },
                                );
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

// ============================================================================
// App Entry Point
// ============================================================================

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(McpState(Mutex::new(McpServer {
            child: None,
            stdin: None,
            stdout_reader: None,
        })))
        .manage(ApiKeyState(Mutex::new(None)))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            // MCP commands
            spawn_mcp_server,
            mcp_request,
            mcp_notify,
            stop_mcp_server,
            // API key commands
            set_api_key,
            clear_api_key,
            has_api_key,
            // Chat commands
            chat_stream,
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