//! RAG (Retrieval Augmented Generation) module for SDLXLIFF segments.
//!
//! Provides vector embedding and semantic search for translation segments,
//! enabling efficient context retrieval for LLM queries.

use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;

// ============================================================================
// Types
// ============================================================================

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Segment {
    #[serde(alias = "segment_id")]
    pub id: String,
    pub source: String,
    pub target: String,
    pub status: String,
    #[serde(default)]
    pub percent: Option<u32>,
    #[serde(default)]
    pub origin: Option<String>,
}

#[derive(Clone, Debug)]
pub(crate) struct IndexedSegment {
    segment: Segment,
    /// Combined source+target embedding (for general search)
    embedding: Vec<f32>,
    /// Source-only embedding (for source language queries)
    source_embedding: Option<Vec<f32>>,
    /// Target-only embedding (for target language queries)
    target_embedding: Option<Vec<f32>>,
}

/// Search mode for RAG queries
#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum SearchMode {
    /// Search combined source+target embedding
    #[default]
    Combined,
    /// Search source text only
    Source,
    /// Search target text only
    Target,
    /// Search both and return max score
    Both,
}

#[derive(Debug, Serialize)]
pub struct SearchResult {
    pub segment: Segment,
    pub score: f32,
}

// ============================================================================
// Vector Store
// ============================================================================

pub struct VectorStore {
    /// Indexed segments per file (keyed by file path)
    indices: HashMap<String, Vec<IndexedSegment>>,
    /// File hashes to detect changes
    file_hashes: HashMap<String, String>,
}

impl VectorStore {
    pub fn new() -> Self {
        Self {
            indices: HashMap::new(),
            file_hashes: HashMap::new(),
        }
    }

    /// Check if file is already indexed and unchanged
    pub fn is_indexed(&self, file_path: &str, file_hash: &str) -> bool {
        self.file_hashes
            .get(file_path)
            .map(|h| h == file_hash)
            .unwrap_or(false)
    }

    /// Store indexed segments for a file
    pub fn store(
        &mut self,
        file_path: String,
        file_hash: String,
        segments: Vec<IndexedSegment>,
    ) {
        self.indices.insert(file_path.clone(), segments);
        self.file_hashes.insert(file_path, file_hash);
    }

    /// Search for similar segments with mode and threshold
    pub fn search(
        &self,
        file_path: &str,
        query_embedding: &[f32],
        limit: usize,
        mode: &SearchMode,
        min_score: f32,
    ) -> Vec<SearchResult> {
        let Some(segments) = self.indices.get(file_path) else {
            return Vec::new();
        };

        let mut results: Vec<SearchResult> = segments
            .iter()
            .filter_map(|indexed| {
                let score = match mode {
                    SearchMode::Combined => cosine_similarity(&indexed.embedding, query_embedding),
                    SearchMode::Source => {
                        indexed.source_embedding.as_ref()
                            .map(|e| cosine_similarity(e, query_embedding))
                            .unwrap_or_else(|| cosine_similarity(&indexed.embedding, query_embedding))
                    }
                    SearchMode::Target => {
                        indexed.target_embedding.as_ref()
                            .map(|e| cosine_similarity(e, query_embedding))
                            .unwrap_or_else(|| cosine_similarity(&indexed.embedding, query_embedding))
                    }
                    SearchMode::Both => {
                        let source_score = indexed.source_embedding.as_ref()
                            .map(|e| cosine_similarity(e, query_embedding))
                            .unwrap_or(0.0);
                        let target_score = indexed.target_embedding.as_ref()
                            .map(|e| cosine_similarity(e, query_embedding))
                            .unwrap_or(0.0);
                        let combined_score = cosine_similarity(&indexed.embedding, query_embedding);
                        // Return max of all three
                        source_score.max(target_score).max(combined_score)
                    }
                };

                // Apply threshold filter
                if score >= min_score {
                    Some(SearchResult {
                        segment: indexed.segment.clone(),
                        score,
                    })
                } else {
                    None
                }
            })
            .collect();

        // Sort by score descending
        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));

        results.truncate(limit);
        results
    }

    /// Get stats about indexed files
    pub fn stats(&self) -> HashMap<String, usize> {
        self.indices
            .iter()
            .map(|(path, segs)| (path.clone(), segs.len()))
            .collect()
    }

    /// Clear index for a file
    pub fn clear(&mut self, file_path: &str) {
        self.indices.remove(file_path);
        self.file_hashes.remove(file_path);
    }
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }

    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();

    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }

    dot / (norm_a * norm_b)
}

