import { get } from 'svelte/store';
import {
	initializeClient,
	clearClient,
	streamChatWithTools,
	type ToolUseBlock,
	type ConversationMessage
} from '$lib/claude';
import { connectMcpServer, disconnectMcpServer, getMcpClient } from '$lib/mcp-client';
import {
	displayMessages,
	toolCalls,
	conversationMessages,
	isLoading,
	inputValue,
	sessionUsage,
	lastRequestUsage,
	shouldAutoScroll,
	resetChat,
	type ToolCall
} from '$lib/stores/chat';
import {
	mcpConnected,
	mcpConnecting,
	mcpError,
	mcpTools,
	resetMcp
} from '$lib/stores/mcp';
import { selectedModel, currentModelUsed } from '$lib/stores/models';
import { selectedPaths } from '$lib/stores/files';
import {
	apiKey,
	showApiKeyInput,
	getApiKey,
	setApiKey as storeApiKey,
	clearApiKey as clearStoredApiKey,
	ragEnabled
} from '$lib/stores/settings';
import {
	initializeRag,
	indexFile,
	searchSegments,
	formatRagContext,
	ragInitialized,
	ragLastContext,
	ragLastSearchResults,
	ragInjectedContext,
	ragSearchCount,
	ragTokensUsed
} from '$lib/services/ragService';

const systemPrompt = `You are an SDLXLIFF translation assistant. You help users translate and edit SDLXLIFF files.

You have access to MCP tools that allow you to:
- read_sdlxliff: Read and extract segments from SDLXLIFF files
- get_sdlxliff_segment: Get a specific segment by ID
- update_sdlxliff_segment: Update a translation
- save_sdlxliff: Save changes to the file
- get_sdlxliff_statistics: Get file statistics
- validate_sdlxliff_segment: Validate a translation before updating
- qa_check_sdlxliff: Run QA checks on translations
- rag_search: Semantic search to find segments by meaning (use for "find segments about X", "show translations related to Y")

When working with SDLXLIFF files:
1. First use get_sdlxliff_statistics to understand the file
2. Use read_sdlxliff to get segments (paginated, max 50 per request)
3. Use rag_search when user asks to FIND or SEARCH for specific content by meaning
4. Use update_sdlxliff_segment to update translations
5. Use save_sdlxliff to persist changes

Be helpful and concise. Preserve formatting and tags in translations.`;

// RAG tool definition (handled by frontend, not MCP)
const ragToolDefinition = {
	name: 'rag_search',
	description:
		'Semantic search to find translation segments by meaning. Use this when the user asks to find, search, or show segments related to a topic. Returns segments ranked by relevance score.',
	input_schema: {
		type: 'object' as const,
		properties: {
			query: {
				type: 'string',
				description: 'Natural language search query (e.g., "30th anniversary", "digital technologies")'
			},
			limit: {
				type: 'number',
				description: 'Maximum number of results to return (default: 5)'
			}
		},
		required: ['query']
	}
};

// Scroll callbacks - set by components
let scrollMessagesCallback: (() => void) | null = null;
let scrollToolsCallback: (() => void) | null = null;

export function setScrollCallbacks(
	messagesScroll: () => void,
	toolsScroll: () => void
): void {
	scrollMessagesCallback = messagesScroll;
	scrollToolsCallback = toolsScroll;
}

export async function initializeApp(): Promise<void> {
	const storedKey = await getApiKey();
	if (storedKey) {
		try {
			apiKey.set(storedKey);
			await initializeClient(storedKey);
			showApiKeyInput.set(false);
			await tryConnectMcp();
			// Initialize RAG (non-blocking)
			initializeRag().catch((e) => console.warn('RAG init failed:', e));
		} catch (error) {
			console.error('Failed to initialize from stored key:', error);
			await clearStoredApiKey();
			showApiKeyInput.set(true);
		}
	}
}

/**
 * Index selected files for RAG search (call when files are selected)
 */
export async function indexSelectedFiles(): Promise<void> {
	if (!get(ragEnabled) || !get(ragInitialized)) return;

	const paths = get(selectedPaths);
	for (const path of paths) {
		try {
			await indexFile(path);
		} catch (error) {
			console.warn('Failed to index file for RAG:', path, error);
		}
	}
}

