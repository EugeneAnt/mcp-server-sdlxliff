<script lang="ts">
	import { sessionUsage, lastRequestUsage } from '$lib/stores/chat';
	import { currentModelDisplayName } from '$lib/stores/models';
	import { ragEnabled } from '$lib/stores/settings';
	import {
		ragInitialized,
		ragIndexedSegments,
		ragLastSearchResults,
		ragIndexing,
		ragSearchCount,
		ragTokensUsed
	} from '$lib/services/ragService';
</script>

{#if $sessionUsage.inputTokens > 0 || $currentModelDisplayName || ($ragEnabled && $ragInitialized)}
	<div class="flex items-center justify-between px-4 py-1.5 bg-zinc-800/30 border-b border-zinc-700/50 text-xs font-mono">
		<div class="flex items-center gap-4 text-zinc-500">
			{#if $currentModelDisplayName}
				<span title="Model used for last request" class="text-blue-400">
					{$currentModelDisplayName}
				</span>
			{/if}
			{#if $sessionUsage.inputTokens > 0}
				<span title="Total tokens this session">
					Session: <span class="text-zinc-400">{($sessionUsage.inputTokens + $sessionUsage.outputTokens).toLocaleString()}</span> tokens
				</span>
			{/if}
			{#if $sessionUsage.cacheReadTokens}
				<span title="Tokens read from cache (90% cheaper)" class="text-green-500">
					Cache hit: {$sessionUsage.cacheReadTokens.toLocaleString()}
				</span>
			{/if}
			{#if $sessionUsage.cacheWriteTokens}
				<span title="Tokens written to cache (25% more expensive, but enables future cache hits)" class="text-amber-500">
					Cache write: {$sessionUsage.cacheWriteTokens.toLocaleString()}
				</span>
			{/if}
			{#if $ragEnabled && $ragInitialized}
				<span title="RAG semantic search - segments indexed for search" class="text-purple-400">
					{#if $ragIndexing}
						RAG: <span class="animate-pulse">indexing...</span>
					{:else if $ragIndexedSegments > 0}
						RAG: {$ragIndexedSegments} indexed
					{:else}
						RAG: ready
					{/if}
				</span>
				{#if $ragSearchCount > 0}
					<span title="RAG searches performed this session" class="text-purple-300">
						{$ragSearchCount} search{$ragSearchCount !== 1 ? 'es' : ''} (~{$ragTokensUsed.toLocaleString()} tokens)
					</span>
				{/if}
			{/if}
		</div>
		{#if $lastRequestUsage}
			<div class="flex items-center gap-3 text-zinc-600">
				<span>Last: ↓{$lastRequestUsage.inputTokens.toLocaleString()} ↑{$lastRequestUsage.outputTokens.toLocaleString()}</span>
				{#if $lastRequestUsage.cacheReadTokens}
					<span class="text-green-600">cached: {$lastRequestUsage.cacheReadTokens.toLocaleString()}</span>
				{/if}
				{#if $lastRequestUsage.cacheWriteTokens}
					<span class="text-amber-600">written: {$lastRequestUsage.cacheWriteTokens.toLocaleString()}</span>
				{/if}
			</div>
		{/if}
	</div>
{/if}
