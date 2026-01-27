<script lang="ts">
	import { toolCalls } from '$lib/stores/chat';
	import { formatToolName } from '$lib/services/chatService';
	import { ragLastContext, ragLastSearchResults, ragInjectedContext } from '$lib/services/ragService';
	import { ragEnabled } from '$lib/stores/settings';

	let toolsContainer = $state<HTMLDivElement | null>(null);
	let ragExpanded = $state(false);
	let verbose = $state(false);

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
		<button
			onclick={() => (verbose = !verbose)}
			class="flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors {verbose ? 'bg-blue-500/20 text-blue-400' : 'bg-zinc-700/50 text-zinc-500 hover:text-zinc-400'}"
			title={verbose ? 'Switch to compact view' : 'Switch to verbose view'}
		>
			<span class="relative w-7 h-4 rounded-full transition-colors {verbose ? 'bg-blue-500' : 'bg-zinc-600'}">
				<span class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform {verbose ? 'translate-x-3' : 'translate-x-0'}"></span>
			</span>
			<span>Verbose</span>
		</button>
	</div>

	<!-- Tools List -->
	<div bind:this={toolsContainer} class="flex-1 overflow-y-auto">
		<!-- RAG Context Section -->
		{#if $ragEnabled && $ragLastContext.length > 0}
			<div class="border-b border-purple-900/50 bg-purple-950/20">
				<button
					onclick={() => (ragExpanded = !ragExpanded)}
					class="w-full flex items-center gap-2 px-4 py-3 hover:bg-purple-900/20 transition-colors text-left"
				>
					<span class="text-purple-400 transition-transform {ragExpanded ? 'rotate-90' : ''}">
						<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<polyline points="9 18 15 12 9 6"></polyline>
						</svg>
					</span>
					<span class="flex-1 text-sm font-medium text-purple-300">
						RAG Context ({$ragLastContext.length} matches)
					</span>
					<span class="text-xs text-purple-500">semantic search</span>
				</button>

				{#if ragExpanded}
					<div class="px-4 pb-3 space-y-2">
						<!-- Matched Segments -->
						{#each $ragLastContext as result, i}
							<div class="bg-zinc-900/50 rounded p-2 text-xs">
								<div class="flex items-center justify-between mb-1">
									<span class="text-purple-400 font-medium">Segment {result.segment.id}</span>
									<span class="text-purple-300 bg-purple-900/50 px-1.5 py-0.5 rounded">
										{(result.score * 100).toFixed(0)}%
									</span>
								</div>
								<div class="text-zinc-500 mb-1 truncate" title={result.segment.source}>
									<span class="text-zinc-600">S:</span> {result.segment.source.length > 60 ? result.segment.source.slice(0, 60) + '...' : result.segment.source}
								</div>
								<div class="text-zinc-400 truncate" title={result.segment.target}>
									<span class="text-zinc-600">T:</span> {result.segment.target.length > 60 ? result.segment.target.slice(0, 60) + '...' : result.segment.target}
								</div>
							</div>
						{/each}

						<!-- Injected Context (what Claude sees) -->
						{#if $ragInjectedContext}
							<div class="mt-3 pt-3 border-t border-purple-900/30">
								<div class="text-xs text-purple-500 uppercase tracking-wide mb-2">Injected into prompt</div>
								<pre class="text-xs bg-zinc-900 rounded p-2 overflow-x-auto text-purple-300/80 max-h-48 overflow-y-auto whitespace-pre-wrap">{$ragInjectedContext}</pre>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{/if}

		{#if $toolCalls.length === 0 && $ragLastContext.length === 0}
			<div class="flex items-center justify-center h-full text-zinc-600 text-sm">
				Tool calls will appear here
			</div>
		{:else if $toolCalls.length > 0}
			{#if verbose}
				<!-- Verbose Mode: Expandable tool details -->
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
			{:else}
				<!-- Compact Mode: Simple tool list -->
				<div class="px-3 py-2 space-y-1">
					{#each $toolCalls as tool}
						<div class="flex items-center gap-2 px-2 py-1.5 rounded bg-zinc-800/30 text-sm">
							{#if tool.isLoading}
								<span class="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0"></span>
							{:else}
								<span class="w-3 h-3 rounded-full bg-green-500/80 shrink-0"></span>
							{/if}
							<span class="text-zinc-300 truncate">{formatToolName(tool.name)}</span>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
	</div>
</div>