// ============================================================================
// Embedding Client
// ============================================================================

#[derive(Clone)]
pub struct EmbeddingClient {
    client: Client,
    api_url: String,
    api_key: Option<String>,
    model: String,
}

#[derive(Serialize)]
struct EmbeddingRequest {
    input: Vec<String>,
    model: String,
}

#[derive(Deserialize)]
struct EmbeddingResponse {
    data: Vec<EmbeddingData>,
}

#[derive(Deserialize)]
struct EmbeddingData {
    embedding: Vec<f32>,
}

impl EmbeddingClient {
    /// Create client for OpenAI-compatible embedding API
    pub fn new(api_url: String, api_key: Option<String>, model: String) -> Self {
        Self {
            client: Client::new(),
            api_url,
            api_key,
            model,
        }
    }

    /// Create client for OpenAI
    pub fn openai(api_key: String) -> Self {
        Self::new(
            "https://api.openai.com/v1/embeddings".to_string(),
            Some(api_key),
            "text-embedding-3-small".to_string(),
        )
    }

    /// Create client for local Ollama
    /// Uses mxbai-embed-large for better multilingual support
    pub fn ollama() -> Self {
        Self::new(
            "http://localhost:11434/api/embeddings".to_string(),
            None,
            "mxbai-embed-large".to_string(),
        )
    }

    /// Create client for local Ollama with nomic (smaller, faster)
    pub fn ollama_nomic() -> Self {
        Self::new(
            "http://localhost:11434/api/embeddings".to_string(),
            None,
            "nomic-embed-text".to_string(),
        )
    }

    /// Get embeddings for texts
    pub async fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }

        // Check if this is Ollama (different API format)
        if self.api_url.contains("11434") || self.api_url.contains("ollama") {
            return self.embed_ollama(texts).await;
        }

        let request = EmbeddingRequest {
            input: texts,
            model: self.model.clone(),
        };

        let mut req = self.client.post(&self.api_url).json(&request);

        if let Some(ref key) = self.api_key {
            req = req.header("Authorization", format!("Bearer {}", key));
        }

        let response = req
            .send()
            .await
            .map_err(|e| format!("Embedding request failed: {}", e))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(format!("Embedding API error {}: {}", status, body));
        }

        let result: EmbeddingResponse = response
            .json()
            .await
            .map_err(|e| format!("Failed to parse embedding response: {}", e))?;

        Ok(result.data.into_iter().map(|d| d.embedding).collect())
    }

    /// Ollama has a different API format
    async fn embed_ollama(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        let mut embeddings = Vec::new();

        // Ollama processes one at a time
        for text in texts {
            let request = serde_json::json!({
                "model": self.model,
                "prompt": text
            });

            let response = self
                .client
                .post(&self.api_url)
                .json(&request)
                .send()
                .await
                .map_err(|e| format!("Ollama request failed: {}", e))?;

            if !response.status().is_success() {
                let status = response.status();
                let body = response.text().await.unwrap_or_default();
                return Err(format!("Ollama error {}: {}", status, body));
            }

            #[derive(Deserialize)]
            struct OllamaResponse {
                embedding: Vec<f32>,
            }

            let result: OllamaResponse = response
                .json()
                .await
                .map_err(|e| format!("Failed to parse Ollama response: {}", e))?;

            embeddings.push(result.embedding);
        }

        Ok(embeddings)
    }

    /// Embed a single text
    pub async fn embed_one(&self, text: String) -> Result<Vec<f32>, String> {
        let results = self.embed(vec![text]).await?;
        results
            .into_iter()
            .next()
            .ok_or_else(|| "No embedding returned".to_string())
    }
}

