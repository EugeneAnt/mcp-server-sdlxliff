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
	clearApiKey as clearStoredApiKey
} from '$lib/stores/settings';

const systemPrompt = `You are an SDLXLIFF translation assistant. You help users translate and edit SDLXLIFF files.

You have access to MCP tools that allow you to:
- read_sdlxliff: Read and extract segments from SDLXLIFF files
- get_sdlxliff_segment: Get a specific segment by ID
- update_sdlxliff_segment: Update a translation
- save_sdlxliff: Save changes to the file
- get_sdlxliff_statistics: Get file statistics
- validate_sdlxliff_segment: Validate a translation before updating
- qa_check_sdlxliff: Run QA checks on translations

When working with SDLXLIFF files:
1. First use get_sdlxliff_statistics to understand the file
2. Use read_sdlxliff to get segments (paginated, max 50 per request)
3. Use update_sdlxliff_segment to update translations
4. Use save_sdlxliff to persist changes

Be helpful and concise. Preserve formatting and tags in translations.`;

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
		} catch (error) {
			console.error('Failed to initialize from stored key:', error);
			await clearStoredApiKey();
			showApiKeyInput.set(true);
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
}

async function handleToolCall(toolUse: ToolUseBlock): Promise<string> {
	const client = getMcpClient();
	if (!client) {
		throw new Error('MCP server not connected');
	}

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

	const result = await client.callTool(toolUse.name, toolUse.input);
	const resultText = result.content.map((c) => c.text || JSON.stringify(c)).join('\n');

	toolCalls.updateToolResponse(toolCallId, resultText);

	return resultText;
}

export async function sendMessage(): Promise<void> {
	const input = get(inputValue).trim();
	if (!input || get(isLoading)) return;

	const userMessage = input;
	inputValue.set('');
	shouldAutoScroll.set(true);

	const paths = get(selectedPaths);
	const contextPrefix =
		paths.length > 0
			? `[Working with ${paths.length} file${paths.length > 1 ? 's' : ''}:\n${paths.map((p) => `- ${p}`).join('\n')}]\n\n`
			: '';
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
		const tools = connected ? get(mcpTools) : [];
		const model = get(selectedModel);
		const messages = get(conversationMessages);

		for await (const event of streamChatWithTools(
			messages,
			systemPrompt,
			tools,
			connected ? handleToolCall : undefined,
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
