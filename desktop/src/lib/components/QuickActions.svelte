<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import quickActionsData from '$lib/data/quickActions.json';

	const dispatch = createEventDispatcher<{ select: string }>();

	interface QuickAction {
		id: string;
		label: string;
		icon: string;
		prompt: string;
	}

	const actions: QuickAction[] = quickActionsData.actions;

	function handleClick(action: QuickAction) {
		dispatch('select', action.prompt);
	}

	// Simple icon components (inline SVG to avoid dependencies)
	function getIcon(icon: string): string {
		switch (icon) {
			case 'clipboard-check':
				return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
					<rect x="9" y="3" width="6" height="4" rx="1"/>
					<path d="m9 14 2 2 4-4"/>
				</svg>`;
			case 'search':
				return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<circle cx="11" cy="11" r="8"/>
					<path d="m21 21-4.3-4.3"/>
				</svg>`;
			case 'chart':
				return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<path d="M3 3v18h18"/>
					<path d="m19 9-5 5-4-4-3 3"/>
				</svg>`;
			case 'alert':
				return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<circle cx="12" cy="12" r="10"/>
					<line x1="12" x2="12" y1="8" y2="12"/>
					<line x1="12" x2="12.01" y1="16" y2="16"/>
				</svg>`;
			default:
				return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<circle cx="12" cy="12" r="10"/>
				</svg>`;
		}
	}
</script>

<div class="flex flex-wrap gap-2 justify-center mt-6 px-4">
	{#each actions as action}
		<button
			onclick={() => handleClick(action)}
			class="flex items-center gap-2 px-4 py-2.5 rounded-xl
				bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-zinc-600
				text-zinc-300 hover:text-zinc-100 text-sm font-medium
				transition-all duration-150 ease-out
				hover:shadow-lg hover:shadow-zinc-900/50
				active:scale-[0.98]"
		>
			<span class="text-zinc-400">
				{@html getIcon(action.icon)}
			</span>
			<span>{action.label}</span>
		</button>
	{/each}
</div>