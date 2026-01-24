<script lang="ts">
	import { selectedPaths } from '$lib/stores/files';
	import { clearSelectedPath } from '$lib/services/fileService';
</script>

{#if $selectedPaths.length > 0}
	<div class="flex items-center gap-2 px-4 py-2 bg-zinc-800/50 border-b border-zinc-700 text-sm">
		<span class="text-blue-400 shrink-0">
			<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
				<polyline points="14 2 14 8 20 8"></polyline>
			</svg>
		</span>
		{#if $selectedPaths.length === 1}
			<span class="flex-1 truncate text-zinc-400 font-mono text-xs" title={$selectedPaths[0]}>{$selectedPaths[0]}</span>
		{:else}
			<span class="flex-1 text-zinc-400 font-mono text-xs" title={$selectedPaths.join('\n')}>
				{$selectedPaths.length} files selected
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
