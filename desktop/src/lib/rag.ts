/**
 * RAG (Retrieval Augmented Generation) client for SDLXLIFF segments.
 *
 * Provides semantic search over translation segments, enabling
 * efficient context retrieval for LLM queries.
 */

import { invoke } from '@tauri-apps/api/core';

export interface Segment {
	id: string;
	source: string;
	target: string;
	status: string;
	percent?: number;
	origin?: string;
}

export interface SearchResult {
	segment: Segment;
	score: number;
}

export interface RagStats {
	[filePath: string]: number;
}

/**
 * Initialize the RAG embedding client.
 *
 * @param apiKey - OpenAI API key (optional if using Ollama)
 * @param useOllama - Use local Ollama instead of OpenAI
 */
export async function ragInit(apiKey?: string, useOllama = false): Promise<string> {
	return invoke<string>('rag_init', {
		request: {
			api_key: apiKey,
			use_ollama: useOllama
		}
	});
}

/**
 * Index segments for semantic search.
 *
 * @param filePath - Path to the SDLXLIFF file
 * @param fileHash - Hash of file contents (for cache invalidation)
 * @param segments - Segments to index
 * @returns Number of segments indexed
 */
export async function ragIndex(
	filePath: string,
	fileHash: string,
	segments: Segment[]
): Promise<number> {
	return invoke<number>('rag_index', {
		request: {
			file_path: filePath,
			file_hash: fileHash,
			segments
		}
	});
}

/**
 * Search for segments matching a natural language query.
 *
 * @param filePath - Path to the indexed SDLXLIFF file
 * @param query - Natural language search query
 * @param limit - Maximum results to return (default: 10)
 * @returns Matching segments with relevance scores
 */
export async function ragSearch(
	filePath: string,
	query: string,
	limit = 10
): Promise<SearchResult[]> {
	return invoke<SearchResult[]>('rag_search', {
		request: {
			file_path: filePath,
			query,
			limit
		}
	});
}

/**
 * Get statistics about indexed files.
 *
 * @returns Map of file paths to segment counts
 */
export async function ragStats(): Promise<RagStats> {
	return invoke<RagStats>('rag_stats');
}

/**
 * Clear the index for a file.
 *
 * @param filePath - Path to the file to clear from index
 */
export async function ragClear(filePath: string): Promise<void> {
	return invoke<void>('rag_clear', { file_path: filePath });
}

/**
 * Compute a simple hash of file content for cache invalidation.
 */
export function computeHash(content: string): string {
	let hash = 0;
	for (let i = 0; i < content.length; i++) {
		const char = content.charCodeAt(i);
		hash = (hash << 5) - hash + char;
		hash = hash & hash; // Convert to 32bit integer
	}
	return hash.toString(16);
}

/**
 * Check if Ollama is running.
 */
export async function checkOllama(): Promise<boolean> {
	return invoke<boolean>('rag_check_ollama');
}

/**
 * Check if a specific Ollama model is installed.
 */
export async function checkOllamaModel(model: string): Promise<boolean> {
	return invoke<boolean>('rag_check_ollama_model', { model });
}

/**
 * Install Ollama via Homebrew (macOS).
 */
export async function installOllama(): Promise<string> {
	return invoke<string>('rag_install_ollama');
}

/**
 * Start Ollama server.
 */
export async function startOllama(): Promise<string> {
	return invoke<string>('rag_start_ollama');
}

/**
 * Pull an Ollama model.
 */
export async function pullOllamaModel(model: string): Promise<string> {
	return invoke<string>('rag_pull_ollama_model', { model });
}