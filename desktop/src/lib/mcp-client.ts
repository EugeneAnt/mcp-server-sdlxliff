import { invoke } from '@tauri-apps/api/core';

interface JsonRpcRequest {
	jsonrpc: '2.0';
	id: number;
	method: string;
	params?: Record<string, unknown>;
}

interface JsonRpcResponse {
	jsonrpc: '2.0';
	id: number;
	result?: unknown;
	error?: {
		code: number;
		message: string;
		data?: unknown;
	};
}

interface McpTool {
	name: string;
	description: string;
	inputSchema: Record<string, unknown>;
}

interface McpToolResult {
	content: Array<{ type: string; text?: string }>;
	isError?: boolean;
}

export class McpClient {
	private requestId = 0;
	private tools: McpTool[] = [];
	private initialized = false;
	private running = false;

	async connect(): Promise<void> {
		// Spawn the MCP server using Tauri command
		await invoke('spawn_mcp_server');
		this.running = true;

		// Initialize the MCP connection
		await this.initialize();
	}

	private async sendRequest(method: string, params?: Record<string, unknown>): Promise<unknown> {
		if (!this.running) {
			throw new Error('MCP server not connected');
		}

		const id = ++this.requestId;
		const request: JsonRpcRequest = {
			jsonrpc: '2.0',
			id,
			method,
			params
		};

		const message = JSON.stringify(request);
		const responseStr = await invoke<string>('mcp_request', { message });

		const response: JsonRpcResponse = JSON.parse(responseStr);

		if (response.error) {
			throw new Error(response.error.message);
		}

		return response.result;
	}

	private async initialize(): Promise<void> {
		// Send initialize request
		await this.sendRequest('initialize', {
			protocolVersion: '2024-11-05',
			capabilities: {},
			clientInfo: {
				name: 'sdlxliff-editor',
				version: '0.1.0'
			}
		});

		// Send initialized notification (no response expected)
		const notification = JSON.stringify({
			jsonrpc: '2.0',
			method: 'notifications/initialized'
		});
		await invoke('mcp_notify', { message: notification });

		// List available tools
		const toolsResult = await this.sendRequest('tools/list') as { tools: McpTool[] };
		this.tools = toolsResult.tools || [];
		this.initialized = true;

		console.log('[MCP] Connected. Available tools:', this.tools.map(t => t.name));
	}

	async disconnect(): Promise<void> {
		this.running = false;
		await invoke('stop_mcp_server');
		this.initialized = false;
	}

	isConnected(): boolean {
		return this.running && this.initialized;
	}

	getTools(): McpTool[] {
		return this.tools;
	}

	getToolsForClaude(): Array<{
		name: string;
		description: string;
		input_schema: Record<string, unknown>;
	}> {
		return this.tools.map(tool => ({
			name: tool.name,
			description: tool.description,
			input_schema: tool.inputSchema
		}));
	}

	async callTool(name: string, args: Record<string, unknown>): Promise<McpToolResult> {
		const result = await this.sendRequest('tools/call', {
			name,
			arguments: args
		});
		return result as McpToolResult;
	}
}

// Singleton instance
let mcpClient: McpClient | null = null;

export function getMcpClient(): McpClient | null {
	return mcpClient;
}

export async function connectMcpServer(): Promise<McpClient> {
	if (mcpClient?.isConnected()) {
		return mcpClient;
	}

	mcpClient = new McpClient();
	await mcpClient.connect();
	return mcpClient;
}

export async function disconnectMcpServer(): Promise<void> {
	if (mcpClient) {
		await mcpClient.disconnect();
		mcpClient = null;
	}
}