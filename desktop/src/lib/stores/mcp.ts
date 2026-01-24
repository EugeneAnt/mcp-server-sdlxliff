import { writable, derived } from 'svelte/store';

export interface Tool {
	name: string;
	description: string;
	input_schema: Record<string, unknown>;
}

export const mcpConnected = writable(false);
export const mcpConnecting = writable(false);
export const mcpError = writable('');
export const mcpTools = writable<Tool[]>([]);

// Derived store for connection status text
export const mcpStatusText = derived(
	[mcpConnected, mcpConnecting, mcpError, mcpTools],
	([$connected, $connecting, $error, $tools]) => {
		if ($connecting) return 'MCP connecting...';
		if ($connected) return `MCP connected (${$tools.length} tools)`;
		if ($error) return 'MCP error - click to retry';
		return 'MCP disconnected - click to connect';
	}
);

// Reset MCP state
export function resetMcp() {
	mcpConnected.set(false);
	mcpConnecting.set(false);
	mcpError.set('');
	mcpTools.set([]);
}
