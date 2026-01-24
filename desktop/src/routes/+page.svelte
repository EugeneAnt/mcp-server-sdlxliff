<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		initializeClient,
		streamChatWithTools,
		type ConversationMessage,
		type ToolUseBlock,
		type TokenUsage
	} from '$lib/claude';
	import {
		connectMcpServer,
		disconnectMcpServer,
		getMcpClient,
		type McpClient
	} from '$lib/mcp-client';
	import { selectSdlxliffFile, selectFolder, findSdlxliffFiles } from '$lib/file-picker';
	import type Anthropic from '@anthropic-ai/sdk';

	interface DisplayMessage {
		role: 'user' | 'assistant' | 'tool';
		content: string;
		toolName?: string;
		isStreaming?: boolean;
	}

	let displayMessages: DisplayMessage[] = [];
	let conversationMessages: ConversationMessage[] = [];
	let inputValue = '';
	let isLoading = false;
	let messagesContainer: HTMLDivElement;
	let apiKey = '';
	let showApiKeyInput = true;
	let mcpConnected = false;
	let mcpConnecting = false;
	let mcpError = '';
	let mcpTools: Anthropic.Tool[] = [];
	let selectedPaths: string[] = [];
	let folderFiles: string[] = [];
	let showFileSelector = false;
	let currentFolder: string | null = null;
	let pendingSelection: Set<string> = new Set();

	// Token usage tracking
	let sessionUsage: TokenUsage = { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0 };
	let lastRequestUsage: TokenUsage | null = null;

	async function handleSelectFile() {
		const path = await selectSdlxliffFile();
		if (path) {
			selectedPaths = [path];
			folderFiles = [];
			showFileSelector = false;
			currentFolder = null;
			pendingSelection = new Set();
		}
	}

	async function handleSelectFolder() {
		const path = await selectFolder();
		if (path) {
			currentFolder = path;
			const files = await findSdlxliffFiles(path);

			if (files.length === 0) {
				alert('No .sdlxliff files found in this folder.');
				return;
			} else if (files.length === 1) {
				selectedPaths = [files[0]];
				folderFiles = [];
				showFileSelector = false;
			} else {
				folderFiles = files;
				showFileSelector = true;
				pendingSelection = new Set();
			}
		}
	}

	function toggleFileSelection(filePath: string) {
		if (pendingSelection.has(filePath)) {
			pendingSelection.delete(filePath);
		} else {
			pendingSelection.add(filePath);
		}
		pendingSelection = pendingSelection;
	}

	function confirmFileSelection() {
		if (pendingSelection.size > 0) {
			selectedPaths = Array.from(pendingSelection).sort();
			showFileSelector = false;
			pendingSelection = new Set();
		}
	}

	function selectAllFiles() {
		pendingSelection = new Set(folderFiles);
	}

	function clearSelectedPath() {
		selectedPaths = [];
		folderFiles = [];
		showFileSelector = false;
		currentFolder = null;
		pendingSelection = new Set();
	}

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

	onMount(async () => {
		const storedKey = localStorage.getItem('anthropic_api_key');
		if (storedKey) {
			try {
				apiKey = storedKey;
				initializeClient(storedKey);
				showApiKeyInput = false;
				await tryConnectMcp();
			} catch (error) {
				console.error('Failed to initialize from stored key:', error);
				// Clear invalid key and show input
				localStorage.removeItem('anthropic_api_key');
				showApiKeyInput = true;
			}
		}
	});

	onDestroy(async () => {
		await disconnectMcpServer();
	});

	async function tryConnectMcp() {
		mcpConnecting = true;
		mcpError = '';
		mcpConnected = false;

		try {
			await disconnectMcpServer();
		} catch (e) {
			// Ignore disconnect errors
		}

		try {
			const client = await connectMcpServer();
			mcpConnected = client.isConnected();
			mcpTools = client.getToolsForClaude() as Anthropic.Tool[];
			console.log('MCP connected, tools:', mcpTools.map(t => t.name));
		} catch (error) {
			// Tauri errors can be strings or objects
			if (error instanceof Error) {
				mcpError = error.message;
			} else if (typeof error === 'string') {
				mcpError = error;
			} else {
				mcpError = JSON.stringify(error);
			}
			mcpConnected = false;
			console.error('MCP connection failed:', error);
		}
		mcpConnecting = false;
	}

	function saveApiKey() {
		if (apiKey.trim()) {
			try {
				localStorage.setItem('anthropic_api_key', apiKey.trim());
				initializeClient(apiKey.trim());
				showApiKeyInput = false;
				tryConnectMcp();
			} catch (error) {
				console.error('Failed to initialize client:', error);
				alert('Failed to initialize: ' + (error instanceof Error ? error.message : 'Unknown error'));
			}
		}
	}

	function clearApiKey() {
		localStorage.removeItem('anthropic_api_key');
		apiKey = '';
		showApiKeyInput = true;
		disconnectMcpServer();
		mcpConnected = false;
	}

	async function handleToolCall(toolUse: ToolUseBlock): Promise<string> {
		const client = getMcpClient();
		if (!client) {
			throw new Error('MCP server not connected');
		}

		displayMessages = [...displayMessages, {
			role: 'tool',
			content: `Calling ${toolUse.name}...`,
			toolName: toolUse.name
		}];

		const result = await client.callTool(toolUse.name, toolUse.input);
		const resultText = result.content
			.map(c => c.text || JSON.stringify(c))
			.join('\n');

		displayMessages = displayMessages.map((m, i) =>
			i === displayMessages.length - 1 && m.role === 'tool'
				? { ...m, content: resultText }
				: m
		);

		return resultText;
	}

	async function sendMessage() {
		if (!inputValue.trim() || isLoading) return;

		const userMessage = inputValue.trim();
		inputValue = '';
		shouldAutoScroll = true;

		const contextPrefix = selectedPaths.length > 0
			? `[Working with ${selectedPaths.length} file${selectedPaths.length > 1 ? 's' : ''}:\n${selectedPaths.map(p => `- ${p}`).join('\n')}]\n\n`
			: '';
		const messageWithContext = contextPrefix + userMessage;

		displayMessages = [...displayMessages, { role: 'user', content: userMessage }];
		conversationMessages = [...conversationMessages, { role: 'user', content: messageWithContext }];
		isLoading = true;

		let assistantMessage = '';
		let assistantDisplayIndex = -1;

		try {
			const tools = mcpConnected ? mcpTools : [];

			for await (const event of streamChatWithTools(
				conversationMessages,
				systemPrompt,
				tools,
				mcpConnected ? handleToolCall : undefined
			)) {
				if (event.type === 'text' && event.content) {
					assistantMessage += event.content;

					if (assistantDisplayIndex === -1) {
						displayMessages = [...displayMessages, {
							role: 'assistant',
							content: assistantMessage,
							isStreaming: true
						}];
						assistantDisplayIndex = displayMessages.length - 1;
					} else {
						displayMessages = displayMessages.map((m, i) =>
							i === assistantDisplayIndex
								? { ...m, content: assistantMessage }
								: m
						);
					}
				} else if (event.type === 'usage' && event.usage) {
					lastRequestUsage = event.usage;
					sessionUsage = {
						inputTokens: sessionUsage.inputTokens + event.usage.inputTokens,
						outputTokens: sessionUsage.outputTokens + event.usage.outputTokens,
						cacheReadTokens: (sessionUsage.cacheReadTokens || 0) + (event.usage.cacheReadTokens || 0),
						cacheWriteTokens: (sessionUsage.cacheWriteTokens || 0) + (event.usage.cacheWriteTokens || 0)
					};
				} else if (event.type === 'done') {
					if (assistantDisplayIndex !== -1) {
						displayMessages = displayMessages.map((m, i) =>
							i === assistantDisplayIndex
								? { ...m, isStreaming: false }
								: m
						);
					}
					if (assistantMessage) {
						conversationMessages = [...conversationMessages, {
							role: 'assistant',
							content: assistantMessage
						}];
					}
				}
			}
		} catch (error) {
			const errorMessage = error instanceof Error ? error.message : 'An error occurred';
			displayMessages = [...displayMessages, {
				role: 'assistant',
				content: `Error: ${errorMessage}`
			}];
		}

		isLoading = false;
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			sendMessage();
		}
	}

	let shouldAutoScroll = true;
	let lastMessageCount = 0;

	function handleScroll() {
		if (!messagesContainer) return;
		const { scrollTop, scrollHeight, clientHeight } = messagesContainer;
		shouldAutoScroll = scrollHeight - scrollTop - clientHeight < 100;
	}

	$: if (messagesContainer && displayMessages.length > lastMessageCount) {
		lastMessageCount = displayMessages.length;
		if (shouldAutoScroll) {
			setTimeout(() => {
				messagesContainer.scrollTop = messagesContainer.scrollHeight;
			}, 0);
		}
	}
