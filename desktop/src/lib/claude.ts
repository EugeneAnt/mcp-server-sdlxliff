import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

export interface ToolUseBlock {
	type: 'tool_use';
	id: string;
	name: string;
	input: Record<string, unknown>;
}

export interface ConversationMessage {
	role: 'user' | 'assistant';
	content: string | ContentBlock[];
}

export interface ContentBlock {
	type: string;
	text?: string;
	id?: string;
	name?: string;
	input?: Record<string, unknown>;
	tool_use_id?: string;
	content?: string;
}

export interface TokenUsage {
	inputTokens: number;
	outputTokens: number;
	cacheReadTokens?: number;
	cacheWriteTokens?: number;
}

export interface StreamEvent {
	type: 'text' | 'tool_use' | 'tool_result' | 'done' | 'error' | 'usage' | 'model_selected';
	content?: string;
	toolUse?: ToolUseBlock;
	error?: string;
	usage?: TokenUsage;
}

export type ModelChoice = 'haiku' | 'sonnet';

interface ChatEvent {
	event_type: string;
	content?: string;
	tool_use?: {
		id: string;
		name: string;
		input: Record<string, unknown>;
	};
	usage?: {
		input_tokens: number;
		output_tokens: number;
		cache_read_tokens?: number;
		cache_write_tokens?: number;
	};
	error?: string;
}

interface Tool {
	name: string;
	description: string;
	input_schema: Record<string, unknown>;
}

// API key is now managed by Rust - these functions sync with Rust state
export async function initializeClient(apiKey: string): Promise<void> {
	await invoke('set_api_key', { key: apiKey });
}

export async function clearClient(): Promise<void> {
	await invoke('clear_api_key');
}

export async function isClientInitialized(): Promise<boolean> {
	return await invoke<boolean>('has_api_key');
}

export async function* streamChatWithTools(
	messages: ConversationMessage[],
	systemPrompt: string,
	mcpTools?: Tool[],
	onToolCall?: (toolUse: ToolUseBlock) => Promise<string>,
	model: ModelChoice = 'sonnet'
): AsyncGenerator<StreamEvent> {
	const streamId = crypto.randomUUID();
	const eventName = `chat-event-${streamId}`;

	// Convert messages to the format Rust expects
	const rustMessages = messages.map((m) => ({
		role: m.role,
		content: m.content
	}));

	// Set up event listener
	const events: StreamEvent[] = [];
	let resolve: (() => void) | null = null;
	let done = false;

	const unlisten = await listen<ChatEvent>(eventName, (event) => {
		const payload = event.payload;

		if (payload.event_type === 'model_selected' && payload.content) {
			events.push({ type: 'model_selected', content: payload.content });
		} else if (payload.event_type === 'text' && payload.content) {
			events.push({ type: 'text', content: payload.content });
		} else if (payload.event_type === 'tool_use' && payload.tool_use) {
			events.push({
				type: 'tool_use',
				toolUse: {
					type: 'tool_use',
					id: payload.tool_use.id,
					name: payload.tool_use.name,
					input: payload.tool_use.input
				}
			});
		} else if (payload.event_type === 'usage' && payload.usage) {
			events.push({
				type: 'usage',
				usage: {
					inputTokens: payload.usage.input_tokens,
					outputTokens: payload.usage.output_tokens,
					cacheReadTokens: payload.usage.cache_read_tokens,
					cacheWriteTokens: payload.usage.cache_write_tokens
				}
			});
		} else if (payload.event_type === 'done') {
			events.push({ type: 'done' });
			done = true;
		} else if (payload.event_type === 'error' && payload.error) {
			events.push({ type: 'error', error: payload.error });
			done = true;
		}

		if (resolve) {
			resolve();
			resolve = null;
		}
	});

	try {
		// Start the stream
		console.time('chat_stream:invoke');
		const requestPayload = {
			request: {
				messages: rustMessages,
				system_prompt: systemPrompt,
				tools: mcpTools,
				stream_id: streamId,
				model: model
			}
		};
		console.log(`chat_stream: ${rustMessages.length} messages, payload size: ${JSON.stringify(requestPayload).length} bytes`);
		await invoke('chat_stream', requestPayload);
		console.timeEnd('chat_stream:invoke');

		// Yield events as they arrive
		while (!done || events.length > 0) {
			if (events.length > 0) {
				const event = events.shift()!;

				// Handle tool calls with the agentic loop
				if (event.type === 'tool_use' && event.toolUse && onToolCall) {
					yield event;

					// Execute the tool
					console.time(`tool:${event.toolUse.name}`);
					const result = await onToolCall(event.toolUse);
					console.timeEnd(`tool:${event.toolUse.name}`);
					console.log(`Tool ${event.toolUse.name} result size: ${result.length} bytes`);
					yield { type: 'tool_result', content: result.slice(0, 500) + '...' };

					// Continue the conversation with tool result
					const updatedMessages: ConversationMessage[] = [
						...messages,
						{
							role: 'assistant',
							content: [
								{
									type: 'tool_use',
									id: event.toolUse.id,
									name: event.toolUse.name,
									input: event.toolUse.input
								}
							]
						},
						{
							role: 'user',
							content: [
								{
									type: 'tool_result',
									tool_use_id: event.toolUse.id,
									content: result
								}
							]
						}
					];

					// Recursively continue the conversation with same model
					for await (const continuedEvent of streamChatWithTools(
						updatedMessages,
						systemPrompt,
						mcpTools,
						onToolCall,
						model
					)) {
						yield continuedEvent;
					}
					return;
				}

				yield event;

				if (event.type === 'done' || event.type === 'error') {
					return;
				}
			} else if (!done) {
				// Wait for more events
				await new Promise<void>((r) => {
					resolve = r;
				});
			}
		}
	} finally {
		unlisten();
	}
}