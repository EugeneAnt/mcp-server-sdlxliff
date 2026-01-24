<script lang="ts">
	import { inputValue, isLoading } from '$lib/stores/chat';
	import { sendMessage } from '$lib/services/chatService';

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			sendMessage();
		}
	}
</script>

<div class="flex gap-2 p-4 bg-zinc-800 border-t border-zinc-700">
	<textarea
		bind:value={$inputValue}
		onkeydown={handleKeydown}
		placeholder="Type a message..."
		rows="1"
		disabled={$isLoading}
		class="flex-1 px-4 py-3 border border-zinc-700 rounded-3xl bg-zinc-900 text-zinc-200 text-base font-sans resize-none focus:border-blue-500 focus:outline-none disabled:opacity-60"
	></textarea>
	<button
		onclick={sendMessage}
		disabled={$isLoading || !$inputValue.trim()}
		class="px-6 py-3 bg-blue-500 text-white rounded-3xl text-base hover:bg-blue-600 disabled:bg-zinc-700 disabled:cursor-not-allowed transition-colors"
	>
		Send
	</button>
</div>
