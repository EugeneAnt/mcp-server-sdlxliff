import { streamText, tool, jsonSchema, stepCountIs, type ModelMessage } from 'ai';
import { createAnthropic } from '@ai-sdk/anthropic';
import { fetch } from '@tauri-apps/plugin-http';
import type Anthropic from '@anthropic-ai/sdk';

let anthropicProvider: ReturnType<typeof createAnthropic> | null = null;

export function initializeClient(apiKey: string) {
	// Use Tauri's fetch to bypass CORS restrictions
	// Add header required for direct browser access
	anthropicProvider = createAnthropic({
		apiKey,
		fetch: fetch as unknown as typeof globalThis.fetch,
		headers: {
			'anthropic-dangerous-direct-browser-access': 'true'
		}
	});
}

export function getProvider() {
	if (!anthropicProvider) {
		throw new Error('AI provider not initialized. Please set your API key.');
	}
	return anthropicProvider;
}

export function isClientInitialized(): boolean {
	return anthropicProvider !== null;
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

export interface StreamEvent {
	type: 'text' | 'tool_use' | 'tool_result' | 'done' | 'error';
	content?: string;
	toolUse?: ToolUseBlock;
	error?: string;
}

/**
 * Build tools object for AI SDK from MCP tools
 */
function buildTools(
	mcpTools: Anthropic.Tool[],
	onToolCall?: (toolUse: ToolUseBlock) => Promise<string>
) {
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const tools: Record<string, any> = {};

	for (const mcpTool of mcpTools) {
		tools[mcpTool.name] = tool({
			description: mcpTool.description || '',
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			inputSchema: jsonSchema<any>(mcpTool.input_schema as any),
			execute: async (args: unknown) => {
				console.log(`[Tool Execute] ${mcpTool.name}`, args);
				if (!onToolCall) return 'Tool execution not configured';
				const toolUse: ToolUseBlock = {
					type: 'tool_use',
					id: crypto.randomUUID(),
					name: mcpTool.name,
					input: args as Record<string, unknown>
				};
				const result = await onToolCall(toolUse);
				console.log(`[Tool Result] ${mcpTool.name}`, result.slice(0, 200));
				return result;
			}
		});
	}

	return tools;
}

export async function* streamChatWithTools(
	messages: ConversationMessage[],
	systemPrompt: string,
	mcpTools?: Anthropic.Tool[],
	onToolCall?: (toolUse: ToolUseBlock) => Promise<string>
): AsyncGenerator<StreamEvent> {
	const provider = getProvider();
	const model = provider('claude-sonnet-4-20250514');

	console.log('[streamChatWithTools] Starting with', messages.length, 'messages');
	console.log('[streamChatWithTools] Tools:', mcpTools?.map((t) => t.name));

	const tools = mcpTools?.length ? buildTools(mcpTools, onToolCall) : undefined;

	const modelMessages: ModelMessage[] = messages.map((m) => ({
		role: m.role,
		content: m.content
	}));

	try {
		console.log('[streamChatWithTools] Calling streamText...');

		const result = streamText({
			model,
			system: systemPrompt,
			messages: modelMessages,
			tools,
			stopWhen: stepCountIs(10),
			providerOptions: {
				anthropic: {
					cacheControl: { type: 'ephemeral' }
				}
			},
			onStepFinish: ({ text, toolCalls, toolResults }) => {
				console.log('[onStepFinish] text length:', text?.length);
				console.log('[onStepFinish] toolCalls:', toolCalls?.length);
				console.log('[onStepFinish] toolResults:', toolResults?.length);
			}
		});

		console.log('[streamChatWithTools] Got result, starting to stream...');

		// Stream all text
		let chunkCount = 0;
		for await (const textPart of result.textStream) {
			chunkCount++;
			if (textPart) {
				console.log(`[Stream chunk ${chunkCount}]`, textPart.slice(0, 50));
				yield { type: 'text', content: textPart };
			}
		}

		console.log('[streamChatWithTools] Stream finished, total chunks:', chunkCount);
		yield { type: 'done' };
	} catch (error) {
		console.error('[streamChatWithTools] Error:', error);
		yield {
			type: 'error',
			error: error instanceof Error ? error.message : 'An error occurred'
		};
	}
}