</script>

<div class="flex flex-col h-screen bg-zinc-900 text-zinc-200 font-sans">
	<!-- Header -->
	<header class="flex items-center justify-between p-4 bg-zinc-800 border-b border-zinc-700">
		<h1 class="text-lg font-medium">XLIFF Chat</h1>
		<div class="flex items-center gap-4">
			{#if !showApiKeyInput}
				<button
					onclick={handleSelectFile}
					title="Select SDLXLIFF file"
					class="flex items-center gap-1.5 text-sm px-2.5 py-1.5 rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600 transition-colors"
				>
					<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
						<polyline points="14 2 14 8 20 8"></polyline>
					</svg>
					<span class="text-xs">File</span>
				</button>
				<button
					onclick={handleSelectFolder}
					title="Select folder"
					class="flex items-center gap-1.5 text-sm px-2.5 py-1.5 rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600 transition-colors"
				>
					<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
					</svg>
					<span class="text-xs">Folder</span>
				</button>
				<button
					onclick={tryConnectMcp}
					disabled={mcpConnecting}
					title={mcpConnected ? 'Click to reconnect' : 'Click to connect'}
					class="text-sm px-2 py-1 rounded transition-colors disabled:cursor-wait
						{mcpConnected ? 'bg-green-900/50 text-green-400' : mcpError ? 'bg-red-900/50 text-red-400' : 'bg-zinc-700 text-zinc-500 hover:bg-zinc-600'}"
				>
					{#if mcpConnecting}
						MCP connecting...
					{:else if mcpConnected}
						MCP connected ({mcpTools.length} tools)
					{:else if mcpError}
						MCP error - click to retry
					{:else}
						MCP disconnected - click to connect
					{/if}
				</button>
				<button
					onclick={clearApiKey}
					title="Change API Key"
					class="p-2 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-700 transition-colors"
				>
					<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<circle cx="12" cy="12" r="3"></circle>
						<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
					</svg>
				</button>
			{/if}
		</div>
	</header>

	<!-- Selected Path Bar -->
	{#if selectedPaths.length > 0}
		<div class="flex items-center gap-2 px-4 py-2 bg-zinc-800/50 border-b border-zinc-700 text-sm">
			<span class="text-blue-400 shrink-0">
				<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
					<polyline points="14 2 14 8 20 8"></polyline>
				</svg>
			</span>
			{#if selectedPaths.length === 1}
				<span class="flex-1 truncate text-zinc-400 font-mono text-xs" title={selectedPaths[0]}>{selectedPaths[0]}</span>
			{:else}
				<span class="flex-1 text-zinc-400 font-mono text-xs" title={selectedPaths.join('\n')}>
					{selectedPaths.length} files selected
				</span>
			{/if}
			<button
				onclick={clearSelectedPath}
				title="Clear selection"
				class="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-zinc-700 transition-colors shrink-0"
			>
				<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<line x1="18" y1="6" x2="6" y2="18"></line>
					<line x1="6" y1="6" x2="18" y2="18"></line>
				</svg>
			</button>
		</div>
	{/if}

	<!-- Token Usage Bar -->
	{#if sessionUsage.inputTokens > 0}
		<div class="flex items-center justify-between px-4 py-1.5 bg-zinc-800/30 border-b border-zinc-700/50 text-xs font-mono">
			<div class="flex items-center gap-4 text-zinc-500">
				<span title="Total tokens this session">
					Session: <span class="text-zinc-400">{(sessionUsage.inputTokens + sessionUsage.outputTokens).toLocaleString()}</span> tokens
				</span>
				{#if sessionUsage.cacheReadTokens}
					<span title="Tokens read from cache (90% cheaper)" class="text-green-500">
						Cache hit: {sessionUsage.cacheReadTokens.toLocaleString()}
					</span>
				{/if}
			</div>
			{#if lastRequestUsage}
				<div class="flex items-center gap-3 text-zinc-600">
					<span>Last: ↓{lastRequestUsage.inputTokens.toLocaleString()} ↑{lastRequestUsage.outputTokens.toLocaleString()}</span>
					{#if lastRequestUsage.cacheReadTokens}
						<span class="text-green-600">cached: {lastRequestUsage.cacheReadTokens.toLocaleString()}</span>
					{/if}
				</div>
			{/if}
		</div>
	{/if}

	<!-- File Selector Bar -->
	{#if showFileSelector}
		<div class="flex items-center gap-3 px-4 py-2 bg-slate-800 border-b border-zinc-700 text-sm">
			<span class="text-zinc-400 shrink-0">
				Select files ({pendingSelection.size}/{folderFiles.length}):
			</span>
			<div class="flex flex-wrap gap-2 flex-1 overflow-x-auto">
				{#each folderFiles as file}
					<button
						onclick={() => toggleFileSelection(file)}
						title={file}
						class="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-zinc-200 transition-colors whitespace-nowrap
							{pendingSelection.has(file) ? 'bg-blue-900/60 border border-blue-500' : 'bg-zinc-700 border border-zinc-600 hover:bg-zinc-600 hover:border-blue-500'}"
					>
						<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-blue-400 shrink-0">
							<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
							<polyline points="14 2 14 8 20 8"></polyline>
						</svg>
						<span>{file.split('/').pop()}</span>
					</button>
				{/each}
			</div>
			<div class="flex items-center gap-2 shrink-0">
				<button
					onclick={selectAllFiles}
					title="Select all"
					class="px-2.5 py-1.5 rounded text-xs bg-zinc-700 text-zinc-200 hover:bg-zinc-600 transition-colors"
				>
					All
				</button>
				<button
					onclick={confirmFileSelection}
					disabled={pendingSelection.size === 0}
					title="Confirm selection"
					class="px-2.5 py-1.5 rounded text-xs bg-blue-500 text-white hover:bg-blue-600 disabled:bg-zinc-700 disabled:text-zinc-500 disabled:cursor-not-allowed transition-colors"
				>
					OK
				</button>
				<button
					onclick={clearSelectedPath}
					title="Cancel"
					class="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-zinc-700 transition-colors"
				>
					<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<line x1="18" y1="6" x2="6" y2="18"></line>
						<line x1="6" y1="6" x2="18" y2="18"></line>
					</svg>
				</button>
			</div>
		</div>
	{/if}

	<!-- Main Content -->
	<main class="flex-1 flex flex-col overflow-hidden">
		{#if showApiKeyInput}
			<div class="flex-1 flex items-center justify-center p-8">
				<div class="bg-zinc-800 p-8 rounded-2xl max-w-md text-center">
					<h2 class="text-2xl font-semibold mb-2">Welcome to XLIFF Chat</h2>
					<p class="text-zinc-500 mb-6">Enter your Anthropic API key to get started.</p>
					<div class="flex gap-2">
						<input
							type="password"
							bind:value={apiKey}
							placeholder="sk-ant-..."
							onkeydown={(e) => e.key === 'Enter' && saveApiKey()}
							class="flex-1 px-4 py-3 border border-zinc-700 rounded-lg bg-zinc-900 text-zinc-200 text-base focus:border-blue-500 focus:outline-none"
						/>
						<button
							onclick={saveApiKey}
							class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
						>
							Save
						</button>
					</div>
					<p class="text-xs text-zinc-600 mt-4">Your key is stored locally and never sent anywhere except Anthropic's API.</p>
				</div>
			</div>
		{:else}
			<!-- Messages -->
			<div bind:this={messagesContainer} onscroll={handleScroll} class="flex-1 overflow-y-auto p-4">
				{#if displayMessages.length === 0}
					<div class="text-center text-zinc-500 mt-16">
						<p>Start a conversation to translate and edit SDLXLIFF files.</p>
						<p class="text-sm text-zinc-600 italic mt-2">Try: "Open ~/Documents/sample.sdlxliff and show me the statistics"</p>
						{#if !mcpConnected && mcpError}
							<p class="text-sm text-red-400 mt-2">MCP Error: {mcpError}</p>
						{/if}
					</div>
				{/if}

				{#each displayMessages as message}
					<div class="mb-4 flex flex-col {message.role === 'user' ? 'items-end' : 'items-start'}">
						{#if message.role === 'tool'}
							<div class="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded mb-1 font-mono">
								{message.toolName}
							</div>
						{/if}
						<div class="max-w-[80%] px-4 py-3 rounded-2xl whitespace-pre-wrap break-words text-[15px] leading-relaxed
							{message.role === 'user' ? 'bg-blue-500 text-white rounded-br-sm' : ''}
							{message.role === 'assistant' ? 'bg-zinc-700 rounded-bl-sm' : ''}
							{message.role === 'tool' ? 'bg-slate-800 border border-blue-500/20 font-mono text-sm max-h-52 overflow-y-auto' : ''}
							{message.isStreaming ? 'border-r-2 border-blue-500 animate-pulse' : ''}"
						>
							{message.content}
						</div>
					</div>
				{/each}

				{#if isLoading && displayMessages[displayMessages.length - 1]?.role === 'user'}
					<div class="mb-4 flex flex-col items-start">
						<div class="bg-zinc-700 px-4 py-4 rounded-2xl rounded-bl-sm flex gap-1.5">
							<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: -0.32s"></span>
							<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: -0.16s"></span>
							<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce"></span>
						</div>
					</div>
				{/if}
			</div>

			<!-- Input Area -->
			<div class="flex gap-2 p-4 bg-zinc-800 border-t border-zinc-700">
				<textarea
					bind:value={inputValue}
					onkeydown={handleKeydown}
					placeholder="Type a message..."
					rows="1"
					disabled={isLoading}
					class="flex-1 px-4 py-3 border border-zinc-700 rounded-3xl bg-zinc-900 text-zinc-200 text-base font-sans resize-none focus:border-blue-500 focus:outline-none disabled:opacity-60"
				></textarea>
				<button
					onclick={sendMessage}
					disabled={isLoading || !inputValue.trim()}
					class="px-6 py-3 bg-blue-500 text-white rounded-3xl text-base hover:bg-blue-600 disabled:bg-zinc-700 disabled:cursor-not-allowed transition-colors"
				>
					Send
				</button>
			</div>
		{/if}
	</main>
</div>