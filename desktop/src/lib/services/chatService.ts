import { get, writable } from 'svelte/store';
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
	addIssue,
	addIssues,
	clearIssues,
	getIssueCounts,
	getApplicableIssues,
	markIssueApplied,
	type Issue
} from '$lib/stores/issues';
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

## Available Tools

- read_sdlxliff: Read segments (paginated, max 50 per request)
- get_sdlxliff_segment: Get a specific segment by ID (includes tags)
- update_sdlxliff_segment: Update a single segment directly (use sparingly)
- save_sdlxliff: Save changes to file
- get_sdlxliff_statistics: Get file statistics and language info
- qa_check_sdlxliff: Run regex-based QA checks (issues auto-tracked)
- rag_search: Semantic search to find segments by meaning
- add_issue_to_report: Log issues with suggested fixes to Issues panel
- apply_pending_fixes: Batch apply all non-skipped fixes from Issues panel

## Workflow

1. **Check translations**: Use qa_check_sdlxliff and/or read segments
2. **Identify issues**: Use add_issue_to_report with suggested_fix (FULL target text with tags)
3. **Discuss with user**: Refine fixes as needed (updates existing issue for same segment)
4. **Apply edits**: When user asks to apply/save, call apply_pending_fixes

## Important: How to Report Issues

When you find a problem that needs fixing, use add_issue_to_report with:
- suggested_fix: The COMPLETE new target text (not a description, the actual text)
- If segment has tags, include them: "Он также {49}запустил{/49} новый проект"
- One fix per segment (later fixes update earlier ones)

Example:
  add_issue_to_report({
    segment_id: "7",
    issue_type: "spelling",
    message: "Spelling error: инвестеционной → инвестиционной",
    suggested_fix: "Полный текст перевода с исправленной ошибкой здесь",
    severity: "error"
  })

## Tool Usage Strategy

**For TARGETED queries**: Use rag_search("term or concept")
**For QA checks**: Use qa_check_sdlxliff (issues auto-populate)
**For COMPREHENSIVE review**: Ask user preference, then read in batches

## DO NOT

- Do NOT call update_sdlxliff_segment directly unless user explicitly asks for immediate single edit
- Instead, collect issues via add_issue_to_report, then apply_pending_fixes when ready
- This lets users review and skip false positives before applying

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

// Issue tracking tool (handled by frontend, not MCP)
const addIssueToolDefinition = {
	name: 'add_issue_to_report',
	description:
		'Log a translation issue to the session tracker. Use when you find actionable problems during review. Issues are tracked in the Issues Panel and can be exported.',
	input_schema: {
		type: 'object' as const,
		properties: {
			segment_id: {
				type: 'string',
				description: 'The segment ID with the issue'
			},
			issue_type: {
				type: 'string',
				enum: ['semantic', 'grammar', 'terminology', 'style', 'punctuation', 'numbers', 'formatting', 'inconsistency', 'other'],
				description: 'Category of the issue'
			},
			severity: {
				type: 'string',
				enum: ['error', 'warning', 'info'],
				description: 'Issue severity (default: warning)'
			},
			message: {
				type: 'string',
				description: 'Description of the issue'
			},
			suggested_fix: {
				type: 'string',
				description: 'Optional suggested correction'
			},
			source: {
				type: 'string',
				description: 'Source text excerpt (optional)'
			},
			target: {
				type: 'string',
				description: 'Target text excerpt (optional)'
			}
		},
		required: ['segment_id', 'issue_type', 'message']
	}
};

// Apply pending fixes tool (LLM calls this to batch-apply from Issues panel)
const applyPendingFixesToolDefinition = {
	name: 'apply_pending_fixes',
	description:
		'Apply all pending fixes from the Issues panel. Reads non-skipped issues with suggested_fix, validates each, updates segments, and saves the file. Call this when user asks to "apply edits", "make the fixes", or "save corrections".',
	input_schema: {
		type: 'object' as const,
		properties: {
			file_path: {
				type: 'string',
				description: 'Path to the SDLXLIFF file to update'
			}
		},
		required: ['file_path']
	}
};

