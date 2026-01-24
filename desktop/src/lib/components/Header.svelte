<script lang="ts">
	import ModelSelect from './ModelSelect.svelte';
	import RagSettings from './RagSettings.svelte';
	import { showApiKeyInput } from '$lib/stores/settings';
	import { mcpConnected, mcpConnecting, mcpError, mcpTools } from '$lib/stores/mcp';
	import { handleSelectFile, handleSelectFolder } from '$lib/services/fileService';
	import { tryConnectMcp, clearApiKeyAndLogout, startNewChat } from '$lib/services/chatService';
</script>

<header class="flex items-center justify-between p-4 bg-zinc-800 border-b border-zinc-700">
	<h1 class="text-lg font-medium">XLIFF Chat</h1>
	<div class="flex items-center gap-4">
		{#if !$showApiKeyInput}
			<button
				onclick={startNewChat}
				title="Start new chat"
				class="flex items-center gap-1.5 text-sm px-2.5 py-1.5 rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600 transition-colors"
			>
				<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M12 5v14M5 12h14"></path>
				</svg>
				<span class="text-xs">New</span>
			</button>
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
			<ModelSelect />
			<RagSettings />
			<button
				onclick={tryConnectMcp}
				disabled={$mcpConnecting}
				title={$mcpConnected ? 'Click to reconnect' : 'Click to connect'}
				class="text-sm px-2 py-1 rounded transition-colors disabled:cursor-wait
					{$mcpConnected ? 'bg-green-900/50 text-green-400' : $mcpError ? 'bg-red-900/50 text-red-400' : 'bg-zinc-700 text-zinc-500 hover:bg-zinc-600'}"
			>
				{#if $mcpConnecting}
					MCP connecting...
				{:else if $mcpConnected}
					MCP connected ({$mcpTools.length} tools)
				{:else if $mcpError}
					MCP error - click to retry
				{:else}
					MCP disconnected - click to connect
				{/if}
			</button>
			<button
				onclick={clearApiKeyAndLogout}
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