export async function cleanupApp(): Promise<void> {
	await disconnectMcpServer();
}

export async function tryConnectMcp(): Promise<void> {
	mcpConnecting.set(true);
	mcpError.set('');
	mcpConnected.set(false);

	try {
		await disconnectMcpServer();
	} catch {
		// Ignore disconnect errors
	}

	try {
		const client = await connectMcpServer();
		mcpConnected.set(client.isConnected());
		mcpTools.set(client.getToolsForClaude());
		console.log('MCP connected, tools:', get(mcpTools).map((t) => t.name));
	} catch (error) {
		if (error instanceof Error) {
			mcpError.set(error.message);
		} else if (typeof error === 'string') {
			mcpError.set(error);
		} else {
			mcpError.set(JSON.stringify(error));
		}
		mcpConnected.set(false);
		console.error('MCP connection failed:', error);
	}
	mcpConnecting.set(false);
}

export async function saveApiKey(): Promise<void> {
	const key = get(apiKey).trim();
	if (key) {
		try {
			await storeApiKey(key);
			await initializeClient(key);
			showApiKeyInput.set(false);
			tryConnectMcp();
		} catch (error) {
			console.error('Failed to initialize client:', error);
			alert(
				'Failed to initialize: ' +
					(error instanceof Error ? error.message : 'Unknown error')
			);
		}
	}
}

export async function clearApiKeyAndLogout(): Promise<void> {
	await clearStoredApiKey();
	await clearClient();
	apiKey.set('');
	showApiKeyInput.set(true);
	disconnectMcpServer();
	resetMcp();
}

export function startNewChat(): void {
	resetChat();
	currentModelUsed.set(null);
	// Reset RAG session stats
	ragSearchCount.set(0);
	ragTokensUsed.set(0);
	ragLastContext.set([]);
	ragLastSearchResults.set(0);
	ragInjectedContext.set('');
}

async function handleToolCall(toolUse: ToolUseBlock): Promise<string> {
	const toolCallId = crypto.randomUUID();
	toolCalls.addToolCall({
		id: toolCallId,
		name: toolUse.name,
		request: toolUse.input
	});

	// Auto-scroll tools panel
	setTimeout(() => {
		if (scrollToolsCallback) scrollToolsCallback();
	}, 0);

	let resultText: string;

	// Handle RAG tool locally (not via MCP)
	if (toolUse.name === 'rag_search') {
		resultText = await handleRagSearch(toolUse.input as { query: string; limit?: number });
	} else {
		// Handle MCP tools
		const client = getMcpClient();
		if (!client) {
			throw new Error('MCP server not connected');
		}
		const result = await client.callTool(toolUse.name, toolUse.input);
		resultText = result.content.map((c) => c.text || JSON.stringify(c)).join('\n');
	}

	toolCalls.updateToolResponse(toolCallId, resultText);
	return resultText;
}

/**
 * Handle RAG search tool call
 */
async function handleRagSearch(input: { query: string; limit?: number }): Promise<string> {
	const { query, limit = 5 } = input;
	const paths = get(selectedPaths);

	if (!get(ragEnabled) || !get(ragInitialized)) {
		return JSON.stringify({ error: 'RAG is not enabled or not initialized' });
	}

	if (paths.length === 0) {
		return JSON.stringify({ error: 'No files selected' });
	}

	try {
		const allResults = [];
		for (const path of paths) {
			const results = await searchSegments(path, query, limit);
			allResults.push(...results);
		}

		if (allResults.length === 0) {
			return JSON.stringify({ results: [], message: 'No matching segments found' });
		}

		// Sort by score and take top results
		allResults.sort((a, b) => b.score - a.score);
		const topResults = allResults.slice(0, limit);

		// Update stores for UI display
		ragLastContext.set(topResults);
		ragLastSearchResults.set(topResults.length);
		ragInjectedContext.set(formatRagContext(topResults));

		// Return structured results
		const response = {
			query,
			results: topResults.map((r) => ({
				segment_id: r.segment.id,
				relevance: `${(r.score * 100).toFixed(0)}%`,
				source: r.segment.source,
				target: r.segment.target,
				status: r.segment.status
			}))
		};

		const resultJson = JSON.stringify(response, null, 2);

		// Track RAG usage (~4 chars per token approximation)
		ragSearchCount.update((n) => n + 1);
		ragTokensUsed.update((n) => n + Math.ceil(resultJson.length / 4));

		return resultJson;
	} catch (error) {
		return JSON.stringify({ error: error instanceof Error ? error.message : 'RAG search failed' });
	}
}

