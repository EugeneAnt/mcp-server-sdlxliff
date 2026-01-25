/**
 * RAG Service - manages semantic search for SDLXLIFF segments
 */

import { get, writable } from 'svelte/store';
import {
	ragInit,
	ragIndex,
	ragSearch,
	ragStats,
	ragClear,
	computeHash,
	type Segment,
	type SearchResult
} from '$lib/rag';
import {
	ragEnabled,
	ragUseOllama,
	openaiApiKey,
	getRagSettings,
	setRagSettings
} from '$lib/stores/settings';
import { getMcpClient } from '$lib/mcp-client';

// RAG state
export const ragInitialized = writable(false);
export const ragIndexing = writable(false);
export const ragError = writable('');

// RAG stats for status line
export const ragIndexedSegments = writable(0);
export const ragLastSearchResults = writable(0);
export const ragSearchCount = writable(0); // Number of rag_search calls this session
export const ragTokensUsed = writable(0); // Approximate tokens returned by RAG this session

// RAG context for tools panel (full search results)
export const ragLastContext = writable<SearchResult[]>([]);

// The actual formatted context string injected into Claude's prompt
export const ragInjectedContext = writable<string>('');

// Track indexed files
const indexedFiles = new Map<string, string>(); // path -> hash

/**
 * Initialize RAG from stored settings
 */
export async function initializeRag(): Promise<void> {
	try {
		const settings = await getRagSettings();

		ragEnabled.set(settings.enabled);
		ragUseOllama.set(settings.useOllama);
		if (settings.openaiKey) {
			openaiApiKey.set(settings.openaiKey);
		}

		if (settings.enabled) {
			await ragInit(settings.openaiKey ?? undefined, settings.useOllama);
			ragInitialized.set(true);
			ragError.set('');
			console.log('RAG initialized:', settings.useOllama ? 'Ollama' : 'OpenAI');
		}
	} catch (error) {
		console.error('Failed to initialize RAG:', error);
		ragError.set(error instanceof Error ? error.message : 'RAG initialization failed');
		ragInitialized.set(false);
	}
}

/**
 * Enable/disable RAG
 */
export async function setRagEnabled(enabled: boolean): Promise<void> {
	const useOllama = get(ragUseOllama);
	const openaiKey = get(openaiApiKey);

	if (enabled) {
		if (!useOllama && !openaiKey) {
			throw new Error('OpenAI API key required when not using Ollama');
		}

		await ragInit(openaiKey || undefined, useOllama);
		ragInitialized.set(true);
	} else {
		ragInitialized.set(false);
	}

	ragEnabled.set(enabled);
	await setRagSettings({ enabled, useOllama, openaiKey });
}

/**
 * Update RAG provider settings
 */
export async function updateRagProvider(useOllama: boolean, openaiKey?: string): Promise<void> {
	ragUseOllama.set(useOllama);
	if (openaiKey !== undefined) {
		openaiApiKey.set(openaiKey);
	}

	const enabled = get(ragEnabled);
	await setRagSettings({
		enabled,
		useOllama,
		openaiKey: openaiKey ?? get(openaiApiKey)
	});

	// Re-initialize if enabled
	if (enabled) {
		await ragInit(openaiKey ?? get(openaiApiKey) ?? undefined, useOllama);
		ragInitialized.set(true);
	}
}

/**
 * Index a file's segments for RAG search
 */
export async function indexFile(filePath: string): Promise<number> {
	if (!get(ragEnabled) || !get(ragInitialized)) {
		return 0;
	}

	ragIndexing.set(true);
	ragError.set('');

	try {
		const client = getMcpClient();
		if (!client) {
			throw new Error('MCP not connected');
		}

		// Get segments via MCP (for_indexing bypasses 50-segment limit)
		const result = await client.callTool('read_sdlxliff', {
			file_path: filePath,
			limit: 10000, // High limit for indexing
			for_indexing: true // Bypass limit cap - segments go to RAG, not Claude context
		});

		const content = result.content[0];
		if (!content.text) {
			throw new Error('No segments returned');
		}

		const data = JSON.parse(content.text);
		const segments: Segment[] = data.segments || [];

		if (segments.length === 0) {
			return 0;
		}

		// Compute hash for cache invalidation
		const segmentText = segments.map((s) => `${s.source}|${s.target}`).join('\n');
		const fileHash = computeHash(segmentText);

		// Check if already indexed with same hash
		if (indexedFiles.get(filePath) === fileHash) {
			console.log('RAG: File already indexed, skipping:', filePath);
			return segments.length;
		}

		// Index segments
		const count = await ragIndex(filePath, fileHash, segments);
		indexedFiles.set(filePath, fileHash);

		// Update total indexed count
		ragIndexedSegments.update((n) => n + count);

		console.log(`RAG: Indexed ${count} segments from ${filePath}`);
		return count;
	} catch (error) {
		console.error('RAG indexing failed:', error);
		ragError.set(error instanceof Error ? error.message : 'Indexing failed');
		return 0;
	} finally {
		ragIndexing.set(false);
	}
}

/**
 * Search for relevant segments
 */
export async function searchSegments(
	filePath: string,
	query: string,
	limit = 10
): Promise<SearchResult[]> {
	if (!get(ragEnabled) || !get(ragInitialized)) {
		return [];
	}

	try {
		// Ensure file is indexed
		if (!indexedFiles.has(filePath)) {
			await indexFile(filePath);
		}

		const results = await ragSearch(filePath, query, limit);
		console.log(`RAG: Found ${results.length} segments for query: "${query}"`);
		return results;
	} catch (error) {
		console.error('RAG search failed:', error);
		ragError.set(error instanceof Error ? error.message : 'Search failed');
		return [];
	}
}

/**
 * Clear index for a file
 */
export async function clearFileIndex(filePath: string): Promise<void> {
	await ragClear(filePath);
	indexedFiles.delete(filePath);
}

/**
 * Get RAG statistics
 */
export async function getIndexStats(): Promise<Record<string, number>> {
	return ragStats();
}

/**
 * Format RAG results as context for Claude
 */
export function formatRagContext(results: SearchResult[]): string {
	if (results.length === 0) return '';

	const lines = results.map((r) => {
		const segment = r.segment;
		return `[Segment ${segment.id}] (relevance: ${(r.score * 100).toFixed(0)}%)
  Source: ${segment.source}
  Target: ${segment.target}
  Status: ${segment.status}`;
	});

	return `Relevant segments from RAG search:\n${lines.join('\n\n')}`;
}