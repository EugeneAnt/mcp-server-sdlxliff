<script lang="ts">
	import { toolCalls } from '$lib/stores/chat';
	import { formatToolName } from '$lib/services/chatService';

	let toolsContainer: HTMLDivElement;

	function toggleToolExpanded(toolId: string) {
		toolCalls.toggleExpanded(toolId);
	}

	// Export scroll function for external use
	export function scrollToBottom() {
		if (toolsContainer) {
			toolsContainer.scrollTop = toolsContainer.scrollHeight;
		}
	}
</script>

<div class="w-96 flex flex-col bg-zinc-850 shrink-0">
	<!-- Tools Header -->
	<div class="flex items-center justify-between px-4 py-3 bg-zinc-800 border-b border-zinc-700">
		<span class="text-sm font-medium text-zinc-400 uppercase tracking-wide">
			{$toolCalls.length} Tool Call{$toolCalls.length !== 1 ? 's' : ''}
		</span>
	</div>

	<!-- Tools List -->
	<div bind:this={toolsContainer} class="flex-1 overflow-y-auto">
		{#if $toolCalls.length === 0}
			<div class="flex items-center justify-center h-full text-zinc-600 text-sm">
				Tool calls will appear here
			</div>
		{:else}
			{#each $toolCalls as tool}
				<div class="border-b border-zinc-700/50">
					<!-- Tool Header -->
					<button
						onclick={() => toggleToolExpanded(tool.id)}
						class="w-full flex items-center gap-2 px-4 py-3 hover:bg-zinc-800/50 transition-colors text-left"
					>
						<span class="text-zinc-500 transition-transform {tool.isExpanded ? 'rotate-90' : ''}">
							<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<polyline points="9 18 15 12 9 6"></polyline>
							</svg>
						</span>
						<span class="flex-1 text-sm font-medium text-zinc-300">
							{formatToolName(tool.name)}
						</span>
						{#if tool.isLoading}
							<span class="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></span>
						{/if}
					</button>

					<!-- Tool Content -->
					{#if tool.isExpanded}
						<div class="px-4 pb-3 space-y-2">
							<!-- Request -->
							<div>
								<div class="text-xs text-zinc-500 uppercase tracking-wide mb-1">Request</div>
								<pre class="text-xs bg-zinc-900 rounded p-2 overflow-x-auto text-green-400 max-h-32 overflow-y-auto">{JSON.stringify(tool.request, null, 2)}</pre>
							</div>

							<!-- Response -->
							{#if tool.response}
								<div>
									<div class="text-xs text-zinc-500 uppercase tracking-wide mb-1">Response</div>
									<pre class="text-xs bg-zinc-900 rounded p-2 overflow-x-auto text-zinc-400 max-h-48 overflow-y-auto">{tool.response.length > 2000 ? tool.response.slice(0, 2000) + '\n... (truncated)' : tool.response}</pre>
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		{/if}
	</div>
</div>
