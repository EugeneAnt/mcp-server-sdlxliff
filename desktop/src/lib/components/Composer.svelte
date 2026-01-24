<script lang="ts">
	import { inputValue, isLoading } from '$lib/stores/chat';
	import { sendMessage } from '$lib/services/chatService';

	let textareaEl: HTMLTextAreaElement;
	const lineHeight = 24;
	const maxLines = 10;
	const minHeight = lineHeight + 8; // 1 line + minimal padding
	const maxHeight = lineHeight * maxLines;

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			sendMessage();
		}
	}

	function autoResize() {
		if (!textareaEl) return;
		textareaEl.style.height = `${minHeight}px`;
		const newHeight = Math.min(textareaEl.scrollHeight, maxHeight);
		textareaEl.style.height = `${newHeight}px`;
	}

	$: if (textareaEl && $inputValue !== undefined) {
		setTimeout(autoResize, 0);
	}
</script>

<div class="p-4 bg-zinc-800 border-t border-zinc-700">
	<div class="relative flex items-end gap-2 px-4 py-2 border border-zinc-600 rounded-2xl bg-zinc-900 focus-within:border-zinc-500 transition-colors">
		<textarea
			bind:this={textareaEl}
			bind:value={$inputValue}
			onkeydown={handleKeydown}
			oninput={autoResize}
			placeholder="Type a message..."
			rows="1"
			disabled={$isLoading}
			class="flex-1 py-1.5 bg-transparent text-zinc-200 text-base font-sans resize-none focus:outline-none disabled:opacity-60 overflow-y-auto placeholder:text-zinc-500"
			style="min-height: {minHeight}px; max-height: {maxHeight}px;"
		></textarea>
		<button
			onclick={sendMessage}
			disabled={$isLoading || !$inputValue.trim()}
			class="flex-shrink-0 w-8 h-8 mb-0.5 flex items-center justify-center rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:bg-zinc-700 disabled:text-zinc-500 disabled:cursor-not-allowed transition-colors"
			title="Send message"
		>
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-4 h-4">
				<path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
			</svg>
		</button>
	</div>
</div>