// ============================================================================
// RAG State (for Tauri)
// ============================================================================

pub struct RagState {
    pub store: Mutex<VectorStore>,
    pub client: Mutex<Option<EmbeddingClient>>,
}

impl RagState {
    pub fn new() -> Self {
        Self {
            store: Mutex::new(VectorStore::new()),
            client: Mutex::new(None),
        }
    }
}

// ============================================================================
// Public API for Tauri Commands
// ============================================================================

/// Initialize the embedding client
pub fn init_client(state: &RagState, api_key: Option<String>, use_ollama: bool) -> Result<(), String> {
    let client = if use_ollama {
        EmbeddingClient::ollama()
    } else if let Some(key) = api_key {
        EmbeddingClient::openai(key)
    } else {
        return Err("No API key provided and Ollama not selected".to_string());
    };

    let mut guard = state.client.lock().map_err(|e| e.to_string())?;
    *guard = Some(client);
    Ok(())
}

/// Index segments for a file
/// When separate_embeddings is true, creates separate source/target embeddings for better search
pub async fn index_segments(
    state: &RagState,
    file_path: String,
    file_hash: String,
    segments: Vec<Segment>,
    separate_embeddings: bool,
) -> Result<usize, String> {
    // Check if already indexed
    {
        let store = state.store.lock().map_err(|e| e.to_string())?;
        if store.is_indexed(&file_path, &file_hash) {
            return Ok(segments.len());
        }
    }

    // Get embedding client
    let client = {
        let guard = state.client.lock().map_err(|e| e.to_string())?;
        guard.clone().ok_or("Embedding client not initialized")?
    };

    // Prepare combined texts for embedding
    let combined_texts: Vec<String> = segments
        .iter()
        .map(|s| format!("Source: {} Target: {}", s.source, s.target))
        .collect();

    // Get combined embeddings
    let combined_embeddings = client.embed(combined_texts).await?;

    if combined_embeddings.len() != segments.len() {
        return Err(format!(
            "Embedding count mismatch: {} vs {}",
            combined_embeddings.len(),
            segments.len()
        ));
    }

    // Optionally get separate source/target embeddings
    let (source_embeddings, target_embeddings) = if separate_embeddings {
        let source_texts: Vec<String> = segments.iter().map(|s| s.source.clone()).collect();
        let target_texts: Vec<String> = segments.iter().map(|s| s.target.clone()).collect();

        let source_emb = client.embed(source_texts).await?;
        let target_emb = client.embed(target_texts).await?;

        (Some(source_emb), Some(target_emb))
    } else {
        (None, None)
    };

    // Create indexed segments
    let indexed: Vec<IndexedSegment> = segments
        .into_iter()
        .enumerate()
        .map(|(i, segment)| {
            IndexedSegment {
                segment,
                embedding: combined_embeddings[i].clone(),
                source_embedding: source_embeddings.as_ref().map(|v| v[i].clone()),
                target_embedding: target_embeddings.as_ref().map(|v| v[i].clone()),
            }
        })
        .collect();

    let count = indexed.len();

    // Store in vector store
    {
        let mut store = state.store.lock().map_err(|e| e.to_string())?;
        store.store(file_path, file_hash, indexed);
    }

    Ok(count)
}

/// Search for similar segments
/// - mode: search combined, source-only, target-only, or both
/// - min_score: minimum relevance threshold (0.0-1.0, default 0.5)
pub async fn search_segments(
    state: &RagState,
    file_path: String,
    query: String,
    limit: usize,
    mode: SearchMode,
    min_score: f32,
) -> Result<Vec<SearchResult>, String> {
    // Get embedding client
    let client = {
        let guard = state.client.lock().map_err(|e| e.to_string())?;
        guard.clone().ok_or("Embedding client not initialized")?
    };

    // Embed query
    let query_embedding = client.embed_one(query).await?;

    // Search with mode and threshold
    let store = state.store.lock().map_err(|e| e.to_string())?;
    Ok(store.search(&file_path, &query_embedding, limit, &mode, min_score))
}

