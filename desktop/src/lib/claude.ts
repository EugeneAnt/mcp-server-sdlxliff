import Anthropic from '@anthropic-ai/sdk';
import { fetch } from '@tauri-apps/plugin-http';

let anthropicClient: Anthropic | null = null;

export function initializeClient(apiKey: string) {
	// Use Tauri's fetch to bypass CORS restrictions
	// dangerouslyAllowBrowser required for browser-like environments
	anthropicClient = new Anthropic({
		apiKey,
		dangerouslyAllowBrowser: true,
		fetch: fetch as unknown as typeof globalThis.fetch
	});
}

export function getClient(): Anthropic {
	if (!anthropicClient) {
		throw new Error('AI provider not initialized. Please set your API key.');
	}
	return anthropicClient;
}

export function isClientInitialized(): boolean {
	return anthropicClient !== null;
}

export interface ToolUseBlock {
	type: 'tool_use';
	id: string;
	name: string;
	input: Record<string, unknown>;
}

export interface ConversationMessage {
	role: 'user' | 'assistant';
	content: string;
}

export interface TokenUsage {
	inputTokens: number;
	outputTokens: number;
	cacheReadTokens?: number;
	cacheWriteTokens?: number;
}

export interface StreamEvent {
	type: 'text' | 'tool_use' | 'tool_result' | 'done' | 'error' | 'usage';
	content?: string;
	toolUse?: ToolUseBlock;
	error?: string;
	usage?: TokenUsage;
}

/**
 * Build tools array with cache control on the last tool
 * This creates a cache breakpoint that includes system + tools
 */
function buildToolsWithCache(mcpTools: Anthropic.Tool[]): Anthropic.Tool[] {
	return mcpTools.map((tool, index) => {
		const isLastTool = index === mcpTools.length - 1;
		if (isLastTool) {
			// Add cache control to the last tool
			return {
				...tool,
				cache_control: { type: 'ephemeral' as const }
			};
		}
		return tool;
	});
}

/**
 * Convert conversation messages to Anthropic format
 */
function buildMessages(
	messages: ConversationMessage[]
): Anthropic.MessageParam[] {
	return messages.map((m) => ({
		role: m.role,
		content: m.content
	}));
}

/**
 * Build system prompt with cache control
 */
function buildSystemWithCache(
	systemPrompt: string
): Anthropic.TextBlockParam[] {
	return [
		{
			type: 'text',
			text: systemPrompt,
			cache_control: { type: 'ephemeral' }
		}
	];
}

