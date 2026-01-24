import { writable, derived } from 'svelte/store';
import type { TokenUsage, ConversationMessage } from '$lib/claude';

export interface DisplayMessage {
	role: 'user' | 'assistant';
	content: string;
	isStreaming?: boolean;
}

export interface ToolCall {
	id: string;
	name: string;
	request: Record<string, unknown>;
	response: string | null;
	isLoading: boolean;
	isExpanded: boolean;
}

function createDisplayMessagesStore() {
	const { subscribe, set, update } = writable<DisplayMessage[]>([]);

	return {
		subscribe,
		set,
		update,
		addUserMessage: (content: string) => {
			update((messages) => [...messages, { role: 'user', content }]);
		},
		addAssistantMessage: (content: string, isStreaming = false) => {
			update((messages) => [...messages, { role: 'assistant', content, isStreaming }]);
			return get(displayMessages).length - 1;
		},
		updateAssistantMessage: (index: number, content: string) => {
			update((messages) =>
				messages.map((m, i) => (i === index ? { ...m, content } : m))
			);
		},
		finishStreaming: (index: number) => {
			update((messages) =>
				messages.map((m, i) => (i === index ? { ...m, isStreaming: false } : m))
			);
		},
		reset: () => set([])
	};
}

function createToolCallsStore() {
	const { subscribe, set, update } = writable<ToolCall[]>([]);

	return {
		subscribe,
		set,
		update,
		addToolCall: (toolCall: Omit<ToolCall, 'response' | 'isLoading' | 'isExpanded'>) => {
			update((calls) => [
				...calls,
				{ ...toolCall, response: null, isLoading: true, isExpanded: true }
			]);
		},
		updateToolResponse: (id: string, response: string) => {
			update((calls) =>
				calls.map((tc) =>
					tc.id === id ? { ...tc, response, isLoading: false } : tc
				)
			);
		},
		toggleExpanded: (id: string) => {
			update((calls) =>
				calls.map((tc) =>
					tc.id === id ? { ...tc, isExpanded: !tc.isExpanded } : tc
				)
			);
		},
		reset: () => set([])
	};
}

// Helper to get current value from store
function get<T>(store: { subscribe: (fn: (value: T) => void) => () => void }): T {
	let value: T;
	store.subscribe((v) => (value = v))();
	return value!;
}

export const displayMessages = createDisplayMessagesStore();
export const toolCalls = createToolCallsStore();
export const conversationMessages = writable<ConversationMessage[]>([]);
export const isLoading = writable(false);
export const inputValue = writable('');

export const sessionUsage = writable<TokenUsage>({
	inputTokens: 0,
	outputTokens: 0,
	cacheReadTokens: 0,
	cacheWriteTokens: 0
});
export const lastRequestUsage = writable<TokenUsage | null>(null);

export const shouldAutoScroll = writable(true);

// Reset all chat state
export function resetChat() {
	displayMessages.reset();
	toolCalls.reset();
	conversationMessages.set([]);
	inputValue.set('');
	sessionUsage.set({ inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0 });
	lastRequestUsage.set(null);
}