/// Get RAG stats
pub fn get_stats(state: &RagState) -> Result<HashMap<String, usize>, String> {
    let store = state.store.lock().map_err(|e| e.to_string())?;
    Ok(store.stats())
}

/// Clear index for a file
pub fn clear_index(state: &RagState, file_path: &str) -> Result<(), String> {
    let mut store = state.store.lock().map_err(|e| e.to_string())?;
    store.clear(file_path);
    Ok(())
}

/// Check if Ollama is running and if the model is installed
pub async fn check_ollama() -> Result<bool, String> {
    let client = reqwest::Client::new();
    match client
        .get("http://localhost:11434/api/tags")
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
    {
        Ok(resp) => Ok(resp.status().is_success()),
        Err(_) => Ok(false),
    }
}

/// Check if a specific model is installed
pub async fn check_ollama_model(model: &str) -> Result<bool, String> {
    let client = reqwest::Client::new();
    let response = client
        .get("http://localhost:11434/api/tags")
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
        .map_err(|_| "Ollama not running")?;

    if !response.status().is_success() {
        return Ok(false);
    }

    let body: serde_json::Value = response.json().await.map_err(|e| e.to_string())?;

    if let Some(models) = body["models"].as_array() {
        for m in models {
            if let Some(name) = m["name"].as_str() {
                if name.starts_with(model) {
                    return Ok(true);
                }
            }
        }
    }

    Ok(false)
}

/// Install Ollama via Homebrew (macOS)
pub fn install_ollama() -> Result<String, String> {
    use std::process::Command;

    // Check if brew exists
    let brew_check = Command::new("which")
        .arg("brew")
        .output()
        .map_err(|e| format!("Failed to check for Homebrew: {}", e))?;

    if !brew_check.status.success() {
        return Err("Homebrew not found. Install from https://brew.sh first.".to_string());
    }

    // Check if ollama already installed
    let ollama_check = Command::new("which")
        .arg("ollama")
        .output()
        .map_err(|e| format!("Failed to check for Ollama: {}", e))?;

    if ollama_check.status.success() {
        return Ok("Ollama is already installed.".to_string());
    }

    // Install ollama
    let output = Command::new("brew")
        .args(["install", "ollama"])
        .output()
        .map_err(|e| format!("Failed to run brew install: {}", e))?;

    if output.status.success() {
        Ok("Ollama installed successfully! Now run: ollama serve".to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("Installation failed: {}", stderr))
    }
}

/// Start Ollama server
pub fn start_ollama() -> Result<String, String> {
    use std::process::Command;

    // Check if ollama is installed
    let ollama_check = Command::new("which")
        .arg("ollama")
        .output()
        .map_err(|e| format!("Failed to check for Ollama: {}", e))?;

    if !ollama_check.status.success() {
        return Err("Ollama not installed. Click 'Install Ollama' first.".to_string());
    }

    // Start ollama serve in background
    Command::new("ollama")
        .arg("serve")
        .spawn()
        .map_err(|e| format!("Failed to start Ollama: {}", e))?;

    Ok("Ollama starting... wait a few seconds then refresh.".to_string())
}

/// Pull Ollama model
pub async fn pull_ollama_model(model: &str) -> Result<String, String> {
    let client = reqwest::Client::new();

    // First check if Ollama is running
    if !check_ollama().await.unwrap_or(false) {
        return Err("Ollama is not running. Start it with: ollama serve".to_string());
    }

    let response = client
        .post("http://localhost:11434/api/pull")
        .json(&serde_json::json!({ "name": model }))
        .send()
        .await
        .map_err(|e| format!("Failed to pull model: {}", e))?;

    if !response.status().is_success() {
        return Err(format!("Failed to pull model: {}", response.status()));
    }

    // Read stream to completion (pull is streamed)
    let bytes = response.bytes().await.map_err(|e| e.to_string())?;

    // Check last line for success
    let text = String::from_utf8_lossy(&bytes);
    if text.contains("\"status\":\"success\"") {
        Ok(format!("Model {} pulled successfully", model))
    } else {
        Ok(format!("Model {} pull completed", model))
    }
}