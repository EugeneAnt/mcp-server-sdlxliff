<script lang="ts">
	import { onMount } from 'svelte';
	import { displayMessages, isLoading, shouldAutoScroll } from '$lib/stores/chat';
	import { mcpConnected, mcpError } from '$lib/stores/mcp';

	let messagesContainer: HTMLDivElement;
	let lastMessageCount = 0;

	function handleScroll() {
		if (!messagesContainer) return;
		const { scrollTop, scrollHeight, clientHeight } = messagesContainer;
		shouldAutoScroll.set(scrollHeight - scrollTop - clientHeight < 100);
	}

	// Export scroll function for external use
	export function scrollToBottom() {
		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight;
		}
	}

	// Auto-scroll on new messages
	$: if (messagesContainer && $displayMessages.length > lastMessageCount) {
		lastMessageCount = $displayMessages.length;
		if ($shouldAutoScroll) {
			setTimeout(() => {
				messagesContainer.scrollTop = messagesContainer.scrollHeight;
			}, 0);
		}
	}
</script>

<div bind:this={messagesContainer} onscroll={handleScroll} class="flex-1 overflow-y-auto p-4">
	{#if $displayMessages.length === 0}
		<div class="text-center text-zinc-500 mt-16">
			<p>Start a conversation to translate and edit SDLXLIFF files.</p>
			<p class="text-sm text-zinc-600 italic mt-2">Try: "Open ~/Documents/sample.sdlxliff and show me the statistics"</p>
			{#if !$mcpConnected && $mcpError}
				<p class="text-sm text-red-400 mt-2">MCP Error: {$mcpError}</p>
			{/if}
		</div>
	{/if}

	{#each $displayMessages as message}
		<div class="mb-4 flex flex-col {message.role === 'user' ? 'items-end' : 'items-start'}">
			<div class="max-w-[85%] px-4 py-3 rounded-2xl whitespace-pre-wrap break-words text-[15px] leading-relaxed
				{message.role === 'user' ? 'bg-blue-500 text-white rounded-br-sm' : 'bg-zinc-700 rounded-bl-sm'}
				{message.isStreaming ? 'border-r-2 border-blue-500 animate-pulse' : ''}"
			>
				{message.content}
			</div>
		</div>
	{/each}

	{#if $isLoading && $displayMessages[$displayMessages.length - 1]?.role === 'user'}
		<div class="mb-4 flex flex-col items-start">
			<div class="bg-zinc-700 px-4 py-4 rounded-2xl rounded-bl-sm flex gap-1.5">
				<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: -0.32s"></span>
				<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" style="animation-delay: -0.16s"></span>
				<span class="w-2 h-2 bg-zinc-500 rounded-full animate-bounce"></span>
			</div>
		</div>
	{/if}
</div>
