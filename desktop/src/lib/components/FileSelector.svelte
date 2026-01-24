<script lang="ts">
	import { showFileSelector, folderFiles, pendingSelection } from '$lib/stores/files';
	import {
		toggleFileSelection,
		confirmFileSelection,
		selectAllFiles,
		clearSelectedPath
	} from '$lib/services/fileService';
</script>

{#if $showFileSelector}
	<div class="flex items-center gap-3 px-4 py-2 bg-slate-800 border-b border-zinc-700 text-sm">
		<span class="text-zinc-400 shrink-0">
			Select files ({$pendingSelection.size}/{$folderFiles.length}):
		</span>
		<div class="flex flex-wrap gap-2 flex-1 overflow-x-auto">
			{#each $folderFiles as file}
				<button
					onclick={() => toggleFileSelection(file)}
					title={file}
					class="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-zinc-200 transition-colors whitespace-nowrap
						{$pendingSelection.has(file) ? 'bg-blue-900/60 border border-blue-500' : 'bg-zinc-700 border border-zinc-600 hover:bg-zinc-600 hover:border-blue-500'}"
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
				disabled={$pendingSelection.size === 0}
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