export async function sendMessage(): Promise<void> {
	const input = get(inputValue).trim();
	if (!input || get(isLoading)) return;

	const userMessage = input;
	inputValue.set('');
	shouldAutoScroll.set(true);

	const paths = get(selectedPaths);

	// Build file context (no automatic RAG - Claude will use rag_search tool when needed)
	let contextPrefix = '';
	if (paths.length > 0) {
		contextPrefix = `[Working with ${paths.length} file${paths.length > 1 ? 's' : ''}:\n${paths.map((p) => `- ${p}`).join('\n')}]\n\n`;
	}

	// Clear previous RAG context (will be populated if Claude calls rag_search)
	ragLastContext.set([]);
	ragLastSearchResults.set(0);
	ragInjectedContext.set('');

	const messageWithContext = contextPrefix + userMessage;

	displayMessages.addUserMessage(userMessage);
	conversationMessages.update((msgs) => [
		...msgs,
		{ role: 'user', content: messageWithContext }
	]);
	isLoading.set(true);

	let assistantMessage = '';
	let assistantDisplayIndex = -1;

	try {
		const connected = get(mcpConnected);
		let tools = connected ? [...get(mcpTools)] : [];

		// Add RAG tool if enabled
		if (get(ragEnabled) && get(ragInitialized)) {
			tools.push(ragToolDefinition);
		}

		const model = get(selectedModel);
		const messages = get(conversationMessages);

		// Allow tool calls if MCP connected OR RAG is available
		const canHandleTools = connected || (get(ragEnabled) && get(ragInitialized));

		for await (const event of streamChatWithTools(
			messages,
			systemPrompt,
			tools,
			canHandleTools ? handleToolCall : undefined,
			model
		)) {
			if (event.type === 'model_selected' && event.content) {
				currentModelUsed.set(event.content);
			} else if (event.type === 'text' && event.content) {
				assistantMessage += event.content;

				if (assistantDisplayIndex === -1) {
					displayMessages.update((msgs) => [
						...msgs,
						{ role: 'assistant', content: assistantMessage, isStreaming: true }
					]);
					assistantDisplayIndex = get(displayMessages).length - 1;
				} else {
					displayMessages.updateAssistantMessage(assistantDisplayIndex, assistantMessage);
				}
			} else if (event.type === 'usage' && event.usage) {
				lastRequestUsage.set(event.usage);
				sessionUsage.update((usage) => ({
					inputTokens: usage.inputTokens + event.usage!.inputTokens,
					outputTokens: usage.outputTokens + event.usage!.outputTokens,
					cacheReadTokens:
						(usage.cacheReadTokens || 0) + (event.usage!.cacheReadTokens || 0),
					cacheWriteTokens:
						(usage.cacheWriteTokens || 0) + (event.usage!.cacheWriteTokens || 0)
				}));
			} else if (event.type === 'done') {
				if (assistantDisplayIndex !== -1) {
					displayMessages.finishStreaming(assistantDisplayIndex);
				}
				if (assistantMessage) {
					conversationMessages.update((msgs) => [
						...msgs,
						{ role: 'assistant', content: assistantMessage }
					]);
				}
			}
		}
	} catch (error) {
		const errorMessage =
			error instanceof Error ? error.message : 'An error occurred';
		displayMessages.update((msgs) => [
			...msgs,
			{ role: 'assistant', content: `Error: ${errorMessage}` }
		]);
	}

	isLoading.set(false);
}

export function formatToolName(name: string): string {
	return name
		.replace(/_/g, ' ')
		.replace(/sdlxliff/gi, 'SDLXLIFF')
		.replace(/\b\w/g, (c) => c.toUpperCase());
}
