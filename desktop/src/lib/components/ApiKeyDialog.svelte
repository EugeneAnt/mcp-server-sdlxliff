<script lang="ts">
	import { apiKey } from '$lib/stores/settings';
	import { saveApiKey } from '$lib/services/chatService';

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			saveApiKey();
		}
	}
</script>

<div class="flex-1 flex items-center justify-center p-8">
	<div class="bg-zinc-800 p-8 rounded-2xl max-w-md text-center">
		<h2 class="text-2xl font-semibold mb-2">Welcome to XLIFF Chat</h2>
		<p class="text-zinc-500 mb-6">Enter your Anthropic API key to get started.</p>
		<div class="flex gap-2">
			<input
				type="password"
				bind:value={$apiKey}
				placeholder="sk-ant-..."
				onkeydown={handleKeydown}
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