export async function* streamChatWithTools(
	messages: ConversationMessage[],
	systemPrompt: string,
	mcpTools?: Anthropic.Tool[],
	onToolCall?: (toolUse: ToolUseBlock) => Promise<string>
): AsyncGenerator<StreamEvent> {
	const client = getClient();

	console.log('[streamChatWithTools] Starting with', messages.length, 'messages');
	console.log('[streamChatWithTools] Tools:', mcpTools?.map((t) => t.name));

	// Build tools with cache control on last tool
	const tools = mcpTools?.length ? buildToolsWithCache(mcpTools) : undefined;

	// Build system prompt with cache control
	const system = buildSystemWithCache(systemPrompt);

	// Convert messages
	let anthropicMessages = buildMessages(messages);

	// Agentic loop - continue until no more tool calls
	let continueLoop = true;
	let totalUsage: TokenUsage = {
		inputTokens: 0,
		outputTokens: 0,
		cacheReadTokens: 0,
		cacheWriteTokens: 0
	};

	while (continueLoop) {
		try {
			console.log('[streamChatWithTools] Making API call...');

			const stream = await client.messages.stream({
				model: 'claude-sonnet-4-20250514',
				max_tokens: 8192,
				system,
				messages: anthropicMessages,
				tools
			});

			let currentText = '';
			const toolCalls: ToolUseBlock[] = [];
			let currentToolUse: Partial<ToolUseBlock> | null = null;
			let toolInputJson = '';

			// Process stream events
			for await (const event of stream) {
				if (event.type === 'content_block_start') {
					if (event.content_block.type === 'text') {
						currentText = '';
					} else if (event.content_block.type === 'tool_use') {
						currentToolUse = {
							type: 'tool_use',
							id: event.content_block.id,
							name: event.content_block.name,
							input: {}
						};
						toolInputJson = '';
					}
				} else if (event.type === 'content_block_delta') {
					if (event.delta.type === 'text_delta') {
						currentText += event.delta.text;
						yield { type: 'text', content: event.delta.text };
					} else if (event.delta.type === 'input_json_delta') {
						toolInputJson += event.delta.partial_json;
					}
				} else if (event.type === 'content_block_stop') {
					if (currentToolUse && toolInputJson) {
						try {
							currentToolUse.input = JSON.parse(toolInputJson);
						} catch {
							currentToolUse.input = {};
						}
						toolCalls.push(currentToolUse as ToolUseBlock);
						currentToolUse = null;
						toolInputJson = '';
					}
				} else if (event.type === 'message_delta') {
					// Message finished - check stop reason
					if (event.delta.stop_reason === 'end_turn') {
						continueLoop = false;
					}
				} else if (event.type === 'message_start') {
					// Extract usage from message start
					const usage = event.message.usage;
					if (usage) {
						totalUsage.inputTokens += usage.input_tokens || 0;
						totalUsage.cacheReadTokens =
							(totalUsage.cacheReadTokens || 0) +
							(usage.cache_read_input_tokens || 0);
						totalUsage.cacheWriteTokens =
							(totalUsage.cacheWriteTokens || 0) +
							(usage.cache_creation_input_tokens || 0);
					}
				}
			}

			// Get final message for output tokens
			const finalMessage = await stream.finalMessage();
			totalUsage.outputTokens += finalMessage.usage?.output_tokens || 0;

			// Log usage for this turn
			console.log('[Token Usage - Turn]', {
				input: finalMessage.usage?.input_tokens,
				output: finalMessage.usage?.output_tokens,
				cacheRead: finalMessage.usage?.cache_read_input_tokens || 0,
				cacheWrite: finalMessage.usage?.cache_creation_input_tokens || 0
			});

			// Handle tool calls if any
			if (toolCalls.length > 0 && onToolCall) {
				console.log('[streamChatWithTools] Processing', toolCalls.length, 'tool calls');

				// Add assistant message with tool use
				const assistantContent: Anthropic.ContentBlockParam[] = [];
				if (currentText) {
					assistantContent.push({ type: 'text', text: currentText });
				}
				for (const tc of toolCalls) {
					assistantContent.push({
						type: 'tool_use',
						id: tc.id,
						name: tc.name,
						input: tc.input
					});
				}
				anthropicMessages = [
					...anthropicMessages,
					{ role: 'assistant', content: assistantContent }
				];

				// Execute tools and collect results
				const toolResults: Anthropic.ToolResultBlockParam[] = [];
				for (const tc of toolCalls) {
					yield { type: 'tool_use', toolUse: tc };
					const result = await onToolCall(tc);
					yield { type: 'tool_result', content: result.slice(0, 500) + '...' };
					toolResults.push({
						type: 'tool_result',
						tool_use_id: tc.id,
						content: result
					});
				}

				// Add tool results as user message
				anthropicMessages = [
					...anthropicMessages,
					{ role: 'user', content: toolResults }
				];

				// Continue the loop for next turn
				continueLoop = true;
			} else {
				// No tool calls, we're done
				continueLoop = false;
			}
		} catch (error) {
			console.error('[streamChatWithTools] Error:', error);
			yield {
				type: 'error',
				error: error instanceof Error ? error.message : 'An error occurred'
			};
			continueLoop = false;
		}
	}

	// Yield final usage
	console.log('[Token Usage - Total]', {
		input: totalUsage.inputTokens,
		output: totalUsage.outputTokens,
		cacheRead: totalUsage.cacheReadTokens || 0,
		cacheWrite: totalUsage.cacheWriteTokens || 0
	});

	yield { type: 'usage', usage: totalUsage };
	yield { type: 'done' };
}