// State for UI feedback
export const isApplyingFixes = writable(false);

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
	// Clear issues for new session
	clearIssues();
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
	} else if (toolUse.name === 'add_issue_to_report') {
		// Handle issue tracking locally
		resultText = handleAddIssue(toolUse.input as {
			segment_id: string;
			issue_type: string;
			severity?: 'error' | 'warning' | 'info';
			message: string;
			suggested_fix?: string;
			source?: string;
			target?: string;
		});
	} else if (toolUse.name === 'apply_pending_fixes') {
		// Handle batch apply from Issues panel
		resultText = await handleApplyPendingFixes(toolUse.input as { file_path: string });
	} else {
		// Handle MCP tools
		const client = getMcpClient();
		if (!client) {
			throw new Error('MCP server not connected');
		}
		const result = await client.callTool(toolUse.name, toolUse.input);
		resultText = result.content.map((c) => c.text || JSON.stringify(c)).join('\n');

		// Auto-populate issues from QA tool
		if (toolUse.name === 'qa_check_sdlxliff') {
			autoPopulateIssuesFromQA(resultText);
		}
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

/**
 * Handle add_issue_to_report tool call (local, not MCP)
 */
function handleAddIssue(input: {
	segment_id: string;
	issue_type: string;
	severity?: 'error' | 'warning' | 'info';
	message: string;
	suggested_fix?: string;
	source?: string;
	target?: string;
}): string {
	addIssue({
		segment_id: input.segment_id,
		issue_type: input.issue_type,
		severity: input.severity || 'warning',
		message: input.message,
		suggested_fix: input.suggested_fix,
		source: input.source || '',
		target: input.target || '',
		source_tool: 'manual_review'
	});

	const counts = getIssueCounts();
	return JSON.stringify({ ok: true, total: counts.total });
}

/**
 * Handle apply_pending_fixes tool call - batch apply from Issues panel
 */
async function handleApplyPendingFixes(input: { file_path: string }): Promise<string> {
	const { file_path } = input;
	const client = getMcpClient();

	if (!client) {
		return JSON.stringify({ error: 'MCP server not connected' });
	}

	const applicableIssues = getApplicableIssues();

	if (applicableIssues.length === 0) {
		return JSON.stringify({
			applied: 0,
			message: 'No applicable issues found. Issues must have suggested_fix and not be skipped.'
		});
	}

	isApplyingFixes.set(true);

	const results: { segment_id: string; status: 'success' | 'error'; message?: string }[] = [];

	try {
		// Apply each fix
		for (const issue of applicableIssues) {
			try {
				// Validate first (optional - check if tags are preserved)
				const validateResult = await client.callTool('validate_sdlxliff_segment', {
					file_path,
					segment_id: issue.segment_id,
					new_target: issue.suggested_fix
				});
				const validation = JSON.parse(validateResult.content[0].text || '{}');

				if (!validation.valid) {
					results.push({
						segment_id: issue.segment_id,
						status: 'error',
						message: `Validation failed: ${validation.errors?.join(', ') || 'unknown error'}`
					});
					continue;
				}

				// Apply the fix
				await client.callTool('update_sdlxliff_segment', {
					file_path,
					segment_id: issue.segment_id,
					target_text: issue.suggested_fix
				});

				// Mark as applied
				markIssueApplied(issue.id);
				results.push({ segment_id: issue.segment_id, status: 'success' });
			} catch (err) {
				results.push({
					segment_id: issue.segment_id,
					status: 'error',
					message: err instanceof Error ? err.message : 'Unknown error'
				});
			}
		}

		// Save the file once after all updates
		const successCount = results.filter((r) => r.status === 'success').length;
		if (successCount > 0) {
			await client.callTool('save_sdlxliff', { file_path });
		}

		const response = {
			applied: successCount,
			failed: results.filter((r) => r.status === 'error').length,
			total: applicableIssues.length,
			results,
			message: successCount > 0 ? `Applied ${successCount} fixes and saved file.` : 'No fixes applied.'
		};

		return JSON.stringify(response, null, 2);
	} finally {
		isApplyingFixes.set(false);
	}
}

/**
 * Exported function for UI "Apply All" button (alternative to LLM tool call)
 */
export async function applyAllFixes(): Promise<void> {
	const paths = get(selectedPaths);
	if (paths.length === 0) {
		alert('No file selected');
		return;
	}

	const result = await handleApplyPendingFixes({ file_path: paths[0] });
	const parsed = JSON.parse(result);

	if (parsed.error) {
		alert(`Error: ${parsed.error}`);
	} else if (parsed.applied > 0) {
		alert(`Applied ${parsed.applied} fixes and saved.`);
	} else {
		alert(parsed.message || 'No fixes to apply.');
	}
}

/**
 * Auto-populate issues from QA tool response
 */
function autoPopulateIssuesFromQA(resultText: string): void {
	try {
		const qaResult = JSON.parse(resultText);
		if (!qaResult.issues || !Array.isArray(qaResult.issues)) return;

		const issues: Omit<Issue, 'id' | 'timestamp' | 'skipped' | 'applied'>[] = qaResult.issues.map(
			(issue: {
				segment_id: string;
				check: string;
				severity: string;
				message: string;
				source_excerpt?: string;
				target_excerpt?: string;
			}) => ({
				segment_id: issue.segment_id,
				issue_type: `qa_${issue.check}`,
				severity: (issue.severity || 'warning') as 'error' | 'warning' | 'info',
				message: issue.message,
				source: issue.source_excerpt || '',
				target: issue.target_excerpt || '',
				source_tool: 'qa_check' as const
			})
		);

		if (issues.length > 0) {
			addIssues(issues);
			console.log(`Auto-populated ${issues.length} issues from QA check`);
		}
	} catch (e) {
		// Ignore parse errors - not all tool results are JSON
		console.warn('Failed to parse QA result for issue tracking:', e);
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

		// Add issue tracking and apply tools (always available when MCP connected)
		if (connected) {
			tools.push(addIssueToolDefinition);
			tools.push(applyPendingFixesToolDefinition);
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
